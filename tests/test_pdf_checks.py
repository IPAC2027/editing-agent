"""PDF checks shared by Word and LaTeX submissions (PDF-*)."""
from __future__ import annotations

from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab")
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from src.checks.pdf_checks import find_author_pdf, run_pdf_checks  # noqa: E402

MM = 72 / 25.4
VERA = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"


def _embedded_font() -> str:
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", str(VERA)))
    return "Vera"


def _clean_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=(595, 792))
    c.setFont(_embedded_font(), 10)
    c.drawString(25 * MM, 792 - 30 * MM, "A JACoW paper inside its margins.")
    c.linkURL("https://doi.org/10.18429/JACoW-IPAC2023-MOPA001",
              (25 * MM, 100, 120 * MM, 112))
    c.drawString(25 * MM, 102, "doi:10.18429/JACoW-IPAC2023-MOPA001")
    c.save()
    return path


def _ids(findings) -> list[str]:
    return sorted(f.check_id for f in findings)


def test_a_clean_jacow_pdf_has_no_findings(tmp_path: Path):
    assert run_pdf_checks(_clean_pdf(tmp_path / "ok.pdf")) == []


def test_each_layout_problem_is_reported(tmp_path: Path):
    path = tmp_path / "bad.pdf"
    c = canvas.Canvas(str(path), pagesize=(595, 842))             # A4
    c.setFont("Helvetica", 10)                                     # standard 14: not embedded
    c.drawString(5 * MM, 842 - 40 * MM, "Text in the left margin")
    c.drawString(297, 842 - 10 * MM, "3")                          # page number at the top
    c.linkURL("https://www.example.org", (25 * MM, 100, 80 * MM, 112))
    c.drawString(25 * MM, 102, "https://www.example.org")
    c.save()

    findings = run_pdf_checks(path)
    ids = _ids(findings)
    assert "PDF-SIZE-01" in ids and any("A4" in f.message for f in findings)
    assert "PDF-MARGIN-01" in ids
    assert "PDF-FONT-01" in ids and any("Helvetica" in f.message for f in findings)
    assert "PDF-LINK-01" in ids and any("example.org" in f.message for f in findings)


def test_a_lone_number_in_the_footer_is_a_page_number_not_a_margin_problem(tmp_path: Path):
    path = tmp_path / "numbered.pdf"
    c = canvas.Canvas(str(path), pagesize=(595, 792))
    c.setFont(_embedded_font(), 10)
    c.drawString(25 * MM, 792 - 30 * MM, "Body text.")
    c.drawString(295, 8 * MM, "2")
    c.save()
    assert _ids(run_pdf_checks(path)) == ["PDF-PAGENUM-01"]


def test_an_unreadable_pdf_says_not_checked(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 this is not a pdf")
    findings = run_pdf_checks(path)
    assert _ids(findings) == ["PDF-00"]
    assert findings[0].message.startswith("NOT CHECKED")


def test_the_author_pdf_is_found_in_the_submission_folder(tmp_path: Path):
    (tmp_path / "PDF").mkdir()
    _clean_pdf(tmp_path / "PDF" / "MOPA001.pdf")
    (tmp_path / "PDF" / "MOPA001_edited.pdf").write_bytes(b"")
    assert find_author_pdf(tmp_path) == tmp_path / "PDF" / "MOPA001.pdf"


def test_word_submissions_get_the_pdf_checks(tmp_path: Path, monkeypatch):
    """Regression: the Word path checked the reference list only."""
    docx = pytest.importorskip("docx")
    from src.workflow.word_prescreen import prescreen_word

    folder = tmp_path / "WRD002-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    (folder / "PDF").mkdir()
    document = docx.Document()
    document.add_paragraph("A Word submission [1].")
    document.add_paragraph("REFERENCES").style = document.styles["Heading 1"]
    document.add_paragraph("[1]\tA. Alpha, \u201cA title\u201d, unpublished.")
    document.save(str(folder / "Source_Files" / "WRD002.docx"))

    c = canvas.Canvas(str(folder / "PDF" / "WRD002.pdf"), pagesize=(595, 842))
    c.setFont(_embedded_font(), 10)
    c.drawString(25 * MM, 842 - 30 * MM, "Body text.")
    c.save()

    result = prescreen_word(folder)
    assert "PDF-SIZE-01" in {f.check_id for f in result.findings}


def test_a_doi_split_across_lines_is_reported(tmp_path: Path):
    path = tmp_path / "split.pdf"
    c = canvas.Canvas(str(path), pagesize=(595, 792))
    c.setFont(_embedded_font(), 9)
    c.drawString(25 * MM, 300, "[1] A. Alpha, “Title”, in Proc. IPAC’23, pp. 1-4. doi:10.18429/JACoW-")
    c.drawString(25 * MM, 288, "IPAC2023-MOPA001")
    c.drawString(25 * MM, 270, "[2] B. Beta, “Title”, 2020. doi:")
    c.drawString(25 * MM, 258, "10.1103/PhysRevLett.1.1")
    uri = "https://doi.org/10.1103/PhysRevAccelBeams.27.011001"
    c.drawString(25 * MM, 240, "[3] C. Gamma, “Title”, 2024. doi:10.1103/PhysRevAccel")
    c.linkURL(uri, (100 * MM, 238, 150 * MM, 249))
    c.drawString(25 * MM, 228, "Beams.27.011001")
    c.linkURL(uri, (25 * MM, 226, 50 * MM, 237))
    c.save()

    found = {f.original for f in run_pdf_checks(path) if f.check_id == "PDF-DOI-01"}
    assert "10.18429/JACoW-" in found
    assert "doi:" in found
    assert "10.1103/PhysRevAccelBeams.27.011001" in found


def test_a_doi_on_one_line_is_not_reported(tmp_path: Path):
    assert not [f for f in run_pdf_checks(_clean_pdf(tmp_path / "ok.pdf"))
                if f.check_id == "PDF-DOI-01"]
