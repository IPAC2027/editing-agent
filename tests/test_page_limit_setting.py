"""The page limit is a conference setting, not a constant."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("reportlab")
from reportlab.pdfgen import canvas  # noqa: E402

from src.checks import layout_checks  # noqa: E402
from src.models import Paper  # noqa: E402


def _pdf(path: Path, pages: int, refs_on: int) -> Path:
    c = canvas.Canvas(str(path), pagesize=(595, 792))
    for number in range(1, pages + 1):
        c.drawString(72, 700, "INTRODUCTION" if number == 1 else "Body text")
        if number == refs_on:
            c.drawString(72, 400, "REFERENCES")
        c.showPage()
    c.save()
    return path


def _ids(paper: Paper) -> list[str]:
    return [f.check_id for f in paper.findings]


def test_the_default_is_three_body_pages(tmp_path, monkeypatch):
    monkeypatch.delenv("JACOW_BODY_PAGES", raising=False)
    paper = Paper(paper_id="X", source_path=tmp_path / "x.tex")
    layout_checks.check_page_limit(paper, _pdf(tmp_path / "a.pdf", 5, 4))
    assert _ids(paper) == ["PAGE-LIMIT-01"]


def test_a_conference_with_four_body_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("JACOW_BODY_PAGES", "4")
    paper = Paper(paper_id="X", source_path=tmp_path / "x.tex")
    layout_checks.check_page_limit(paper, _pdf(tmp_path / "b.pdf", 5, 4))
    assert _ids(paper) == []
    layout_checks.check_page_limit(paper, _pdf(tmp_path / "c.pdf", 5, 5))
    assert _ids(paper) == ["PAGE-LIMIT-01"] and "page 5" in paper.findings[0].message


def test_an_unreadable_pdf_is_not_a_pass(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    paper = Paper(paper_id="X", source_path=tmp_path / "x.tex")
    layout_checks.check_page_limit(paper, bad)
    assert paper.findings and paper.findings[0].message.startswith("NOT CHECKED")
