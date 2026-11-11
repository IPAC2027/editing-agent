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


# ---------------------------------------------------------------------------
# arXiv: cached, and rested when it stops answering
# ---------------------------------------------------------------------------
#
# The formatter asks arXiv about every reference Crossref and DataCite could
# not confirm. arXiv allows one request every three seconds, and when it is
# busy each request ends in rate-limit waits and a 10-second timeout, three
# times over: preparing one paper took many minutes, mostly waiting on arXiv
# ("HTTP 429 rate-limited by export.arxiv.org", "The read operation timed
# out"). Its answers were not cached either, so preparing again asked again.
#
# So, without changing the formatter: arXiv's answers are kept in the same
# lookup cache, and after a failure arXiv is left alone for a while. A request
# skipped that way is recorded as a network failure, exactly as a timeout is,
# so a reference only arXiv could have confirmed is reported "not checked",
# never as possibly fabricated.

ARXIV_REST_SECONDS = 15 * 60
_ARXIV_HOSTS = {"export.arxiv.org", "arxiv.org"}
_arxiv = {"resting_until": 0.0, "cache": None, "installed": False}
_arxiv_lock = threading.Lock()


def _arxiv_cache():
    from jacow_formatter.cache import SqliteCache

    with _arxiv_lock:
        if _arxiv["cache"] is None:
            try:
                _arxiv["cache"] = SqliteCache(cache_dir() / "lookups.sqlite")
            except Exception:  # noqa: BLE001 — no cache is slower, not wrong
                _arxiv["cache"] = False
        return _arxiv["cache"] or None


def _guarded_get_raw(original):
    import time
    import urllib.parse

    from jacow_formatter import net

    def get_raw(url: str, *args, **kwargs) -> bytes:
        if urllib.parse.urlparse(url).netloc not in _ARXIV_HOSTS:
            return original(url, *args, **kwargs)
        cache = _arxiv_cache()
        key = "aiagent-arxiv:" + url
        hit = cache.get(key) if cache else None
        if hit is not None:
            return hit.get("body", "").encode("utf-8")
        if time.monotonic() < _arxiv["resting_until"]:
            net._record_net_error(url, "arXiv skipped: not answering")
            return b""
        body = original(url, *args, **kwargs)
        if body:
            if cache:
                cache.set(key, {"body": body.decode("utf-8", "replace")},
                          ttl=30 * 86_400)
            return body
        with _arxiv_lock:
            first = time.monotonic() >= _arxiv["resting_until"]
            _arxiv["resting_until"] = time.monotonic() + ARXIV_REST_SECONDS
        if first:
            print(f"  arXiv is not answering (rate-limited or slow): arXiv searches are "
                  f"skipped for the next {ARXIV_REST_SECONDS // 60} minutes. References only "
                  "arXiv could confirm are marked 'not checked'.", flush=True)
        return b""

    get_raw.__wrapped__ = original
    return get_raw


def _install_arxiv_guard() -> None:
    from jacow_formatter import agent as formatter_agent
    from jacow_formatter import sources as formatter_sources

    with _arxiv_lock:
        if _arxiv["installed"]:
            return
        _arxiv["installed"] = True
    for module in (formatter_sources, formatter_agent):
        current = getattr(module, "_http_get_raw", None)
        if current is not None and not hasattr(current, "__wrapped__"):
            module._http_get_raw = _guarded_get_raw(current)


_install_arxiv_guard()


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
    # Whatever follows the end of the bibliography is not the reference's.
    (re.compile(r"\\end\s*\{thebibliography\}.*$|\\endthebibliography\b.*$", re.DOTALL), ""),
    # Quote commands (often written with no space: \textquotedblleft{}Title).
    (re.compile(r"\\textquotedblleft(?:\{\})?\s*"), "\u201c"),
    (re.compile(r"\\textquotedblright(?:\{\})?"), "\u201d"),
    (re.compile(r"\\textquoteleft(?:\{\})?\s*"), "\u2018"),
    (re.compile(r"\\textquoteright(?:\{\})?"), "\u2019"),
    (re.compile(r"\\enquote\*?\{([^{}]*)\}"), "\u201c\\1\u201d"),
    (re.compile(r"\\doi\{([^}]*)\}"), r"doi:\1"),
    (re.compile(r"\\url\{([^}]*)\}"), r"\1"),
    (re.compile(r"\\href\{[^}]*\}\{([^{}]*)\}"), r"\1"),
    (re.compile(r"\\(?:emph|textit|textbf|textrm|textsc|textsl|textup|textnormal|mbox|NoCaseChange)"
                r"\{([^{}]*)\}"), r"\1"),
    # Font switches: {\it Title}, \bf 17.
    (re.compile(r"\\(?:it|bf|em|sl|sc|rm|tt|itshape|bfseries|upshape|normalfont)\b\s*"), ""),
    (re.compile(r"\\newblock\b\s*"), ""),
    (re.compile(r"\\\\(?:\[[^\]]*\])?"), " "),           # \\ line breaks
    (re.compile(r"\\[ ,;:!/]"), " "),                        # \  \, \; spaces
    (re.compile(r"``"), "\u201c"), (re.compile(r"''"), "\u201d"),
    (re.compile(r"(?<!\\)~"), " "), (re.compile(r"---"), "\u2014"), (re.compile(r"--"), "\u2013"),
    (re.compile(r"\\([&%#_$])"), r"\1"),
    (re.compile(r"(?<!\\)[{}]"), ""),
)

# Accents: \"o, \'{e}, \c{c}, \v{s} -> ö, é, ç, š.
_ACCENT_MARKS = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
                 "=": "\u0304", ".": "\u0307", "c": "\u0327", "v": "\u030c", "u": "\u0306",
                 "H": "\u030b", "r": "\u030a", "k": "\u0328"}
_ACCENT_RE = re.compile(r"\{?\\(['`^\"~=.]|[cvuHrk](?=[\s{]))\s*\{?\\?([A-Za-z])\}?\}?")
_LETTERS = {"\\ss": "\u00df", "\\o": "\u00f8", "\\O": "\u00d8", "\\aa": "\u00e5",
            "\\AA": "\u00c5", "\\ae": "\u00e6", "\\AE": "\u00c6", "\\l": "\u0142",
            "\\L": "\u0141", "\\i": "i"}
_LETTER_RE = re.compile(r"\{?(\\(?:ss|aa|AA|ae|AE|o|O|l|L|i))\b\}?")


def _accents(text: str) -> str:
    import unicodedata

    text = _ACCENT_RE.sub(lambda m: unicodedata.normalize(
        "NFC", m.group(2) + _ACCENT_MARKS[m.group(1)]), text)
    return _LETTER_RE.sub(lambda m: _LETTERS[m.group(1)], text)


_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
          "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "kappa": "κ",
          "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
          "sigma": "σ", "tau": "τ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
          "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
          "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω"}
_GREEK_RE = re.compile(r"\$\s*\\(" + "|".join(_GREEK) + r")\s*\$")


def latex_to_plain(body: str) -> str:
    text = _GREEK_RE.sub(lambda m: _GREEK[m.group(1)], _accents(body))
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
    # What is still wrong after the rules (and the local model), described for
    # the editor: src.refcheck.Difficulty.view(), or None when nothing is.
    difficulty: dict | None = None
    evidence_detail: str = ""


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
    """('DOI and pages added from Crossref; year corrected …', main source).

    Only values the reformatted reference shows are named: a publisher or an
    ISSN the lookup found but the reference does not print is not news.
    """
    added: dict[str, list[str]] = {}
    corrected: list[str] = []
    sources: list[str] = []
    folded = plain.lower()
    shown = re.sub(r"\s+", " ", str(result.get("formatted") or "")).lower()
    for change in lookup_changes(result):
        value = change.new.lower().rstrip(".")
        if shown and value and value not in shown.replace("\u2013", "-") \
                and value.replace("\u2013", "-") not in shown.replace("\u2013", "-"):
            continue
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
            # A journal's name never hides a number ("KEK Preprint 2005-109" is
            # not "KEK Preprint" abbreviated: the report number would be lost).
            if re.findall(r"\d+", name) != re.findall(r"\d+", journal):
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
    if outcome.after is not None and mode != "prefer" and outcome.difficulty is None:
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
    import src.refcheck as refcheck
    current = outcome.after or plain
    if outcome.after is not None and len(refcheck.errors(refcheck.lint(answer))) > \
            len(refcheck.errors(refcheck.lint(current))):
        return                           # no better than what the rules already offer
    outcome.after = answer
    outcome.difficulty = None
    outcome.tier = Tier.SUGGEST
    outcome.message = (f"{label} reformatted to JACoW Annex B style by the fine-tuned "
                       f"reference model ({model}); verified to preserve every number, "
                       "DOI, word and name.")
    outcome.findings = [f for f in outcome.findings
                        if f.check_id not in ("FMT-REF-03", "REF-CHECK-01")]
    left = refcheck.errors(refcheck.lint(answer))
    if left:
        d = refcheck.describe(answer, left, label=label)
        outcome.difficulty = d.view()
        outcome.findings.append(Finding(
            check_id="REF-CHECK-01", severity=Severity.INFO,
            message=f"{label} still breaks JACoW rules (difficulty: {d.level}).\n"
                    + d.for_editor(), original=answer[:240]))


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
    """The formatter's answer, then the JACoW rules and the local model (src.refcheck)."""
    outcome, result = _formatter_screen(raw, label=label, line=line, offline=offline, llm=llm)
    if not raw.strip():
        return outcome
    try:
        return _with_rules(outcome, result or {}, label=label or "Reference", line=line,
                           llm=llm, offline=offline)
    except Exception:  # noqa: BLE001 — the rules never stop a paper
        import logging
        logging.getLogger(__name__).exception("reference rules failed on %r", raw[:80])
        return outcome


def _facts(result: dict) -> dict:
    """Values a lookup verified: ``{field: (value, source)}`` (no model's guesses)."""
    facts: dict[str, tuple[str, str]] = {}
    for change in lookup_changes(result):
        source = _SOURCE_NAMES.get(change.source.lower(), change.source)
        if not source or "language model" in source or change.source.lower().startswith("llm"):
            continue
        facts[change.field] = (change.new, source)
    return facts


def _model_wanted(llm: bool | None) -> bool:
    if llm is False or os.getenv("REFERENCE_FIX", "on").strip().lower() in ("off", "0", "no"):
        return False
    from src.llm import client
    return client.is_enabled()


def _doi_facts(plain: str, kind: str, facts: dict) -> object | None:
    """The DOI's verdict (src.refcheck.doi) folded into the facts the rules use.

    A DOI the formatter's lookup supplied is kept only if it passes the same
    strict check (the same title, author, year, journal, volume and page).
    """
    from src.refcheck import doi as doi_module

    try:
        report = doi_module.check(plain, kind)
    except Exception:  # noqa: BLE001 — no verdict: nothing changes
        return None
    if report.status == "found":
        facts["doi"] = (report.doi, report.source)
    elif report.status == "corrected":
        facts["doi_fix"] = (report.written, report.doi, report.source, report.reason)
        facts.pop("doi", None)
    elif report.status in ("wrong", "unresolved"):
        facts["doi_problem"] = (report.written, report.reason)
        facts.pop("doi", None)
    elif report.status == "possible":
        facts["doi_possible"] = (report.written, report.doi, report.source, report.reason)
        facts.pop("doi", None)
    elif report.status == "none" and facts.get("doi"):
        if not _doi_fits(plain, kind, facts["doi"][0]):
            facts.pop("doi", None)
    return report


def _doi_fits(plain: str, kind: str, doi: str) -> bool:
    from src.refcheck import doi as doi_module

    work = doi_module.lookup(doi)
    if not isinstance(work, doi_module.Work) or not work.title:
        return False
    return doi_module.match(doi_module.fields_of(plain, kind), work)[0]


def _with_rules(outcome: ReferenceResult, result: dict, *, label: str, line: int | None,
                llm: bool | None, offline: bool = False) -> ReferenceResult:
    """Fix what the JACoW rules can, have the model fix what they describe, report the rest.

    The formatter's rewrite (already in *outcome*) and the rules' (and model's)
    version compete: the one the rules find fewer problems in wins, the rules'
    on a tie, because it changes only what is wrong.
    """
    import src.refcheck as refcheck
    from src.refcheck.rules import FIXED

    plain = outcome.raw.strip()
    facts = _facts(result)
    report = None
    if not (offline or _env_bool("AIAGENT_OFFLINE")):
        report = _doi_facts(plain, refcheck.kind_of(plain, str(result.get("type") or "")), facts)
        if report is not None and report.status in ("corrected", "wrong") or \
                (report is not None and report.status == "possible" and report.written):
            # The verdict below says which DOI is right; the formatter's
            # "belongs to a different paper" would only repeat it.
            outcome.findings = [f for f in outcome.findings if f.check_id != "REF-INT-01"]
        if report is not None and report.status in ("ok", "found", "corrected"):
            # A registry knows the reference: "not found anywhere" is not so.
            outcome.findings = [f for f in outcome.findings if f.check_id != "REF-INT-03"]
    checked = refcheck.check_reference(plain, kind=str(result.get("type") or ""), facts=facts,
                                       label=label, llm=_model_wanted(llm))
    kind = checked.kind

    def problems(text: str) -> list:
        return refcheck.errors(refcheck.lint(text, kind=kind, facts=facts))

    formatter_text = outcome.after
    ours = checked.text if checked.changed else None
    if formatter_text is not None:
        # The rules on top of the formatter's rewrite, checked against the author's text.
        polished = refcheck.fix(formatter_text, kind=kind, facts=facts)
        if polished.changed:
            declared = dict(outcome.declared or {})
            verdict = check_rewrite(
                plain, polished.text,
                allowed_substitutions=list(declared.get("allowed_substitutions", []))
                + polished.declared["allowed_substitutions"],
                allowed_additions=list(declared.get("allowed_additions", []))
                + polished.declared["allowed_additions"],
                allowed_removals=list(declared.get("allowed_removals", []))
                + polished.declared["allowed_removals"])
            if verdict.ok:
                formatter_text = polished.text
                if not polished.presentation_only:
                    outcome.tier = Tier.SUGGEST
                outcome.after = formatter_text
    # The formatter's rewrite passed the damage check and may carry verified
    # values and layouts the rules cannot make (a book's): it wins unless the
    # rules find it worse. A sign that a reference was garbled (names in the
    # title, LaTeX left over, a word twice) weighs more than a missing comma.
    def score(text: str) -> int:
        return sum(5 if i.code in _GARBLED else 1 for i in problems(text))

    if formatter_text is not None and report is not None:
        # A DOI the formatter added must pass the strict check too.
        added = {d.lower() for d in re.findall(r"10\.\d{4,9}/[^\s\"<>]+", formatter_text)} - \
            {d.lower() for d in re.findall(r"10\.\d{4,9}/[^\s\"<>]+", plain)}
        verified = {facts["doi"][0].lower()} if facts.get("doi") else set()
        if facts.get("doi_fix"):
            verified.add(facts["doi_fix"][1].lower())
        if any(d.rstrip(".,;)") not in verified and
               not _doi_fits(plain, checked.kind, d.rstrip(".,;)")) for d in added):
            formatter_text = None
            if ours is None:
                outcome.after, outcome.tier = None, None
    if formatter_text is not None and not _keeps_links(plain, formatter_text):
        formatter_text = None            # it lost a DOI or a web address the author gave
        if outcome.after is not None and ours is None:
            outcome.after, outcome.tier = None, None
    if formatter_text is not None and (ours is None or score(formatter_text) <= score(ours)):
        final = formatter_text
    elif ours is not None:
        final = ours
        outcome.after = ours
        done = list(dict.fromkeys(
            (i.message.rstrip(".") if i.code in ("REF-DOI-WRONG", "REF-DOI-POSSIBLE") else
             FIXED.get(i.code, i.code) + (f" from {i.fix.source}" if i.fix.source else ""))
            for i in checked.fixed.applied if i.code != "REF-PUNCT"))
        sources = checked.fixed.sources
        if checked.repair is not None:
            outcome.tier = Tier.SUGGEST
            outcome.evidence_source = "llm"
            fixed_by_model = list(dict.fromkeys(FIXED.get(c, c) for c in checked.repair.fixed))
            outcome.message = (
                f"{label} corrected: " + "; ".join(done + fixed_by_model) + ". The JACoW rules "
                f"fixed what they could; the local model ({checked.repair.model}) fixed "
                + (", ".join(fixed_by_model) or "the rest")
                + ", and its answer was checked again by the rules and the damage check.")
            outcome.evidence_detail = (f"JACoW rules, then {checked.repair.model} "
                                       f"({'; '.join(checked.repair.how)}), checked by "
                                       "the rules and check_rewrite")
        else:
            automatic = checked.fixed.presentation_only and not sources
            outcome.tier = Tier.AUTO if automatic else Tier.SUGGEST
            outcome.message = (f"{label} corrected by the JACoW reference rules: "
                               + ("; ".join(done) or "punctuation") + ".")
            outcome.evidence_source = ("jacow-refdb" if any("jacow" in s.lower() or
                                                            "refs." in s for s in sources)
                                       else "crossref" if sources else "local-rule")
            outcome.added_from = ", ".join(sources)
            outcome.evidence_detail = ("JACoW reference rules, each fix checked by "
                                       "check_rewrite")
        # The formatter's rejected rewrite no longer matters: this one was not.
        outcome.findings = [f for f in outcome.findings if not _rejection(f)]
    else:
        final = plain

    left = problems(final)
    description = refcheck.describe(final, left, kind=kind, facts=refcheck.model_facts(facts),
                                    label=label)
    if description is not None:
        outcome.difficulty = description.view()
        outcome.difficulty["model_tried"] = bool(checked.repair or checked.model_refused)
        serious = any(i.severity == refcheck.ERROR for i in left)
        tried = (" The local model was asked and its answers were refused."
                 if checked.model_refused and not checked.repair else "")
        outcome.findings.append(Finding(
            check_id="REF-CHECK-01",
            severity=Severity.WARNING if serious else Severity.INFO, line=line,
            message=f"{label} still breaks JACoW rules (difficulty: {description.level})."
                    f"{tried}\n{description.for_editor()}",
            original=final[:240]))
    return outcome


#: Problems that mean a reference has been garbled, not merely mis-punctuated.
_GARBLED = frozenset({"REF-TITLE-NAMES", "REF-LATEX", "REF-REPEATED", "REF-AUTH-FORM"})


def _keeps_links(before: str, after: str) -> bool:
    """Every DOI and web address of *before* is still in *after* (a URL may become its DOI)."""
    low = after.lower()
    for doi in re.findall(r"10\.\d{4,9}/[^\s\"<>]+", before):
        if doi.rstrip(".,;)").lower() not in low:
            return False
    for url in re.findall(r"https?://\S+", before):
        url = url.rstrip(".,;)")
        inner = re.search(r"10\.\d{4,9}/\S+", url)
        if url.lower() not in low and not (inner and inner.group(0).lower() in low) \
                and not re.search(r"(?:accelconf|jacow)", url, re.I):
            return False
    return True


def _rejection(finding: Finding) -> bool:
    """The formatter's 'a rewrite was computed but rejected' note."""
    return finding.check_id == "FMT-REF-03" and "rejected" in finding.message


def _formatter_screen(raw: str, *, label: str = "", line: int | None = None,
                      offline: bool = False, llm: bool | None = None
                      ) -> tuple[ReferenceResult, dict | None]:
    """Format, look up and verify one reference; decide what the agent does."""
    label = label or "Reference"
    outcome = ReferenceResult(raw=raw)
    plain = raw.strip()
    if not plain:
        return outcome, None

    try:
        result = _agent(offline, llm).process_record(plain)
    except Exception as exc:  # noqa: BLE001 — never let one reference stop a paper
        outcome.findings.append(Finding(
            check_id="FMT-REF-03", severity=Severity.INFO, line=line,
            message=(f"{label}: NOT CHECKED — the reference could not be processed "
                     f"({type(exc).__name__}); left exactly as submitted."),
            original=plain[:240]))
        return outcome, None

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
        return outcome, result

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
        return outcome, result

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
        return outcome, result

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
    return outcome, result


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


