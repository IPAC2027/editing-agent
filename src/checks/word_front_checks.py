"""Title, author and unit checks for Word submissions.

LaTeX papers get these from :mod:`src.checks.formatting_checks` and
:func:`src.autofix.latex_edits.unit_edits`; Word papers previously got none of
them.  They are findings, not tracked changes: a body paragraph in Word is
split into runs (superscripts, symbols, fields), and rewriting one safely is a
larger job than reporting what to change.

- FMT-TITLE-02  the title ends with punctuation (same rule as LaTeX)
- WORD-TITLE-01 the title is not in capitals (units and names such as GeV,
                JACoW, SwissFEL keep their own case)
- FMT-AUTH-01   author names not in "Initials Surname" form (same rule as LaTeX)
- WORD-AUTH-02  "and" between author names
- WORD-UNIT-01  value and unit separated by an ordinary space, or none
- WORD-UNIT-02  unit written in the wrong case (Gev, Mhz)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.autofix.latex_edits import (
    _ALL_UNIT_KEYS,
    _AMBIGUOUS_UNIT_KEYS,
    _COUNTER_WORD_RE,
    _UNIT_BY_LOWER,
)
from src.models import Finding, Severity
from src.parser.latex_parser import is_jacow_author_name

NBSP = "\u00a0"
_TITLE_STYLES = {"jacow_paper title", "title", "jacow_title"}
_FOOTNOTE_MARKS = "*†‡§¶"


@dataclass
class WordFrontMatter:
    title: str = ""
    author_line: str = ""
    body: list[str] = field(default_factory=list)   # paragraphs before REFERENCES


def read_front_matter(doc_path: Path) -> WordFrontMatter:
    """Title, author line and body paragraphs, by JACoW style name where present."""
    import docx  # python-docx

    paragraphs = [(p.text, (p.style.name if p.style is not None else "") or "")
                  for p in docx.Document(str(doc_path)).paragraphs]
    result = WordFrontMatter()
    title_index: int | None = None
    for index, (text, style) in enumerate(paragraphs):
        if text.strip() and style.lower() in _TITLE_STYLES:
            result.title, title_index = text.strip(), index
            break
    if title_index is None:
        title_index = next((i for i, (t, _) in enumerate(paragraphs) if t.strip()), None)
        if title_index is not None:
            result.title = paragraphs[title_index][0].strip()

    if title_index is not None:
        styled = next((t for t, s in paragraphs[title_index + 1:]
                       if t.strip() and "author" in s.lower()), None)
        following = next((t for t, _ in paragraphs[title_index + 1:] if t.strip()), "")
        # Authors and affiliation often share one paragraph, separated by a
        # line break: only the names are the author line.
        result.author_line = author_part((styled or following))

    for text, _ in paragraphs:
        if re.fullmatch(r"\s*REFERENCES?\s*", text, re.IGNORECASE):
            break
        result.body.append(text)
    return result


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

def _title_word_ok(word: str, previous: str = "") -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", word)
    if not letters or letters.isupper():
        return True
    # Mixed case with a capital after the first letter: GeV, JACoW, SwissFEL,
    # SPring-8, mW.  These are intentional and must be kept.
    if any(ch.isupper() for ch in letters[1:]):
        return True
    # A lowercase unit symbol (mm, s, ns) may stay lowercase — but only right
    # after a number, or "a" (ampere's key) would excuse the article.
    return (bool(re.search(r"\d$", previous)) and letters == letters.lower()
            and letters in _ALL_UNIT_KEYS)


def check_title(title: str) -> list[Finding]:
    findings: list[Finding] = []
    visible = title.rstrip(_FOOTNOTE_MARKS + " ").strip()
    if not visible:
        return findings
    if visible.endswith((".", ",", ";", ":", "!", "?")):
        findings.append(Finding(
            check_id="FMT-TITLE-02", severity=Severity.WARNING, original=title,
            suggested=visible.rstrip(".,;:!?") + title[len(visible):],
            message="The title must not end with punctuation.",
        ))
    words = visible.split()
    ok = [_title_word_ok(w, words[i - 1] if i else "") for i, w in enumerate(words)]
    lower = [w for w, good in zip(words, ok) if not good]
    if lower:
        suggested = " ".join(w if good else w.upper() for w, good in zip(words, ok))
        findings.append(Finding(
            check_id="WORD-TITLE-01", severity=Severity.WARNING, original=visible,
            suggested=suggested,
            message=("The title must be in capitals (14 pt bold uppercase), keeping the "
                     "case of units and names such as GeV or SwissFEL. Not in capitals: "
                     + ", ".join(f"'{w}'" for w in lower[:6])
                     + (" …" if len(lower) > 6 else "") + "."),
        ))
    return findings


# ---------------------------------------------------------------------------
# Authors
# ---------------------------------------------------------------------------

_AFFILIATION_WORDS = re.compile(
    r"\b(?:Institute|Institut|University|Universit\w*|Univ\.|Laborator\w*|Lab\b|Center|"
    r"Centre|Department|Dept\.|College|School|Faculty|Facility|Research|Academy|"
    r"Corporation|Inc\.|GmbH|Ltd|Foundation|Hospital|Observatory|National)\b")


def author_part(paragraph: str) -> str:
    """The author names in an author paragraph, without the affiliation.

    Stops at the first line break, and otherwise at the first comma-separated
    part that names an institution ("Institute for …", "University of …").
    """
    first_line = re.split(r"[\n\x0b\r]", paragraph.strip(), maxsplit=1)[0].strip()
    # "M. Kappa, for XYZG" / "… on behalf of the X Collaboration": a group the
    # author speaks for, not another author.
    first_line = re.split(r",?\s+(?:for|on behalf of)\s+(?=\S)", first_line, maxsplit=1)[0].strip()
    parts = [p.strip() for p in first_line.split(",")]
    kept: list[str] = []
    for part in parts:
        match = _AFFILIATION_WORDS.search(part)
        if match:
            before = part[:match.start()].strip()
            # "H.P. Alpha† Institute for …": the names before the institution word
            if before:
                kept.append(before)
            break
        kept.append(part)
    return ", ".join(p for p in kept if p)


def _author_names(line: str) -> list[str]:
    cleaned = re.sub(rf"[{_FOOTNOTE_MARKS}]|(?<=[A-Za-z’'])\d+(?:,\d+)*", "", line)
    parts = re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", cleaned.strip())
    return [p.strip() for p in parts if p.strip()]


def check_authors(author_line: str) -> list[Finding]:
    findings: list[Finding] = []
    if not author_line:
        return findings
    if re.search(r"\band\b", author_line):
        findings.append(Finding(
            check_id="WORD-AUTH-02", severity=Severity.WARNING, original=author_line,
            suggested=re.sub(r",?\s+and\s+", ", ", author_line),
            message="Author names are separated by commas only, without 'and'.",
        ))
    names = _author_names(author_line)
    offenders = [n for n in names if not is_jacow_author_name(n)]
    if offenders:
        findings.append(Finding(
            check_id="FMT-AUTH-01", severity=Severity.WARNING,
            original=", ".join(offenders),
            message=(f"{len(offenders)} of {len(names)} author names are not in JACoW "
                     "'Initials Surname' form: " + ", ".join(f"'{n}'" for n in offenders[:8])
                     + ". Abbreviate given names to initials."),
        ))
    return findings


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

_WORD_NUMBER_UNIT_RE = re.compile(
    r"(?<![\w.])(?P<number>\d+(?:[.,]\d+)?)(?P<sep>[ \t\u00a0\u202f]*)"
    r"(?P<unit>[A-Za-zµΩ]+)(?![A-Za-z])"
)


def check_units(paragraphs: list[str]) -> list[Finding]:
    """One finding per kind of problem, with examples — not one per measurement."""
    spacing: list[str] = []
    casing: list[tuple[str, str]] = []
    for paragraph in paragraphs:
        for match in _WORD_NUMBER_UNIT_RE.finditer(paragraph):
            unit, sep = match.group("unit"), match.group("sep")
            key = unit.lower()
            if key not in _ALL_UNIT_KEYS:
                continue
            if _COUNTER_WORD_RE.search(paragraph[max(0, match.start() - 24):match.start()]):
                continue
            # Without a space, only multi-letter units are reliable: "5m" is a
            # measurement, but "2D" or "3G" are not.
            if not sep and len(unit) < 2:
                continue
            if sep not in (NBSP, "\u202f"):
                spacing.append(match.group(0))
            canonical = _UNIT_BY_LOWER.get(key)
            if (canonical and unit != canonical and len(canonical) > 1
                    and key not in _AMBIGUOUS_UNIT_KEYS):
                casing.append((match.group(0), f"{match.group('number')}{NBSP}{canonical}"))

    findings: list[Finding] = []
    if spacing:
        examples = ", ".join(f"'{s}'" for s in list(dict.fromkeys(spacing))[:5])
        findings.append(Finding(
            check_id="WORD-UNIT-01", severity=Severity.WARNING,
            original=examples,
            message=(f"{len(spacing)} value(s) are not joined to their unit by a "
                     f"non-breaking space (Ctrl+Shift+Space in Word), e.g. {examples}."),
        ))
    seen: set[str] = set()
    for original, suggested in casing:
        if original in seen:
            continue
        seen.add(original)
        findings.append(Finding(
            check_id="WORD-UNIT-02", severity=Severity.WARNING,
            original=original, suggested=suggested,
            message=f"'{original}': use the standard unit symbol, '{suggested}'.",
        ))
    return findings


def run_all(doc_path: Path) -> list[Finding]:
    front = read_front_matter(doc_path)
    return [*check_title(front.title), *check_authors(front.author_line),
            *check_units(front.body)]
