"""Paragraph and heading layout in Word papers, as tracked formatting changes.

Style Guide, *Subsection Headings* and *Paragraph Text*: subsection headings
are 12 pt italic, left aligned, directly above their text with no column
break after them; paragraphs are 10 pt, justified, first line indented
0.33 cm, and never leave a single line at the top or bottom of a column.

The JACoW template's styles already say all of that.  What goes wrong in
submissions is direct formatting on top of them, or the wrong style:

=============  ==========================================================  =======
Check          Fix                                                          Tier
=============  ==========================================================  =======
WORD-PARA-01   body paragraph whose indent was overridden -> style's 0.33 cm  auto
WORD-PARA-02   widow/orphan control off -> on                                auto
WORD-PARA-03   body text in "Normal" or a heading style -> body-text style   suggest
WORD-PARA-04   direct font size / italic / bold on body text removed        suggest
WORD-HEAD-03   heading not kept with its next paragraph -> kept             auto
WORD-HEAD-05   subsection heading not 12 pt italic, left -> style restored   suggest
WORD-HEAD-04   third-level heading on its own line (should run in)          report
=============  ==========================================================  =======

Every change is a tracked *formatting* change (w:pPrChange / w:rPrChange):
the reviewing pane shows "Formatted: …" and rejecting it restores the
author's formatting exactly.
"""

from __future__ import annotations

import copy
import datetime as _dt
import itertools
from dataclasses import dataclass, field
from pathlib import Path

from src.models import Finding, Severity

BODY_STYLE_IDS = ("JACoWBodyTextIndent",)
_TWIPS_033CM = 187


@dataclass
class FormatFix:
    paragraph_index: int
    check_id: str
    tier: str
    message: str
    set_style: str = ""                                  # style id
    remove_ppr: list[str] = field(default_factory=list)  # e.g. ["w:jc", "w:ind"]
    add_ppr: list[str] = field(default_factory=list)     # e.g. ["w:keepNext"]
    remove_rpr: list[str] = field(default_factory=list)  # on every run

    def as_dict(self) -> dict:
        return {"set_style": self.set_style, "remove_ppr": self.remove_ppr,
                "add_ppr": self.add_ppr, "remove_rpr": self.remove_rpr}


# ---------------------------------------------------------------------------
# Reading effective formatting
# ---------------------------------------------------------------------------

def _style_chain(style):
    while style is not None:
        yield style
        style = style.base_style


def _effective(paragraph, attr):
    value = getattr(paragraph.paragraph_format, attr)
    if value is not None:
        return value, True
    for style in _style_chain(paragraph.style):
        value = getattr(style.paragraph_format, attr)
        if value is not None:
            return value, False
    return None, False


def _style_has(document, style_id: str) -> bool:
    return any(s.style_id == style_id for s in document.styles)


def _doc_default_widow_control(document) -> bool:
    from docx.oxml.ns import qn
    defaults = document.styles.element.find(qn("w:docDefaults"))
    return defaults is not None and defaults.find(".//" + qn("w:widowControl")) is not None


def format_fixes(doc_path: Path) -> tuple[list[FormatFix], list[Finding]]:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn

    document = docx.Document(str(doc_path))
    fixes: list[FormatFix] = []
    findings: list[Finding] = []
    has_body_style = _style_has(document, BODY_STYLE_IDS[0])
    widow_default = _doc_default_widow_control(document)
    paragraphs = document.paragraphs

    for index, p in enumerate(paragraphs):
        text = p.text.strip()
        if not text:
            continue
        if text.upper().startswith("REFERENCES") and len(text) < 15:
            break
        style = p.style.name if p.style is not None else ""
        style_l = style.lower()
        sid = p.style.style_id if p.style is not None else ""
        words = len(text.split())
        ppr = p._p.pPr
        next_text = next((q for q in paragraphs[index + 1:] if q.text.strip()), None)

        is_heading = "heading" in style_l and "abstract" not in style_l
        looks_like_body = words > 14 and not text.startswith(("Figure", "Table", "Fig."))

        # Body text in the wrong style ("Normal", or a heading style).
        if has_body_style and looks_like_body and (style_l == "normal" or is_heading):
            fixes.append(FormatFix(
                index, "WORD-PARA-03", "suggest",
                f"Paragraph in style '{style}' is body text: give it the body-text style "
                "(10 pt, justified, first line indented 0.33 cm).",
                set_style=BODY_STYLE_IDS[0],
                remove_ppr=["w:jc", "w:ind", "w:keepNext", "w:spacing", "w:outlineLvl"],
                remove_rpr=["w:i", "w:iCs", "w:b", "w:bCs", "w:sz", "w:szCs"]))
            continue

        if is_heading:
            keep, _ = _effective(p, "keep_with_next")
            if not keep and next_text is not None:
                fixes.append(FormatFix(
                    index, "WORD-HEAD-03", "auto",
                    f"'{text[:50]}': kept with the next paragraph, so no column break "
                    "falls between a heading and its text.", add_ppr=["w:keepNext"]))
            if "subsection" in style_l:
                align, direct_align = _effective(p, "alignment")
                italic_off = any(r.font.italic is False for r in p.runs if r.text.strip())
                sizes = {r.font.size.pt for r in p.runs if r.font.size and r.text.strip()}
                wrong = []
                if direct_align and align not in (None, WD_ALIGN_PARAGRAPH.LEFT):
                    wrong.append("alignment")
                if italic_off:
                    wrong.append("italic")
                if sizes and sizes != {12.0}:
                    wrong.append("size")
                if wrong:
                    fixes.append(FormatFix(
                        index, "WORD-HEAD-05", "suggest",
                        f"Subsection heading '{text[:50]}': 12 pt italic, left aligned "
                        f"(direct {', '.join(wrong)} removed).",
                        remove_ppr=["w:jc"] if "alignment" in wrong else [],
                        remove_rpr=[t for t, w in (("w:i", "italic"), ("w:iCs", "italic"),
                                                   ("w:sz", "size"), ("w:szCs", "size"))
                                    if w in wrong]))
            if "third" in style_l and next_text is not None and words <= 8:
                findings.append(Finding(
                    check_id="WORD-HEAD-04", severity=Severity.INFO,
                    message=(f"Third-level heading '{text}' is on a line of its own. JACoW "
                             "third-level headings are 10 pt bold and run into the paragraph "
                             "text, followed by an em space."),
                    original=text))
            continue

        if sid in BODY_STYLE_IDS:
            indent = p.paragraph_format.first_line_indent
            if ppr is not None and ppr.find(qn("w:ind")) is not None and (
                    indent is None or abs(indent.twips - _TWIPS_033CM) > 10):
                fixes.append(FormatFix(
                    index, "WORD-PARA-01", "auto",
                    f"'{text[:50]}…': first-line indent restored to 0.33 cm.",
                    remove_ppr=["w:ind"]))
            sizes = {r.font.size.pt for r in p.runs if r.font.size and r.text.strip()}
            if sizes and sizes != {10.0}:
                fixes.append(FormatFix(
                    index, "WORD-PARA-04", "suggest",
                    f"'{text[:50]}…': direct font size {sorted(sizes)} pt removed (10 pt).",
                    remove_rpr=["w:sz", "w:szCs"]))
            # As in the JACoW skill's audit: only widow control switched OFF
            # somewhere in the style chain is a problem; unset inherits Word's.
            widow, _ = _effective(p, "widow_control")
            if widow is False:
                fixes.append(FormatFix(
                    index, "WORD-PARA-02", "auto",
                    f"'{text[:50]}…': widow/orphan control on, so no single line is left "
                    "at the top or bottom of a column.", add_ppr=["w:widowControl"]))
    return fixes, findings


# ---------------------------------------------------------------------------
# Writing tracked formatting changes
# ---------------------------------------------------------------------------

_ids = itertools.count(5000)


def _change_attrs(el, author: str) -> None:
    from docx.oxml.ns import qn
    el.set(qn("w:id"), str(next(_ids)))
    el.set(qn("w:author"), author)
    el.set(qn("w:date"), _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def apply_format_fix(paragraph, spec: dict, author: str) -> int:
    """Apply one fix (as_dict) to *paragraph* as tracked formatting changes."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    changed = 0
    ppr = paragraph._p.get_or_add_pPr()
    snapshot = copy.deepcopy(ppr)
    for tag in ("w:rPr", "w:sectPr", "w:pPrChange"):
        for el in snapshot.findall(qn(tag)):
            snapshot.remove(el)
    if spec.get("set_style"):
        ppr.get_or_add_pStyle().set(qn("w:val"), spec["set_style"])
        changed += 1
    for tag in spec.get("remove_ppr") or []:
        for el in ppr.findall(qn(tag)):
            ppr.remove(el)
            changed += 1
    for tag in spec.get("add_ppr") or []:
        if ppr.find(qn(tag)) is None:
            getattr(ppr, "get_or_add_" + tag.split(":")[1])()
            changed += 1
    if changed:
        for old in ppr.findall(qn("w:pPrChange")):
            ppr.remove(old)
        change = OxmlElement("w:pPrChange")
        _change_attrs(change, author)
        inner = OxmlElement("w:pPr")
        for child in list(snapshot):
            inner.append(child)
        change.append(inner)
        ppr.append(change)

    for run in paragraph._p.iter(qn("w:r")):
        rpr = run.find(qn("w:rPr"))
        if rpr is None:
            continue
        targets = [el for tag in spec.get("remove_rpr") or [] for el in rpr.findall(qn(tag))]
        if not targets:
            continue
        before = copy.deepcopy(rpr)
        for el in before.findall(qn("w:rPrChange")):
            before.remove(el)
        for el in targets:
            rpr.remove(el)
        change = OxmlElement("w:rPrChange")
        _change_attrs(change, author)
        inner = OxmlElement("w:rPr")
        for child in list(before):
            inner.append(child)
        change.append(inner)
        rpr.append(change)
        changed += 1
    return changed
