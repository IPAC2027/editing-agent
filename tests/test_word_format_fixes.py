"""Paragraph and heading layout as tracked formatting changes (test run, Oct 2026).

Body text set in 'Normal' or a subsection-heading style, first-line indents
overridden to 0, headings not kept with their text — all of which the
editor's copy of a test paper showed — become tracked formatting changes.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
from docx.enum.style import WD_STYLE_TYPE  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

LONG = ("The High-Field Magnet Programme is developing magnets for future colliders, with "
        "a focus on niobium-tin conductors and high-temperature superconductors at CERN.")


def _doc(tmp_path: Path) -> Path:
    d = docx.Document()
    body = d.styles.add_style("JACoW_Body Text Indent", WD_STYLE_TYPE.PARAGRAPH)
    body.element.set(qn("w:styleId"), "JACoWBodyTextIndent")
    body.paragraph_format.first_line_indent = Cm(0.33)
    body.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    sub = d.styles.add_style("JACoW_Subsection Heading", WD_STYLE_TYPE.PARAGRAPH)
    sub.font.italic = True
    sub.font.size = Pt(12)
    d.add_paragraph("A TITLE", style="Title")
    d.add_paragraph("Abstract")
    d.add_paragraph("Results", style="JACoW_Subsection Heading")          # 1: not kept with next
    p = d.add_paragraph(LONG, style="JACoW_Body Text Indent")             # indent overridden
    p.paragraph_format.first_line_indent = Cm(0)
    d.add_paragraph(LONG, style="Normal")                                 # body text in Normal
    h = d.add_paragraph(LONG, style="JACoW_Subsection Heading")           # body text in heading
    for run in h.runs:
        run.font.italic = False
        run.font.size = Pt(10)
    d.add_paragraph("REFERENCES")
    path = tmp_path / "f.docx"
    d.save(str(path))
    return path


def test_layout_problems_become_fixes(tmp_path):
    from src.autofix.word_format_fixes import format_fixes
    fixes, _ = format_fixes(_doc(tmp_path))
    found = {(f.check_id, f.tier) for f in fixes}
    assert ("WORD-HEAD-03", "auto") in found
    assert ("WORD-PARA-01", "auto") in found
    assert sum(1 for f in fixes if f.check_id == "WORD-PARA-03") == 2     # Normal + heading style
    restyle = next(f for f in fixes if f.check_id == "WORD-PARA-03")
    assert restyle.set_style == "JACoWBodyTextIndent" and "w:i" in restyle.remove_rpr


def test_fixes_are_tracked_formatting_changes(tmp_path):
    from src.autofix.word_format_fixes import format_fixes
    from src.output.docx_tracked import write_tracked_docx
    source = _doc(tmp_path)
    fixes, _ = format_fixes(source)
    out = tmp_path / "out.docx"
    write_tracked_docx(source, out, [], [(f.paragraph_index, f.as_dict(), "test") for f in fixes])
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert xml.count("<w:pPrChange") == len({f.paragraph_index for f in fixes if f.set_style or f.remove_ppr or f.add_ppr})
    assert "<w:rPrChange" in xml
    reread = docx.Document(str(out))
    restyled = [p for p in reread.paragraphs if p.text == LONG]
    assert all(p.style.style_id == "JACoWBodyTextIndent" for p in restyled)
    assert all(p.paragraph_format.first_line_indent is None for p in restyled)  # style's 0.33 cm applies
