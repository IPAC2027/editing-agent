"""References whose DOI or URL is on a line of its own (test run, Oct 2026).

Every reference in that paper had its link in the paragraph below.  The link
lines were treated as separate entries and lost; once attached, the corrections
spanned two paragraphs and could not be written as tracked changes.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")


def _paper(tmp_path: Path) -> Path:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    folder = tmp_path / "LNK001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    d = docx.Document()
    d.add_paragraph("A TITLE", style="Title")
    d.add_paragraph("A. Alpha")
    d.add_paragraph("Text [1], [2].")
    d.add_paragraph("REFERENCES")
    d.add_paragraph("[1] N. Editor (ed.), “Accelerator Roadmap for a Future "
                    "R&D Roadmap”, CERN-2022-001, 2022.")
    link = d.add_paragraph()
    r_id = link.part.relate_to("https://doi.org/10.23731/CYRM-2099-001", RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), r_id)
    run = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = "https://doi.org/10.23731/CYRM-2099-001"
    run.append(t); h.append(run); link._p.append(h)
    d.add_paragraph("[2] G.Alpha, P.McBeta, „RF developments for a future collider “, 2025.")
    d.add_paragraph("https://indico.cern.ch/event/1000000/contributions/2000000/ ")
    d.save(str(folder / "Source_Files" / "LNK001.docx"))
    return folder


def test_link_lines_belong_to_their_reference(tmp_path):
    from src.parser.word_parser import parse_word
    pw = parse_word(_paper(tmp_path) / "Source_Files" / "LNK001.docx")
    assert [r.n for r in pw.references] == [1, 2]
    assert pw.references[0].doi == "10.23731/CYRM-2099-001"
    assert pw.references[1].raw_text.endswith("contributions/2000000/")


def test_both_paragraphs_are_written_as_tracked_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIAGENT_OFFLINE", "1")
    from src.workflow.word_prescreen import prescreen_word
    folder = _paper(tmp_path)
    result = prescreen_word(folder)
    assert not [f for f in result.findings if f.check_id == "WORD-TRACK-01"]
    tracked = next((folder / "aiagent_prescreen").glob("*_tracked.docx"))
    xml = zipfile.ZipFile(tracked).read("word/document.xml").decode()
    # The DOI line: old URL deleted, "doi:…" inserted inside a hyperlink.
    assert "https://doi.org/10.23731/CYRM-2099-001</w:delText>" in xml
    assert "<w:hyperlink" in xml and "doi:10.23731/CYRM-2099-001" in xml
    # The plain URL line is left alone: no full stop added to it.
    assert "2000000/.</w:t>" not in xml
