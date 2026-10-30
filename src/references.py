"""The one place the agent talks to the reference engine.

Every reference — a Word paragraph, a ``\\bibitem`` body or a ``.bib`` entry —
is formatted, looked up and integrity-checked by ``jacow_formatter``.  This
module turns the formatter's answer into the agent's vocabulary:

=================================================  ============================
Formatter result                                   Agent outcome
=================================================  ============================
Only presentation changes (``DOI:`` → ``doi:``,    Tier.AUTO
"et al" punctuation, serial comma, quotes, dash)
Full reformat that passes check_rewrite and        Tier.SUGGEST
adds no fields from lookups
Reformat that fills in or corrects fields from     Tier.SUGGEST, each value and
Crossref, DataCite or JACoW                        its source on the card
integrity ``doi_mismatch``                         flag: REF-INT-01
integrity ``suspected_fabricated``                 flag: REF-INT-02
integrity ``unverifiable``                         INFO: REF-INT-03, NOT CHECKED
Fails check_rewrite, or a "defaulted" flag         rewrite discarded, author's
                                                   text kept (FMT-REF-03, INFO)
=================================================  ============================

Nothing else in the agent imports ``jacow_formatter`` directly, so a change of
engine version is a change to this file and its tests.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from jacow_formatter import (  # re-exported for the rest of the agent
    AgentConfig,
    JacowAgent,
    TitleCasing,
    check_rewrite,
    proper_noun_risk,
    sent_case_report,
    split_refs,
)
from jacow_formatter.journals import normalize_journal

from src.edits import Tier
from src.house_style import HouseStyle, load_house_style
from src.models import Finding, Severity

__all__ = [
    "ReferenceResult", "screen_reference", "doi_form_only", "formatter_config", "presentation_only",
    "latex_to_plain", "plain_to_latex", "lowercase_evidence", "check_rewrite", "proper_noun_risk",
    "sent_case_report", "TitleCasing", "normalize_journal", "split_refs",
]

# Formatter source/stage names, as an editor would recognise them.
_SOURCE_NAMES = {
    "search-cascade": "Crossref or DataCite",
    "crossref": "Crossref",
    "datacite": "DataCite",
    "jacow-db": "the JACoW proceedings database",
    "refdb": "refs.jacow.org",
    "arxiv": "arXiv",
    "isbn": "OpenLibrary",
    "inspirehep": "INSPIRE",
    "llm": "a language model",
    "llm-journal": "a language model",
}

_INTEGRITY_FINDINGS = {
    "doi_mismatch": (
        "REF-INT-01", Severity.WARNING,
        "the cited DOI belongs to a different paper. Check the DOI against the "
        "reference before anything else."),
    "suspected_fabricated": (
        "REF-INT-02", Severity.WARNING,
        "no index has this reference although several were searched. Check it by "
        "hand: it may be mistyped, unindexed, or not exist."),
    "unverifiable": (
        "REF-INT-03", Severity.INFO,
        "NOT CHECKED — not found in Crossref, DataCite or the JACoW proceedings. "
        "Common for reports, talks, strategy inputs, preprints and older papers; "
        "check by hand if in doubt."),
}


# ---------------------------------------------------------------------------
# Settings: one .env for both tools
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def cache_dir() -> Path:
    root = os.getenv("AIAGENT_CACHE_DIR", "").strip()
    return Path(root).expanduser() if root else Path.home() / ".cache" / "aiagent"


def formatter_config(*, offline: bool = False, style: HouseStyle | None = None,
                     llm: bool | None = None) -> AgentConfig:
    """Build the formatter's settings from the agent's .env.

    * ``CROSSREF_EMAIL`` becomes ``mailto`` (polite Crossref access);
    * both tools share one lookup cache under ``AIAGENT_CACHE_DIR``;
    * ``LLM_*`` settings drive the formatter's OpenAI-compatible client, so one
      local model (Ollama, LM Studio) serves both;
    * the conference house style sets dashes, apostrophes and "App."/"Appl.".
    """
    style = style or load_house_style()
    use_llm = _env_bool("LLM_ENABLED") if llm is None else llm
    base = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    lookups = not offline and not _env_bool("AIAGENT_OFFLINE")
    email = os.getenv("CROSSREF_EMAIL", "").strip()
    return AgentConfig(
        mailto=email if "@" in email else "",
        cache_path=cache_dir() / "lookups.sqlite",
        use_crossref=lookups, use_datacite=lookups, use_inspirehep=lookups,
        use_jacow_remote=lookups, use_refdb=lookups, use_ltwa=lookups,
        use_llm=use_llm,
        # Let authoritative values correct the author's, not only fill gaps.
        # Every correction is a decision for the editor with old -> new shown.
        prefer_authoritative=_env_bool("REFERENCE_CORRECTIONS", True),
        llm_provider="openai-compatible",
        llm_endpoint=f"{base}/chat/completions",
        llm_model=os.getenv("LLM_MODEL", "qwen3:14b"),
        curly_quotes=style.curly_quotes,
        page_range_dash=style.page_range_dash,
        label_apostrophe=style.label_apostrophe,
        applied_physics=style.applied_physics,
    )


_agents: dict[tuple, JacowAgent] = {}
_lock = threading.Lock()


def _agent(offline: bool, llm: bool | None) -> JacowAgent:
    style = load_house_style()
    key = (offline, llm, style)
    with _lock:
        if key not in _agents:
            _agents[key] = JacowAgent(formatter_config(offline=offline, style=style, llm=llm))
        return _agents[key]


_LOWER_WORD_RE = re.compile(r"(?<![\w./@-])([a-z][a-z\-]{2,})(?![\w./@-])")


def lowercase_evidence(body_text: str) -> set[str]:
    r"""Words the paper's own prose writes in lowercase.

    Extends the formatter's lexicon with this paper's vocabulary: if the
    author writes "cryomodule" in a sentence, it is an ordinary word here.
    """
    text = re.sub(r"(?<!\\)%[^\n]*", " ", body_text)
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    return {match.group(1) for match in _LOWER_WORD_RE.finditer(text)}


# ---------------------------------------------------------------------------
# Presentation-only changes
# ---------------------------------------------------------------------------

def _presentation_key(text: str) -> str:
    """*text* with every presentation-only difference normalised away."""
    t = text.strip()
    t = re.sub(r"https?://(?:dx\.)?doi\.org/", "doi:", t, flags=re.IGNORECASE)
    t = re.sub(r"\bdoi\s*:\s*", "doi:", t, flags=re.IGNORECASE)
    t = re.sub(r"\bet\.?\s*al\b\.?", "et al.", t, flags=re.IGNORECASE)
    t = re.sub(r",\s+and\s+", " and ", t)                  # serial comma
    t = re.sub(r"\b([A-Z]\.)\s+(?=[A-Z]\.)", r"\1", t)       # "H. P." = "H.P."
    t = t.translate(str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'",
                                   "\u2019": "'", "\u2013": "-", "\u2014": "-"}))
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t.rstrip(". ")


def presentation_only(before: str, after: str) -> bool:
    """True when *after* differs from *before* only in presentation."""
    return _presentation_key(before) == _presentation_key(after)


# ---------------------------------------------------------------------------
# LaTeX bodies
# ---------------------------------------------------------------------------

_LATEX_TO_PLAIN = (
    (re.compile(r"\\doi\{([^}]*)\}"), r"doi:\1"),
    (re.compile(r"\\url\{([^}]*)\}"), r"\1"),
    (re.compile(r"\\(?:emph|textit|textbf|textrm|NoCaseChange)\{([^{}]*)\}"), r"\1"),
    (re.compile(r"``"), "\u201c"), (re.compile(r"''"), "\u201d"),
    (re.compile(r"(?<!\\)~"), " "), (re.compile(r"---"), "\u2014"), (re.compile(r"--"), "\u2013"),
    (re.compile(r"\\([&%#_$])"), r"\1"),
    (re.compile(r"(?<!\\)[{}]"), ""),
)


def latex_to_plain(body: str) -> str:
    text = body
    for pattern, replacement in _LATEX_TO_PLAIN:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def plain_to_latex(text: str) -> str:
    """Formatted plain text back to LaTeX: DOIs as \\doi{…}, URLs as \\url{…}."""
    pieces: list[str] = []
    for token in re.split(r"(\bdoi:\S+|https?://\S+)", text):
        if token.lower().startswith("doi:"):
            doi = token[4:].rstrip(".,;")
            pieces.append(f"\\doi{{{doi}}}" + token[4 + len(doi):])
        elif token.lower().startswith("http"):
            url = token.rstrip(".,;")
            pieces.append(f"\\url{{{url}}}" + token[len(url):])
        else:
            pieces.append(re.sub(r"(?<!\\)([&%#_$])", r"\\\1", token)
                          .replace("\u2013", "--").replace("\u2014", "---")
                          .replace("\u201c", "``").replace("\u201d", "''"))
    return "".join(pieces)


# ---------------------------------------------------------------------------
# One reference
# ---------------------------------------------------------------------------

@dataclass
class ReferenceResult:
    """What the agent does with one reference."""

    raw: str
    after: str | None = None          # None: keep the author's text
    tier: Tier | None = None
    message: str = ""
    evidence_source: str = "local-rule"
    added_from: str = ""              # "Crossref" etc. when lookups added fields
    integrity: str = ""
    findings: list[Finding] = field(default_factory=list)
    # What check_rewrite was told it may accept (for audit and tests).
    declared: dict = field(default_factory=dict)
    # Values the lookups supplied, as given to the fine-tuned reference model.
    record: dict = field(default_factory=dict)


# Formatter stages whose values come from an authoritative source rather than
# the citation text.  Not 'identifier': that stage also records identifiers
# parsed from the citation itself; a merge after a lookup by the cited DOI is
# taken from the formatter's field log instead.
_LOOKUP_STAGES = frozenset({"search-cascade", "jacow-db", "refdb", "arxiv", "isbn",
                            "llm", "llm-journal"})
_REPLACED_RE = re.compile(r"^(\w+) replaced from authoritative record: (['\"])(.*?)\2 -> (['\"])(.*?)\4$")


@dataclass
class LookupChange:
    field: str
    new: str
    old: str = ""            # empty: the field was added, not corrected
    source: str = ""


def lookup_changes(result: dict) -> list[LookupChange]:
    """Every value an authoritative source added or corrected, with its source."""
    changes: dict[str, LookupChange] = {}
    for entry in result.get("field_log") or []:
        field_name, value = str(entry.get("field", "")), str(entry.get("value", ""))
        if field_name and value:
            source = str(entry.get("source", "")).split("/")[0].split(" (")[0]
            changes[field_name] = LookupChange(field_name, value, source=source)
    for entry in result.get("provenance_detail") or []:
        if entry.get("stage") in _LOOKUP_STAGES and entry.get("value") not in (None, "", []):
            field_name = str(entry.get("field"))
            value = entry["value"]
            value = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            if field_name not in changes:
                changes[field_name] = LookupChange(
                    field_name, value, source=_SOURCE_NAMES.get(entry["stage"], entry["stage"]))
    for flag in result.get("flags") or []:
        match = _REPLACED_RE.match(str(flag))
        if match and match.group(1) in changes:
            changes[match.group(1)].old = match.group(3)
    # Values that are also in the citation were confirmed, not added.
    return [c for c in changes.values() if c.new]


def _derived_values(result: dict) -> list[str]:
    return [c.new for c in lookup_changes(result)]


def _replaced_values(result: dict) -> list[str]:
    return [c.old for c in lookup_changes(result) if c.old]


def _changes_note(plain: str, result: dict) -> tuple[str, str]:
    """('DOI and pages added from Crossref; year corrected …', main source)."""
    added: dict[str, list[str]] = {}
    corrected: list[str] = []
    sources: list[str] = []
    folded = plain.lower()
    for change in lookup_changes(result):
        source = _SOURCE_NAMES.get(change.source.lower(), change.source) or "a lookup"
        if change.old:
            corrected.append(f"{change.field} corrected from {source} "
                             f"({change.old} \u2192 {change.new})")
        elif change.new.lower() not in folded:
            added.setdefault(source, []).append("DOI" if change.field == "doi" else change.field)
        else:
            continue
        if source not in sources:
            sources.append(source)
    parts = [f"{' and '.join(fields)} added from {source}" for source, fields in added.items()]
    return "; ".join(parts + corrected), (sources[0] if sources else "")


def _journal_substitutions(raw: str, result: dict) -> list[tuple[str, str]]:
    """Declare the ISO 4 abbreviation of the journal name, which JACoW requires.

    "Review of Scientific Instruments" -> "Rev. Sci. Instrum." is four
    "dropped" words to the damage check unless it is declared.
    """
    journal = str((result.get("rec") or {}).get("journal") or "").strip()
    if not journal:
        return []
    pairs = []
    for segment in re.split(r"[,\u201d\"]", raw):
        segment = segment.strip()
        # "Nat. Photon. 4" in the compact style: the volume follows the name
        # with no comma, and "A429" (volume with section letter) likewise.
        candidates = {segment.rstrip("."), segment,
                      re.sub(r"\s+[A-Z]?\d[\w\s()]*$", "", segment).strip()}
        for name in candidates:
            if not name or name == journal or name.rstrip(".") == journal.rstrip("."):
                continue
            try:
                if normalize_journal(name) == journal:
                    pairs.append((name, journal))
                    break
            except Exception:  # noqa: BLE001
                continue
    return pairs


_RAW_QUOTE_RE = re.compile(r"[\u201c\u201e\"]")
_URL_ONLY_RE = re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE)


_DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+?)(?=[\s,;]|\.?\s*$)", re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(r"\bDOI\s*:\s*(?=10\.\d{4,9}/)", re.IGNORECASE)


def _try_reference_model(raw: str, outcome: ReferenceResult, *, label: str,
                         llm: bool | None) -> None:
    """Ask the fine-tuned reference model (``REFERENCE_MODEL``), validate, offer.

    Off unless ``REFERENCE_MODEL`` names a served model.  In the default
    ``fallback`` mode it is asked only when the rule-based rewrite was not
    offered; ``REFERENCE_MODEL_MODE=prefer`` asks it for every reference and
    uses its answer whenever that passes validation.  Its answer passes the
    same damage check as any rewrite, with only the lookups' values declared,
    and is always a decision for the editor.
    """
    model = os.getenv("REFERENCE_MODEL", "").strip()
    if not model or llm is False:
        return
    mode = os.getenv("REFERENCE_MODEL_MODE", "fallback").strip().lower()
    if outcome.after is not None and mode != "prefer":
        return
    from src.finetune.prompt import messages
    from src.llm import client
    plain = raw.strip()
    try:
        msgs = messages(plain, outcome.record or None)
        answer = client.chat(msgs[0]["content"], msgs[1]["content"], model=model,
                             temperature=0.0, timeout=60).strip()
    except Exception:  # noqa: BLE001 — a model failure leaves the rule-based result
        return
    answer = re.sub(r"\s+", " ", answer.strip().strip("`")).strip()
    if not answer or answer == plain or answer == outcome.after:
        return
    verdict = check_rewrite(plain, answer,
                            allowed_additions=list(outcome.record.values()),
                            allowed_substitutions=_journal_substitutions(
                                plain, {"rec": {"journal": _abbrev_in(answer)}}))
    if not verdict.ok:
        return
    outcome.after = answer
    outcome.tier = Tier.SUGGEST
    outcome.message = (f"{label} reformatted to JACoW Annex B style by the fine-tuned "
                       f"reference model ({model}); verified to preserve every number, "
                       "DOI, word and name.")
    outcome.findings = [f for f in outcome.findings if f.check_id != "FMT-REF-03"]


def _abbrev_in(answer: str) -> str:
    """The journal abbreviation in a formatted reference ("…”, Phys. Rev. Lett., vol.")."""
    m = re.search(r"[\u201d\"],\s*([A-Z][\w.&\s:-]+?\.),\s*(?:vol\.|no\.|pp?\.|\d)", answer)
    return m.group(1).strip() if m else ""


def doi_form_only(text: str) -> str:
    """*text* with every DOI written as ``doi:10.…`` and nothing else changed.

    "https://doi.org/10.23731/CYRM-2099-001" and "DOI: 10.…" become
    "doi:10.23731/CYRM-2099-001".  Annex B's form for a DOI; applied even
    when the rest of the reference is left as written.
    """
    text = _DOI_URL_RE.sub(lambda m: f"doi:{m.group(1)}", text)
    return _DOI_PREFIX_RE.sub("doi:", text)


def screen_reference(raw: str, *, label: str = "", line: int | None = None,
                     offline: bool = False, llm: bool | None = None) -> ReferenceResult:
    """Format, look up and verify one reference; decide what the agent does.

    When no full rewrite is offered — rejected by the damage check, or nothing
    to reformat — the DOI is still put in the ``doi:…`` form on its own, as a
    presentation fix: it changes no information.
    """
    outcome = _screen_reference(raw, label=label, line=line, offline=offline, llm=llm)
    _try_reference_model(raw, outcome, label=label or "Reference", llm=llm)
    if outcome.after is None:
        plain = raw.strip()
        fixed = doi_form_only(plain)
        if fixed != plain:
            outcome.after = fixed
            outcome.tier = Tier.AUTO
            outcome.message = (f"{label or 'Reference'}: DOI written in the JACoW form "
                               "doi:…; the rest of the reference is unchanged.")
    return outcome


def _screen_reference(raw: str, *, label: str = "", line: int | None = None,
                     offline: bool = False, llm: bool | None = None) -> ReferenceResult:
    """Format, look up and verify one reference; decide what the agent does."""
    label = label or "Reference"
    outcome = ReferenceResult(raw=raw)
    plain = raw.strip()
    if not plain:
        return outcome

    try:
        result = _agent(offline, llm).process_record(plain)
    except Exception as exc:  # noqa: BLE001 — never let one reference stop a paper
        outcome.findings.append(Finding(
            check_id="FMT-REF-03", severity=Severity.INFO, line=line,
            message=(f"{label}: NOT CHECKED — the reference could not be processed "
                     f"({type(exc).__name__}); left exactly as submitted."),
            original=plain[:240]))
        return outcome

    integrity = (result.get("integrity") or {}).get("verdict", "")
    outcome.integrity = integrity
    outcome.record = {c.field: c.new for c in lookup_changes(result)}
    # With lookups switched off every reference is "unverifiable"; the run's
    # lookup status already says so once, so it is not repeated per reference.
    lookups_ran = not (offline or _env_bool("AIAGENT_OFFLINE"))
    if integrity in _INTEGRITY_FINDINGS and (integrity != "unverifiable" or lookups_ran):
        check_id, severity, text = _INTEGRITY_FINDINGS[integrity]
        if integrity == "unverifiable" and _URL_ONLY_RE.match(plain):
            # A bare web address has nothing an index could confirm.
            text = ""
        elif integrity == "unverifiable" and not _RAW_QUOTE_RE.search(plain) and re.search(r"\b\d+\s*,\s*\d+", plain):
            # "Journal 99, 099999 (2011)": the usual reason is the missing
            # title, not the age or kind of the publication.
            text = ("NOT CHECKED — no index match for this journal, volume and page, and "
                    "the citation has no title to search on. Check the reference by hand; "
                    "a DOI from the publisher's page can be added.")
        if text:
            outcome.findings.append(Finding(
                check_id=check_id, severity=severity, line=line,
                message=f"{label}: {text}", original=plain[:240]))

    formatted = (result.get("formatted") or "").replace("\n", " ").strip()
    formatted = re.sub(r"\s+", " ", formatted)
    flags = [str(f) for f in result.get("flags") or []]
    if not formatted or formatted == plain:
        return outcome

    declared = {"allowed_additions": _derived_values(result),
                "allowed_removals": _replaced_values(result),
                "allowed_substitutions": _journal_substitutions(plain, result)}
    outcome.declared = declared
    verdict = check_rewrite(plain, formatted, **declared)
    if not verdict.ok or any("defaulted" in f for f in flags):
        reason = verdict.reason if not verdict.ok else "a value would have been guessed"
        outcome.findings.append(Finding(
            check_id="FMT-REF-03", severity=Severity.INFO, line=line,
            message=(f"{label}: a JACoW-style rewrite was computed but rejected because "
                     f"it {reason}. The reference is unchanged — check it by hand if "
                     "the formatting looks wrong."),
            original=plain[:240]))
        return outcome

    # The formatter leaves capitalised words it cannot classify as written.
    # When a local model is available, it is asked about exactly those words —
    # the same labels-only, unanimous-samples rule as for .bib titles — and the
    # result must pass the damage check again.  A model-assisted change is
    # always a decision for the editor, never automatic.
    lowered: list[str] = []
    candidate, words, still_unsure = _model_title_casing(formatted, llm)
    if words:
        recheck = check_rewrite(
            plain, candidate, allowed_additions=_derived_values(result),
            allowed_removals=_replaced_values(result),
            allowed_substitutions=_journal_substitutions(plain, result)
            + [(w, w.lower()) for w in words])
        if recheck.ok:
            formatted, lowered = candidate, words

    if formatted == plain:
        return outcome

    changes_note, main_source = _changes_note(plain, result)
    added_from = main_source
    outcome.after = formatted
    outcome.added_from = added_from
    if changes_note:
        # Added or corrected from an authoritative source: always the
        # editor's decision, with every value and its source on the card.
        outcome.tier = Tier.SUGGEST
        outcome.evidence_source = "crossref" if "Crossref" in changes_note else "jacow-refdb"
        outcome.message = f"{label} reformatted to JACoW Annex B style; {changes_note}."
    elif presentation_only(plain, formatted) and not lowered:
        outcome.tier = Tier.AUTO
        outcome.message = f"{label}: presentation corrected (DOI form, punctuation)."
    else:
        outcome.tier = Tier.SUGGEST
        outcome.message = (f"{label} reformatted to JACoW Annex B style. Verified to "
                           "preserve every number, DOI, word and name in the original.")
    if lowered:
        outcome.message += (" Lowercased on the local model's unanimous advice: "
                            + ", ".join(f"'{w}'" for w in lowered) + ".")
    return outcome


_QUOTED_TITLE_RE = re.compile(r"\u201c([^\u201d]+)\u201d")


def _model_title_casing(formatted: str, llm: bool | None
                        ) -> tuple[str, list[str], tuple[str, ...] | None]:
    """Ask the local model about the title words sentence case left as written.

    Returns the candidate text, the words the model lowercased, and the words
    still undecided after asking it — ``None`` when the model was not asked.
    """
    if llm is False:
        return formatted, [], None
    from src.llm import classify

    if not classify.available():
        return formatted, [], None
    match = _QUOTED_TITLE_RE.search(formatted)
    if not match:
        return formatted, [], None
    title = match.group(1)
    casing = classify.resolve_title_casing(title)
    if casing.text == title:
        return formatted, [], tuple(casing.unsure)
    words = [old.strip("()[],.;:!?") for old, new in zip(title.split(), casing.text.split())
             if old != new and old.lower() == new]
    candidate = formatted[:match.start(1)] + casing.text + formatted[match.end(1):]
    return candidate, words, tuple(casing.unsure)


