"""Corrections to the main text of a Word paper, as tracked changes.

The main-text checks used to be reported only; nothing was written into the
Word file (one test paper: "[8][9]", "14 T", "1.9 K" all left as they were).  This
module turns each mechanical rule into a span fix on one paragraph:

==================  =====================================================  =======
Check               Fix                                                    Tier
==================  =====================================================  =======
WORD-UNIT-01        ordinary space before a unit -> non-breaking space    auto
TXT-CITE-01         "[8][9]", "[1], [2]" -> "[8, 9]", "[1, 2]"            auto
TXT-TAB-01          "Tab. 1" -> "Table 1"                                 auto
TXT-FIG-01          "Fig. 1" starting a sentence -> "Figure 1"            auto
WORD-UNIT-02        "Gev" -> "GeV" (unambiguous symbols only)             suggest
TXT-EQ-01           "equation 1" / "Eq. 1" -> "Eq. (1)"                   suggest
WORD-TITLE-01, FMT-TITLE-02  title in capitals; no closing punctuation             suggest
WORD-AUTH-02        no "and" in the author list                           suggest
WORD-HEAD-01        numbered section heading -> unnumbered                suggest
WORD-HEAD-02        subsection heading in Title Case                      suggest
WORD-CAP-01         "Figure 1 -" / "Fig. 1." -> "Figure 1:"               suggest
WORD-CAP-02         figure caption ends with a full stop                  suggest
WORD-CAP-03         heading-style table caption has no full stop          suggest
==================  =====================================================  =======

Report-only (no safe automatic fix): WORD-STYLE-01 (body text in a heading
style), TXT-ACR-01 (acronyms not expanded at first use).

A paragraph containing a hyperlink, field or other non-run content is never
rewritten: the tracked-change writer rebuilds a paragraph from its runs, and
would lose those.  Its problems stay reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.autofix.latex_edits import (
    _ALL_UNIT_KEYS,
    _AMBIGUOUS_UNIT_KEYS,
    _COUNTER_WORD_RE,
    _UNIT_BY_LOWER,
)
from src.models import Finding, Severity

NBSP = "\u00a0"


@dataclass
class BodyFix:
    paragraph_index: int
    start: int
    end: int
    before: str
    after: str
    tier: str            # "auto" | "suggest"
    check_id: str
    message: str


@dataclass
class _Para:
    index: int
    text: str            # concatenated run text — what the writer rewrites
    style: str
    writable: bool


def _paragraphs(doc_path: Path) -> list[_Para]:
    import docx
    from docx.oxml.ns import qn

    out = []
    for i, p in enumerate(docx.Document(str(doc_path)).paragraphs):
        runs_text = "".join(r.text for r in p.runs)
        el = p._element
        complex_content = bool(
            el.findall(qn("w:hyperlink")) or el.findall(qn("w:fldSimple"))
            or el.findall(".//" + qn("w:fldChar")) or el.findall(qn("w:ins"))
            or el.findall(qn("w:del")) or el.findall(".//" + qn("w:footnoteReference"))
            or el.findall(".//" + qn("m:oMath")))
        out.append(_Para(i, runs_text, (p.style.name if p.style is not None else "") or "",
                         writable=not complex_content and runs_text == p.text))
    return out


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

_NUMBER_UNIT_RE = re.compile(
    r"(?<![\w.])(?P<number>\d+(?:[.,]\d+)?)(?P<sep>[ \t]+)(?P<unit>[A-Za-zµΩ]+(?:/[A-Za-z]+)?)(?![A-Za-z])")


def _unit_fixes(p: _Para) -> list[BodyFix]:
    fixes = []
    for m in _NUMBER_UNIT_RE.finditer(p.text):
        unit = m.group("unit")
        key = unit.lower()
        if key not in _ALL_UNIT_KEYS:
            continue
        if _COUNTER_WORD_RE.search(p.text[max(0, m.start() - 24):m.start()]):
            continue
        if len(unit) == 1 and unit.islower():
            continue                 # "3 m" is fine, "a 2 s delay" too, but "1 a" is a word
        fixes.append(BodyFix(p.index, m.start("sep"), m.end("sep"), m.group("sep"), NBSP,
                             "auto", "WORD-UNIT-01",
                             f"'{m.group(0)}': joined by a non-breaking space."))
        canonical = _UNIT_BY_LOWER.get(key)
        if (canonical and unit != canonical and len(canonical) > 1
                and key not in _AMBIGUOUS_UNIT_KEYS):
            fixes.append(BodyFix(p.index, m.start("unit"), m.end("unit"), unit, canonical,
                                 "suggest", "WORD-UNIT-02",
                                 f"'{unit}' → '{canonical}': standard unit symbol."))
    return fixes


_ADJACENT_CITES_RE = re.compile(
    r"\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\](?:\s*,?\s*\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\])+")


def _citation_fixes(p: _Para) -> list[BodyFix]:
    fixes = []
    for m in _ADJACENT_CITES_RE.finditer(p.text):
        numbers = re.findall(r"\[([^\]]+)\]", m.group(0))
        merged = "[" + ", ".join(n.strip() for n in numbers) + "]"
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0), merged, "auto",
                             "TXT-CITE-01", f"'{m.group(0)}' → '{merged}': one bracket."))
    return fixes


def _callout_fixes(p: _Para) -> list[BodyFix]:
    fixes = []
    for m in re.finditer(r"\bTab\.(\s*)(\d+)", p.text):
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0),
                             f"Table{m.group(1) or NBSP}{m.group(2)}", "auto", "TXT-TAB-01",
                             f"'{m.group(0)}': a table reference is never abbreviated."))
    for m in re.finditer(r"(?:^|(?<=[.!?]\s))(Figs?)\.(?=\s*\d)", p.text):
        full = "Figures" if m.group(1) == "Figs" else "Figure"
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0), full, "auto",
                             "TXT-FIG-01", f"'{m.group(0)}' starts a sentence: '{full}'."))
    for m in re.finditer(r"\b(Eqs?\.)(\s*)(\d+)\b(?!\s*\))", p.text):
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0),
                             f"{m.group(1)}{m.group(2) or NBSP}({m.group(3)})", "suggest",
                             "TXT-EQ-01", f"'{m.group(0)}': the number goes in parentheses."))
    for m in re.finditer(r"\b[Ee]quation(\s*)\(?(\d+)\)?", p.text):
        if m.start() == 0 or re.search(r"[.!?]\s*$", p.text[:m.start()]):
            continue
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0), f"Eq.{NBSP}({m.group(2)})",
                             "suggest", "TXT-EQ-01",
                             f"'{m.group(0)}' mid-sentence: 'Eq. ({m.group(2)})'."))
    return fixes


_SMALL_WORDS = frozenset("a an and as at but by for from in into nor of on or per the to via vs with".split())


def _title_case(text: str) -> str:
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        core = w.strip("()[]\"'“”,:;")
        if (i > 0 and core.lower() in _SMALL_WORDS) or not core or not core[0].isalpha():
            out.append(w)
        elif core.islower():
            out.append(w.replace(core, core[0].upper() + core[1:], 1))
        else:
            out.append(w)
    return " ".join(out)


def _heading_fixes(p: _Para, findings: list[Finding]) -> list[BodyFix]:
    style = p.style.lower()
    text = p.text
    fixes: list[BodyFix] = []
    if "heading" not in style or not text.strip():
        return fixes
    if len(text.split()) > 14:
        findings.append(Finding(
            check_id="WORD-STYLE-01", severity=Severity.WARNING,
            message=(f"A paragraph of body text is in the heading style '{p.style}': "
                     f"'{text[:80]}…'. Apply the body-text style."),
            original=text[:200]))
        return fixes
    numbered = re.match(r"^\s*((?:\d+(?:\.\d+)*|[IVX]+|[A-H])[.)]?\s+)(?=\S)", text)
    if numbered and ("section" in style or "subsection" in style or re.match(r"heading \d", style)):
        fixes.append(BodyFix(p.index, numbered.start(1), numbered.end(1), numbered.group(1), "",
                             "suggest", "WORD-HEAD-01",
                             f"'{text.strip()[:60]}': headings are not numbered."))
    if "subsection" in style or "third" in style or re.match(r"heading [23]\b", style):
        start = numbered.end(1) if numbered else 0
        body = text[start:]
        cased = _title_case(body)
        if cased != body:
            fixes.append(BodyFix(p.index, start, len(text), body, cased, "suggest",
                                 "WORD-HEAD-02", f"'{body.strip()}': subsection headings use Title Case."))
    return fixes


_CAPTION_RE = re.compile(r"^(?P<label>(?:Figure|Fig\.|FIG\.|Table|TABLE))\s*(?P<num>\d+)(?P<sep>\s*[-\u2013\u2014.:]?\s*)")


def _caption_fixes(p: _Para) -> list[BodyFix]:
    m = _CAPTION_RE.match(p.text)
    if not m or len(p.text) < 8:
        return []
    is_caption_style = "caption" in p.style.lower()
    sep = m.group("sep")
    # A body sentence that merely starts "Figure 1 shows…" is not a caption.
    if not is_caption_style and not re.search(r"[-\u2013\u2014.:]", sep):
        return []
    fixes: list[BodyFix] = []
    figure = m.group("label").lower().startswith("fig")
    label = "Figure" if figure else "Table"
    wanted = f"{label} {m.group('num')}: "
    if m.group(0) != wanted:
        fixes.append(BodyFix(p.index, 0, m.end(), m.group(0), wanted, "suggest", "WORD-CAP-01",
                             f"'{m.group(0).strip()}' → '{wanted.strip()}': caption label form."))
    stripped = p.text.rstrip()
    if figure and not stripped.endswith((".", "?", "!")):
        fixes.append(BodyFix(p.index, len(stripped), len(stripped), "", ".", "suggest",
                             "WORD-CAP-02", "A figure caption ends with a full stop."))
    if not figure and stripped.endswith(".") and len(stripped.split()) <= 10 \
            and not re.search(r"[.!?]\s+\S", stripped[m.end():-1]):
        fixes.append(BodyFix(p.index, len(stripped) - 1, len(stripped), ".", "", "suggest",
                             "WORD-CAP-03", "A heading-style table caption has no full stop."))
    return fixes


def _title_fixes(p: _Para) -> list[BodyFix]:
    """One suggestion for the whole title, not one per word."""
    from src.checks.word_front_checks import _title_word_ok

    fixes = []
    text = p.text
    visible = text[:len(text.rstrip("*†‡§¶ "))]
    core_end = len(visible.rstrip().rstrip(".,;:"))
    words = list(re.finditer(r"\S+", visible[:core_end]))
    wrong = [i for i, w in enumerate(words)
             if not _title_word_ok(w.group(0), words[i - 1].group(0) if i else "")]
    if wrong:
        start, end = words[wrong[0]].start(), words[wrong[-1]].end()
        segment = visible[start:end]
        fixed = " ".join(
            w if _title_word_ok(w, prev) else w.upper()
            for prev, w in zip([visible[:start].split()[-1] if visible[:start].split() else ""]
                               + segment.split()[:-1], segment.split()))
        if " ".join(segment.split()) == segment:
            fixes.append(BodyFix(p.index, start, end, segment, fixed, "suggest", "WORD-TITLE-01",
                                 "The title is in capitals, keeping units and names "
                                 "such as GeV or SwissFEL in their own case."))
    if visible.rstrip().endswith((".", ",", ";", ":")):
        end = len(visible.rstrip())
        fixes.append(BodyFix(p.index, end - 1, end, visible.rstrip()[-1], "", "suggest",
                             "FMT-TITLE-02", "The title must not end with punctuation."))
    return fixes


def _author_fixes(p: _Para) -> list[BodyFix]:
    from src.checks.word_front_checks import author_part

    names = author_part(p.text)
    fixes = []
    for m in re.finditer(r",?\s+and\s+", p.text[:len(names) + 5]):
        fixes.append(BodyFix(p.index, m.start(), m.end(), m.group(0), ", ", "suggest",
                             "WORD-AUTH-02", "Author names are separated by commas only."))
    # A full given name -> its initial ("Michael Duval" -> "M. Duval"), except
    # where the first word is probably a family name written first.
    from jacow_formatter.verify import _FAMILY_FIRST_NAMES
    for m in re.finditer(r"(?:(?<=^)|(?<=,\s)|(?<=\band\s))([A-Z][a-z]{2,})(?=\s+[A-Z][\w'\u2019\-]+)",
                         p.text[:len(names)]):
        if m.group(1).lower() in _FAMILY_FIRST_NAMES:
            continue
        fixes.append(BodyFix(p.index, m.start(1), m.end(1), m.group(1), m.group(1)[0] + ".",
                             "suggest", "FMT-AUTH-01",
                             f"'{m.group(1)}': JACoW lists authors as initials and surname."))
    return fixes


_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,5}s?)\b")
_WELL_KNOWN = frozenset("""CERN RF DC AC LHC SLAC DESY KEK PSI GSI FEL SRF CW USA UK EU
IPAC JACOW PDF ID II III IV TM TE HOM PC CPU GPU URL DOI""".split())


def _acronym_finding(paras: list[_Para]) -> Finding | None:
    text = "\n".join(p.text for p in paras)
    seen: dict[str, int] = {}
    for m in _ACRONYM_RE.finditer(text):
        seen.setdefault(m.group(1).rstrip("s"), m.start())
    unexplained = []
    for acronym, first in seen.items():
        if acronym in _WELL_KNOWN or len(acronym) < 2:
            continue
        if text.count(acronym) < 2:
            continue
        window = text[max(0, first - 2):first + len(acronym) + 1]
        if "(" in window[:2] and ")" in window[-2:]:
            continue                                   # "… Physics Update (ESPPU)"
        if re.search(r"\(" + re.escape(acronym) + r"\)", text[first:]):
            later = text.find(f"({acronym})", first)
            if later > first:
                unexplained.append(f"{acronym} (expanded only later)")
                continue
        unexplained.append(acronym)
    if not unexplained:
        return None
    shown = ", ".join(unexplained[:10]) + (" …" if len(unexplained) > 10 else "")
    return Finding(check_id="TXT-ACR-01", severity=Severity.INFO,
                   message=(f"Acronyms not expanded at their first use: {shown}. Expand each "
                            "the first time it appears, in the abstract and in the body."),
                   original=shown)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def body_fixes(doc_path: Path) -> tuple[list[BodyFix], list[Finding], dict[int, str]]:
    """All main-text fixes, report-only findings, and each paragraph's run text."""
    paras = _paragraphs(doc_path)
    findings: list[Finding] = []
    fixes: list[BodyFix] = []
    body: list[_Para] = []
    title_done = author_done = False
    for p in paras:
        if re.fullmatch(r"\s*REFERENCES?\s*", p.text, re.IGNORECASE):
            break
        body.append(p)
    # Without the JACoW styles, the paragraph after the title is the authors.
    has_author_style = any("author" in p.style.lower() for p in body)
    for p in body:
        style = p.style.lower()
        if not p.text.strip():
            continue
        found: list[BodyFix] = []
        if not title_done and ("title" in style or p is body[0]):
            title_done = True
            found += _title_fixes(p)
        elif not author_done and ("author" in style or not has_author_style):
            author_done = True
            found += _author_fixes(p)
        elif "author" in style or "abstract_heading" in style.replace(" ", "_"):
            continue
        else:
            found += _heading_fixes(p, findings)
            if "heading" not in style:
                found += _caption_fixes(p)
                found += _citation_fixes(p) + _callout_fixes(p)
            found += _unit_fixes(p)
        if not p.writable:
            continue                 # reported by the checks, never rewritten
        fixes += _without_overlaps(found)
    # From the abstract on: the title is in capitals by rule, and the author
    # block holds institute abbreviations, so neither says anything here.
    start = next((i for i, p in enumerate(body) if "abstract" in p.style.lower()), 0)
    acronyms = _acronym_finding([p for p in body[start:]
                                 if not re.search(r"heading|title|author", p.style.lower())])
    if acronyms:
        findings.append(acronyms)
    return fixes, findings, {p.index: p.text for p in paras}


def _without_overlaps(fixes: list[BodyFix]) -> list[BodyFix]:
    kept: list[BodyFix] = []
    for fix in sorted(fixes, key=lambda f: (f.start, -(f.end - f.start))):
        if any(fix.start < k.end and k.start < fix.end for k in kept):
            continue
        if any(fix.start == fix.end == k.start == k.end for k in kept):
            continue
        kept.append(fix)
    return kept


def apply_fixes(text: str, fixes: list[BodyFix]) -> str:
    """*text* with *fixes* (all on that paragraph) applied."""
    for fix in sorted(fixes, key=lambda f: f.start, reverse=True):
        text = text[:fix.start] + fix.after + text[fix.end:]
    return text
