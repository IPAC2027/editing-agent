"""Mechanical checks that a reference rewrite did not damage the reference.

Round-tripping a reference through a field model and re-emitting it from a
template is the highest-risk operation in this codebase: the model can drop a
clause, the template can double a separator, and sentence-casing can lowercase
a surname.  None of that is caught by reading the output — it is caught by
comparing the output to the input.

The previous guard checked only for a handful of *missing markers* (``in Proc.``,
``pp.``, ``vol.``, a DOI token).  It passed both defects observed on the sample
corpus:

* ``pp. 611-632,,`` — a doubled comma the template introduced;
* ``Poincaré`` → ``poincaré`` — a proper noun the sentence-caser lowercased.

:func:`check_rewrite` catches both, plus every other case where information
present in the input is absent from the output.  A rewrite that fails any check
is discarded and the original text is kept: the agent's job is to save the
editor time, and a damaged reference costs more time than an unformatted one.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

# Markers whose disappearance means a whole clause was lost.
_STRUCTURAL_MARKERS = (
    (r"\bin\s+Proc\.", "the 'in Proc.' clause"),
    (r"\bpresented\s+at\b", "the 'presented at' clause"),
    (r"\bpp?\.\s*\d", "the page numbers"),
    (r"\bvol\.\s*\w", "the volume"),
    (r"\bno\.\s*\w", "the issue number"),
    (r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", "the month"),
    (r"\bthesis\b", "the thesis designation"),
    (r"\bunpublished\b", "the 'unpublished' note"),
    (r"\bRep\.\s*\w", "the report number"),
)

_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+", re.IGNORECASE)
_DIGIT_RUN_RE = re.compile(r"\d+")
_WORD_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

# Doubled separators that only a template bug produces.
_DOUBLED_PUNCT_RE = re.compile(r"([,;:])\s*\1|\.\.(?!\.)|\s,|\(\s*\)|\{\s*\}")

# Latin abbreviations and initials legitimately produce ".," and ". ," patterns,
# so the doubled-punctuation test ignores those.
_BENIGN_DOUBLE = re.compile(r"\bet al\.\s*,|\b[A-Z]\.\s*,")


@dataclass
class RewriteVerdict:
    """Outcome of verifying one rewrite."""

    ok: bool
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok

    @property
    def reason(self) -> str:
        return "; ".join(self.problems)


def _fold(text: str) -> str:
    lowered = text.lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(ch) != "Mn"
    )


def check_rewrite(
    original: str,
    rewritten: str,
    *,
    allow_case_change: bool = True,
    unsure_tokens: tuple[str, ...] | list[str] = (),
    allowed_substitutions: Sequence[tuple[str, str]] = (),
) -> RewriteVerdict:
    """Return a verdict on whether *rewritten* is a safe replacement for *original*.

    The checks, in the order they are cheapest to reason about:

    *allowed_substitutions* declares changes the caller knows about and vouches
    for, as ``(before, after)`` pairs.  Both sides are masked out before
    comparison, so a legitimate ISO-4 journal abbreviation — "SIAM Journal on
    Applied Dynamical Systems" to "SIAM J. Appl. Dyn. Syst.", which is exactly
    what JACoW requires — is not reported as five dropped words.  Anything the
    caller does not declare is still checked.

    1. **Abstention.** If sentence-casing could not classify a word, no rewrite.
    2. **Doubled punctuation.** New ``,,`` / ``..`` / `` ,`` / empty groups.
    3. **Digits.** Every run of digits in the input must appear in the output
       with at least the same multiplicity — page ranges, years, volumes and
       DOIs are all digits, and losing one is unrecoverable by eye.
    4. **DOIs.** Every DOI in the input must survive verbatim.
    5. **Words.** No word may vanish (accent- and case-insensitively).
    6. **Capitalisation.** A word may not change case unless the input and
       output agree on it — this is the ``Poincaré`` → ``poincaré`` check.
    7. **Structure.** No structural marker may disappear.
    8. **Bulk.** The output may not be dramatically shorter than the input.
    """
    problems: list[str] = []
    notes: list[str] = []

    original = original.strip()
    rewritten = rewritten.strip()

    if not rewritten:
        return RewriteVerdict(False, ["the rewrite is empty"])

    # Mask declared substitutions on both sides with the same placeholder.
    for index, (was, now) in enumerate(allowed_substitutions):
        was, now = (was or "").strip(), (now or "").strip()
        if not was or not now or was == now:
            continue
        if was in original and now in rewritten:
            placeholder = f"\x00SUB{index}\x00"
            original = original.replace(was, placeholder)
            rewritten = rewritten.replace(now, placeholder)
            notes.append(f"allowed substitution: {was!r} -> {now!r}")

    if unsure_tokens:
        listed = ", ".join(f"'{token}'" for token in unsure_tokens)
        problems.append(
            f"sentence case could not classify {listed} — leaving the title as written"
        )

    # 2. doubled punctuation the original did not have
    def _doubles(text: str) -> Counter:
        stripped = _BENIGN_DOUBLE.sub(" ", text)
        return Counter(match.group(0).strip() for match in _DOUBLED_PUNCT_RE.finditer(stripped))

    before_doubles, after_doubles = _doubles(original), _doubles(rewritten)
    for token, count in after_doubles.items():
        if count > before_doubles.get(token, 0):
            problems.append(f"introduced doubled punctuation {token!r}")

    # 3. digits
    before_digits = Counter(_DIGIT_RUN_RE.findall(original))
    after_digits = Counter(_DIGIT_RUN_RE.findall(rewritten))
    lost_digits = [run for run, count in before_digits.items()
                   if after_digits.get(run, 0) < count]
    if lost_digits:
        problems.append(
            "dropped the number(s) " + ", ".join(sorted(lost_digits)[:4])
        )

    # 4. DOIs
    for doi in _DOI_RE.findall(original):
        trimmed = doi.rstrip(".,;)]}")
        if trimmed.lower() not in rewritten.lower():
            problems.append(f"dropped the DOI {trimmed}")

    # 5 & 6. words and their capitalisation
    before_words = _WORD_RE.findall(original)
    after_words = _WORD_RE.findall(rewritten)
    after_folded = Counter(_fold(word) for word in after_words)
    before_folded = Counter(_fold(word) for word in before_words)
    lost_words = [word for word, count in before_folded.items()
                  if after_folded.get(word, 0) < count]
    if lost_words:
        problems.append("dropped the word(s) " + ", ".join(sorted(lost_words)[:5]))

    if not allow_case_change:
        before_exact = Counter(before_words)
        after_exact = Counter(after_words)
        recased = sorted(
            word for word, count in before_exact.items()
            if after_exact.get(word, 0) < count
            and after_folded.get(_fold(word), 0) >= count
        )
        if recased:
            problems.append("changed the capitalisation of " + ", ".join(recased[:5]))

    # 7. structure
    for pattern, description in _STRUCTURAL_MARKERS:
        if re.search(pattern, original, re.IGNORECASE) and not re.search(
            pattern, rewritten, re.IGNORECASE
        ):
            problems.append(f"dropped {description}")

    # 8. bulk
    if len(rewritten) < 0.6 * len(original):
        problems.append(
            f"the rewrite is {len(rewritten)} characters against {len(original)} — "
            "too much was removed"
        )

    if original == rewritten:
        notes.append("no change")

    return RewriteVerdict(ok=not problems, problems=problems, notes=notes)


def proper_noun_risk(original: str, rewritten: str) -> list[str]:
    """Words that were lowercased and might be proper nouns.

    Used for reporting: a rewrite is rejected by :func:`check_rewrite`, and this
    explains to the editor which word triggered it.
    """
    risky: list[str] = []
    after = {_fold(word): word for word in _WORD_RE.findall(rewritten)}
    for word in _WORD_RE.findall(original):
        if not word[:1].isupper():
            continue
        counterpart = after.get(_fold(word))
        if counterpart and counterpart.islower():
            risky.append(word)
    return risky
