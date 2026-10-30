"""The only sanctioned uses of a language model in this codebase.

The rule, stated once
--------------------
**A model may classify, segment, or verify. It may never author a
bibliographic fact.**

A DOI, a year, a volume, a page range, a venue: these are the fields an editor
cannot check at a glance, which makes a plausible wrong value worse than a
blank one. They come from Crossref, DataCite or refs.jacow.org, and they are
verified before they are shown. Two prompt templates that asked a model to
supply them (``doi_lookup_prompt``, ``missing_metadata_prompt``) have been
removed rather than merely discouraged.

What is left is where a model is genuinely better than the alternative, and
where its answer is **mechanically checkable**:

:func:`classify_title_words`
    Is "Poincaré" a proper noun? A hand-maintained whitelist cannot answer
    this — the set of surnames, facilities, codes and instruments in
    accelerator physics is open-ended — and this is the one place where the
    deterministic path is structurally unable to do the job. The model returns
    one label per token; a response with the wrong number of labels, or any
    token it does not recognise, is rejected.

Reference segmentation and line-break hyphens are the reference formatter's
job (``jacow_formatter``), under the same verbatim rule: the model may point
at spans of the citation, never supply them.  The agent's own copies of
reference-type classification and segmentation were removed when the
formatter became the single reference engine.

:func:`adjudicate_finding`
    Ask the model to *suppress* a deterministic finding it judges wrong. Used
    only to hide findings, never to add them: a wrong suppression costs the
    editor nothing they did not already have, while a wrong addition costs them
    a wild-goose chase.

Three practices that matter more with a 7–8B local model than a hosted one, and
are enforced here rather than left to the prompt:

* **Constrained decoding.** JSON mode is requested, so a malformed response is
  a parse failure rather than something to salvage.
* **Self-consistency.** Every classification is sampled three times and must be
  unanimous. Disagreement is the cheapest abstention signal available, and
  small models disagree with themselves far more than large ones.
* **Abstention is a first-class answer.** ``UNSURE`` propagates all the way to
  the report, where it becomes a flag for a human instead of an edit.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from enum import Enum

from src.lookup_status import STATUS

logger = logging.getLogger(__name__)

#: How many samples must agree before a classification is accepted.
SAMPLES = int(os.environ.get("LLM_SAMPLES", "3"))


class WordLabel(str, Enum):
    KEEP = "KEEP"      # a proper noun or acronym: leave the capital alone
    LOWER = "LOWER"    # an ordinary word: safe to lowercase
    UNSURE = "UNSURE"  # do not decide — escalate to the editor


class Verdict(str, Enum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    UNSURE = "UNSURE"


_SYSTEM = (
    "You are a classification component inside a deterministic editorial tool for "
    "JACoW/IPAC accelerator-physics proceedings. You return only the requested "
    "labels, as JSON. You never invent bibliographic data — no DOIs, years, "
    "volumes, page numbers or venues — and you answer UNSURE whenever you are not "
    "confident. UNSURE is a correct and expected answer; a confident wrong answer "
    "costs an editor more time than an abstention."
)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def available() -> bool:
    from src.llm import client

    return client.is_enabled()


def _sample_temperature() -> float:
    """The temperature the repeated samples are drawn at.

    Unanimity across three samples is only evidence of confidence if the
    samples can actually differ.  Drawn at temperature 0 a local model returns
    the same tokens three times, so the check degenerates into "did the server
    answer three times" — it catches a timeout or malformed JSON and nothing
    else.  A small but non-zero temperature is what makes a wobbly
    classification disagree with itself and therefore abstain.

    One sample is a different case: there is nothing to compare it with, so it
    is drawn greedily.  ``LLM_TEMPERATURE`` overrides either.
    """
    raw = os.environ.get("LLM_TEMPERATURE")
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 0.0 if SAMPLES <= 1 else 0.3


def _ask_json(user: str, *, temperature: float | None = None) -> dict | None:
    """One JSON-constrained completion, or ``None`` on any failure."""
    if temperature is None:
        temperature = _sample_temperature()
    from src.llm import client

    with STATUS.attempt("llm") as outcome:
        try:
            raw = client.chat(_SYSTEM, user, json_mode=True, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return None
        outcome.succeeded()

    text = (raw or "").strip()
    # Tolerate a fenced block, but nothing looser: anything else is a failure.
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("model returned non-JSON: %r", text[:200])
        return None
    return parsed if isinstance(parsed, dict) else None


def _unanimous(samples: list, *, minimum: int | None = None):
    """The value all samples agree on, or ``None``.

    Unanimity, not majority: two votes out of three is exactly the situation
    where a small model is guessing.
    """
    votes = [s for s in samples if s is not None]
    needed = minimum or SAMPLES
    if len(votes) < needed:
        return None
    counts = Counter(json.dumps(v, sort_keys=True) for v in votes)
    value, count = counts.most_common(1)[0]
    return json.loads(value) if count == len(votes) else None


# ---------------------------------------------------------------------------
# 1. Title-word classification
# ---------------------------------------------------------------------------

def classify_title_words(title: str, words: list[str]) -> dict[str, WordLabel]:
    """Label each of *words* KEEP / LOWER / UNSURE in the context of *title*.

    *words* are the tokens the deterministic caser could not classify, so the
    model is only ever asked about the residue — never about the whole title,
    and never for rewritten text.  Every label is applied by
    :func:`jacow_formatter.sent_case_report`'s caller, in code; the model's
    output is data.

    Any response that does not label exactly the requested words is discarded,
    and everything falls back to UNSURE.
    """
    if not words or not available():
        return {word: WordLabel.UNSURE for word in words}

    listed = json.dumps(words, ensure_ascii=False)
    user = (
        "JACoW reference titles use sentence case: ordinary words are lowercased, "
        "proper nouns and acronyms keep their capitals.\n\n"
        f"Title: {title}\n\n"
        f"Classify each of these words from that title: {listed}\n\n"
        'Reply with JSON: {"labels": {"<word>": "KEEP"|"LOWER"|"UNSURE"}}\n'
        "KEEP  — a proper noun, a person, a place, a facility, a project, a code "
        "name, a trademark, or an acronym.\n"
        "LOWER — an ordinary word of the language.\n"
        "UNSURE — you cannot tell. Prefer UNSURE over guessing.\n"
        "Label every listed word and no others. Do not return any other text."
    )

    samples = [_ask_json(user) for _ in range(SAMPLES)]
    agreed = _unanimous([
        _normalise_labels(sample, words) for sample in samples
    ])
    if not agreed:
        return {word: WordLabel.UNSURE for word in words}
    return {word: WordLabel(label) for word, label in agreed.items()}


def _normalise_labels(payload: dict | None, words: list[str]) -> dict | None:
    """Validate a labels response against the requested words."""
    if not payload:
        return None
    labels = payload.get("labels")
    if not isinstance(labels, dict):
        return None
    lowered = {str(k).strip(): str(v).strip().upper() for k, v in labels.items()}
    result: dict[str, str] = {}
    for word in words:
        label = lowered.get(word) or lowered.get(word.lower())
        if label not in {item.value for item in WordLabel}:
            return None  # incomplete or unrecognised: discard the whole sample
        result[word] = label
    if len(lowered) != len(words):
        return None  # the model labelled something it was not asked about
    return result


# ---------------------------------------------------------------------------
# 2. Adjudicating deterministic findings (suppress only)
# ---------------------------------------------------------------------------

def adjudicate_finding(check_id: str, message: str, excerpt: str) -> Verdict:
    """Ask whether a deterministic finding is a false positive.

    Only ever used to *hide* a finding.  The model is not permitted to add one:
    a suppression that is wrong leaves the editor exactly where they were
    without the tool, while an addition that is wrong sends them looking for a
    problem that is not there.

    A model that cannot be reached, disagrees with itself, or answers UNSURE
    leaves the finding standing.
    """
    if not available():
        return Verdict.UNSURE

    user = (
        "A deterministic checker flagged something in a JACoW paper. Decide "
        "whether the flag is correct.\n\n"
        f"Check: {check_id}\n"
        f"Message: {message}\n"
        f"Text it flagged:\n{excerpt[:800]}\n\n"
        'Reply with JSON: {"verdict": "CONFIRM"|"REJECT"|"UNSURE", '
        '"quote": "<the exact text your verdict is about>"}\n'
        "CONFIRM — the flag is right.\n"
        "REJECT — the flag is wrong; the text is acceptable as written.\n"
        "UNSURE — you cannot tell.\n"
        "The quote must be copied from the text above. Do not return any other text."
    )
    samples = [_ask_json(user) for _ in range(SAMPLES)]
    normalised = []
    for sample in samples:
        if not sample:
            normalised.append(None)
            continue
        verdict = str(sample.get("verdict", "")).strip().upper()
        quote = str(sample.get("quote", "")).strip()
        # The quote must be real: it is the cheapest check that the model was
        # looking at the text rather than the message.
        if verdict not in {item.value for item in Verdict} or (quote and quote not in excerpt):
            normalised.append(None)
            continue
        normalised.append({"verdict": verdict})
    agreed = _unanimous(normalised)
    return Verdict(agreed["verdict"]) if agreed else Verdict.UNSURE


def suppress_false_positives(findings: list, source: str) -> tuple[list, list]:
    """Partition *findings* into ``(kept, suppressed)`` using the model.

    Suppressed findings are not discarded by the caller — they are reported
    separately, so an editor can see what the model hid and why.
    """
    if not available():
        return list(findings), []

    kept: list = []
    suppressed: list = []
    for finding in findings:
        excerpt = finding.original or _line_excerpt(source, finding.line)
        if not excerpt:
            kept.append(finding)
            continue
        if adjudicate_finding(finding.check_id, finding.message, excerpt) is Verdict.REJECT:
            suppressed.append(finding)
        else:
            kept.append(finding)
    return kept, suppressed


def _line_excerpt(source: str, line: int | None, context: int = 1) -> str:
    if not line:
        return ""
    lines = source.splitlines()
    start = max(0, line - 1 - context)
    end = min(len(lines), line + context)
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# Integration helper
# ---------------------------------------------------------------------------

def resolve_title_casing(title: str, *, evidence: set[str] | None = None):
    """Sentence-case *title*, using a model only for the words that abstained.

    The deterministic pass runs first and does almost all the work; the model
    is asked only about the residue it could not classify, and only ever for
    labels.  The text is then rebuilt in code from those labels, so the model
    never gets to return prose.  Words it also cannot classify stay UNSURE, and
    a title with any UNSURE word is left exactly as the author wrote it.

    Returns a :class:`jacow_formatter.TitleCasing`.
    """
    from src.references import TitleCasing, sent_case_report

    report = sent_case_report(title, evidence=evidence)
    if not report.unsure or not available():
        return report

    labels = classify_title_words(title, list(report.unsure))
    to_lower = {
        word for word, label in labels.items() if label is WordLabel.LOWER
    }
    still_unsure = tuple(
        word for word, label in labels.items() if label is WordLabel.UNSURE
    )
    if not to_lower:
        return TitleCasing(report.text, still_unsure, report.changed, report.protected)

    # Rebuild from the deterministic output, lowercasing only the tokens the
    # model positively identified as ordinary words.
    rebuilt = []
    for token in report.text.split():
        core = token.strip("\u201c\u201d\"'()[],.;:!?")
        rebuilt.append(token.lower() if core in to_lower else token)
    text = " ".join(rebuilt)
    return TitleCasing(text, still_unsure, text != title, report.protected)
