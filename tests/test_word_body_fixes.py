"""Main-text corrections in Word papers, written as tracked changes.

Regression (test run, Oct 2026): the main-text checks were reported but nothing
was changed in the Word file — "[8][9]" and "14 T" stayed as they were.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
NBSP = "\u00a0"


def _paper(tmp_path: Path) -> Path:
    folder = tmp_path / "TXT001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    d = docx.Document()
    d.add_paragraph("Commissioning of a 3 GeV Booster.", style="Title")
    d.add_paragraph("A. Alpha and B. Beta")
    d.add_paragraph("Abstract")
    d.add_paragraph("The Large Booster (LB) works at 14 T and 1.9 K [1].")
    d.add_paragraph("1. Introduction", style="Heading 1")
    d.add_paragraph("beam dynamics and optics", style="Heading 2")
    d.add_paragraph("The LB is described in [1][2]. Fig. 1 shows it. See Tab. 1 and equation 1, "
                    "at 90 TeV and 250 Gev.")
    d.add_paragraph("Figure 1 - The layout of the booster")
    d.add_paragraph("Table 1: Main Parameters.")
    d.add_paragraph("REFERENCES")
    d.add_paragraph("[1] A. Alpha, “Title”, 2020.")
    d.add_paragraph("[2] B. Beta, “Title”, 2021.")
    d.save(str(folder / "Source_Files" / "TXT001.docx"))
    return folder


@pytest.fixture
def screened(tmp_path, monkeypatch):
    monkeypatch.setenv("AIAGENT_OFFLINE", "1")
    from src.workflow.word_prescreen import prescreen_word
    folder = _paper(tmp_path)
    prescreen_word(folder)
    out = folder / "aiagent_prescreen"
    data = json.loads((out / "word_edits.json").read_text(encoding="utf-8"))
    corrections = data if isinstance(data, list) else data.get("edits", data.get("corrections", []))
    return folder, [c for c in corrections if c.get("spans")]


def _by_check(corrections):
    found = {}
    for c in corrections:
        found.setdefault(c["check_id"], []).append(c)
    return found


def test_mechanical_fixes_are_automatic(screened):
    _, body = screened
    found = _by_check(body)
    assert {c["tier"] for c in found["WORD-UNIT-01"]} == {"auto"}
    assert len(found["WORD-UNIT-01"]) >= 4                      # 14 T, 1.9 K, 90 TeV, 250 Gev
    assert found["TXT-CITE-01"][0]["spans"][0]["after"] == "[1, 2]"
    assert found["TXT-TAB-01"][0]["tier"] == "auto"
    assert found["TXT-FIG-01"][0]["spans"][0]["after"] == "Figure"


def test_judgement_fixes_are_suggestions(screened):
    _, body = screened
    found = _by_check(body)
    for check in ("WORD-UNIT-02", "TXT-EQ-01", "WORD-TITLE-01", "FMT-TITLE-02",
                  "WORD-AUTH-02", "WORD-HEAD-01", "WORD-HEAD-02", "WORD-CAP-01",
                  "WORD-CAP-02", "WORD-CAP-03"):
        assert check in found, check
        assert {c["tier"] for c in found[check]} == {"suggest"}, check
    assert found["WORD-UNIT-02"][0]["spans"][0]["after"] == "GeV"
    assert found["WORD-HEAD-02"][0]["spans"][0]["after"] == "Beam Dynamics and Optics"
    assert found["WORD-CAP-01"][0]["spans"][0]["after"] == "Figure 1: "


def test_the_tracked_file_carries_the_main_text_fixes(screened):
    folder, _ = screened
    tracked = next((folder / "aiagent_prescreen").glob("*_tracked.docx"))
    xml = zipfile.ZipFile(tracked).read("word/document.xml").decode()
    import re
    accepted = re.sub(r"<w:del\b.*?</w:del>", "", xml, flags=re.DOTALL)
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", accepted))
    assert "[1, 2]" in text and f"14{NBSP}T" in text and "See Table" in text
    assert "<w:ins " in xml


def test_the_desk_merges_accepted_fixes_in_one_paragraph(tmp_path):
    from src.desk import paper as desk_paper

    before = "See Tab. 1 at 90 TeV [1][2]."
    accepted = [
        {"id": "W001", "tier": "auto", "check_id": "TXT-TAB-01", "paragraph_index": 3, "before": before,
         "after": before, "spans": [{"start": 4, "end": 8, "after": "Table"}], "more": []},
        {"id": "W002", "tier": "auto", "check_id": "WORD-UNIT-01", "paragraph_index": 3, "before": before,
         "after": before, "spans": [{"start": 16, "end": 17, "after": NBSP}], "more": []},
    ]
    merged = before
    for span in sorted([s for c in accepted for s in c["spans"]], key=lambda s: s["start"], reverse=True):
        merged = merged[:span["start"]] + span["after"] + merged[span["end"]:]
    assert merged == f"See Table 1 at 90{NBSP}TeV [1][2]."
    assert hasattr(desk_paper, "_write_reviewed_docx")


def test_finishing_writes_only_the_accepted_main_text_fixes(screened):
    """The reviewed file has every automatic fix and the accepted suggestions."""
    import re

    from src.desk.paper import Paper, _write_reviewed_docx

    folder, body = screened
    paper = Paper(folder)
    eq = next(c for c in body if c["check_id"] == "TXT-EQ-01")
    unit = next(c for c in body if c["check_id"] == "WORD-UNIT-02")
    paper.state.decide(eq["id"], "accepted")
    paper.state.decide(unit["id"], "rejected")
    written = _write_reviewed_docx(paper)
    reviewed = folder / "aiagent_prescreen" / written[0]
    xml = zipfile.ZipFile(reviewed).read("word/document.xml").decode()
    accepted = re.sub(r"<w:del\b.*?</w:del>", "", xml, flags=re.DOTALL)
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", accepted))
    assert "[1, 2]" in text and "See Table" in text           # automatic, applied
    assert f"Eq.{NBSP}(1)" in text                             # suggestion, accepted
    assert "250\u00a0Gev" in text                              # case fix rejected, NBSP kept


def test_the_title_is_one_suggestion_and_given_names_become_initials():
    from src.autofix.word_body_fixes import _author_fixes, _Para, _title_fixes
    from src.autofix.word_body_fixes import apply_fixes
    text = "Commissioning of a 3 GeV Booster at SPring-8*"
    title = _title_fixes(_Para(0, text, "Title", True))
    assert len(title) == 1
    assert apply_fixes(text, title) == "COMMISSIONING OF A 3 GeV BOOSTER AT SPring-8*"
    authors = _author_fixes(_Para(1, "R. Okafor\u2020, T. Vance and Michael Duval", "Author", True))
    assert {(f.check_id, f.after) for f in authors} == {("WORD-AUTH-02", ", "), ("FMT-AUTH-01", "M.")}
    assert not [f for f in _author_fixes(_Para(1, "Zhang Wei, A. Alpha", "Author", True))
                if f.check_id == "FMT-AUTH-01"]
