"""Title, author and unit checks for Word submissions.

Regression: Word papers got reference checks only; LaTeX papers got title,
author and unit checks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.checks import word_front_checks as wf

NBSP = "\u00a0"


def _ids(findings):
    return sorted(f.check_id for f in findings)


def test_a_title_case_title_is_reported_with_its_units_kept():
    findings = wf.check_title("Commissioning of a 3 GeV Booster at SPring-8*")
    assert _ids(findings) == ["WORD-TITLE-01"]
    assert findings[0].suggested == "COMMISSIONING OF A 3 GeV BOOSTER AT SPring-8"


def test_a_correct_title_passes():
    assert wf.check_title("DESIGN OF A 1.3 GHz SRF CRYOMODULE FOR THE JACoW LINAC*") == []
    assert wf.check_title("A 5 mm APERTURE FOR SwissFEL") == []


def test_title_punctuation_is_reported():
    assert "FMT-TITLE-02" in _ids(wf.check_title("A TITLE WITH A PERIOD.*"))


def test_author_line_rules():
    ids = _ids(wf.check_authors("A. N. Primary-author†, B. Coauthor, and C. Contributor"))
    assert ids == ["WORD-AUTH-02"]
    findings = wf.check_authors("Kim Moreau†, A. Brandt1,2, H. Nakamura")
    assert _ids(findings) == ["FMT-AUTH-01"] and "Kim Moreau" in findings[0].message
    assert wf.check_authors("R. Okafor†, L. Ashworth, M. Duval, T. Vance") == []


def test_units_spacing_and_case():
    paragraphs = [f"The beam is accelerated from 150 MeV to 3{NBSP}GeV at 1.3GHz.",
                  f"Gradient of 16{NBSP}Mv/m and 250 Kev; see Fig. 2 A and Table 3 K."]
    findings = wf.check_units(paragraphs)
    spacing = [f for f in findings if f.check_id == "WORD-UNIT-01"]
    casing = {f.original: f.suggested for f in findings if f.check_id == "WORD-UNIT-02"}
    assert len(spacing) == 1 and "'150 MeV'" in spacing[0].message and "1.3GHz" in spacing[0].message
    assert "3\u00a0GeV" not in spacing[0].message
    assert casing == {"250 Kev": f"250{NBSP}keV"}                 # Mv is ambiguous (mV/MV)
    assert "2 A" not in spacing[0].message and "3 K" not in spacing[0].message


def test_front_matter_is_read_from_jacow_styles(tmp_path: Path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Commissioning of a Booster*", style="Title")
    document.add_paragraph("R. Okafor, and T. Vance")
    document.add_paragraph("Body at 3 GeV.")
    document.add_paragraph("REFERENCES")
    document.add_paragraph("[1] Not body 5 MeV.")
    path = tmp_path / "paper.docx"
    document.save(str(path))

    front = wf.read_front_matter(path)
    assert front.title == "Commissioning of a Booster*"
    assert front.author_line == "R. Okafor, and T. Vance"
    assert not any("5 MeV" in p for p in front.body)
    assert _ids(wf.run_all(path)) == ["WORD-AUTH-02", "WORD-TITLE-01", "WORD-UNIT-01"]


def test_the_affiliation_is_not_part_of_the_author_list():
    """Regression (test run): author and affiliation in one paragraph, split by a
    line break, were read as six 'authors' and an 'and' in the institute name."""
    para = ("H.P. Alpha\u2020\nInstitute for Beam Physics and Technology, "
            "Example University, Springfield, ST, USA")
    assert wf.author_part(para) == "H.P. Alpha\u2020"
    assert wf.check_authors(wf.author_part(para)) == []
    same_line = "A. Alpha, B. Beta, Institute for Beam Physics and Technology, College Park"
    assert wf.author_part(same_line) == "A. Alpha, B. Beta"
    assert wf.author_part("A. Alpha\u2020, B. Beta, C. Gamma") == "A. Alpha\u2020, B. Beta, C. Gamma"


def test_a_group_the_author_speaks_for_is_not_an_author():
    """Regression (test run): 'M. Kappa, for XYZG' reported 'for XYZG' as a name."""
    assert wf.author_part("M.\u00a0Kappa, for XYZG ") == "M.\u00a0Kappa"
    assert wf.author_part("A. Alpha on behalf of the MICE collaboration") == "A. Alpha"
    assert wf.check_authors(wf.author_part("M.\u00a0Kappa, for XYZG ")) == []
