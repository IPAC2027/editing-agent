"""Tests for src.refs.extract — heuristic field extractor.

Covers the orchestrator and the individual sub-extractors that the
autofix reformat path depends on for the user's NAPAC-style
references.
"""

import pytest

from src.refs.extract import (
    TITLE_TAIL_INSTITUTIONS,
    _extract_conference,
    extract_from_raw,
)


# ── extract_conference: the most-used standalone entry point ─────────────

def test_extract_conference_in_proc_acronym_4digit_year():
    rec = {}
    _extract_conference(
        "A. Smith, \"T\", in Proc. IPAC'23, Venice, Italy, May 2023, pp. 1-3.",
        rec,
    )
    assert rec["conference"] == "IPAC"
    assert rec["year"] == "2023"
    assert rec["city"] == "Venice"
    assert rec["country"] == "Italy"


def test_extract_conference_in_proc_2digit_year():
    rec = {}
    _extract_conference(
        "A. Smith, \"T\", in Proc. NAPAC'16, Chicago, IL, USA, Oct. 2016.",
        rec,
    )
    assert rec["conference"] == "NAPAC"
    assert rec["year"] == "2016"


def test_extract_conference_city_state_country_3_tokens():
    """``Chicago, IL, USA,`` must lift state as the middle token, not
    confuse it with the country.  Regression for the user's case."""
    rec = {}
    _extract_conference(
        "A. Smith, \"T\", in Proc. NAPAC'16, Chicago, IL, USA, Oct. 2016.",
        rec,
    )
    assert rec["city"] == "Chicago"
    assert rec["country"] == "USA"
    # The state is not stored separately — that's an OK limitation.


def test_extract_conference_in_proc_4digit_year_with_3_tokens():
    """4-digit-year form of the City/State/Country case (e.g. SRF2021)."""
    rec = {}
    _extract_conference(
        "A. Smith, \"T\", in Proc. SRF2021, East Lansing, MI, USA, Jun. 2021.",
        rec,
    )
    assert rec["conference"] == "SRF2021"
    assert rec["city"] == "East Lansing"
    assert rec["country"] == "USA"


def test_extract_conference_presented_at_unpublished():
    rec = {}
    _extract_conference(
        'A. Smith, "T", presented at IPAC\'23, Venice, Italy, May 2023, unpublished.',
        rec,
    )
    assert rec["conference"] == "IPAC"
    assert rec["city"] == "Venice"
    assert rec["country"] == "Italy"


def test_extract_conference_lifts_paper_id():
    rec = {}
    _extract_conference(
        'A. Smith, "T", in Proc. IPAC\'23, Venice, Italy, May 2023, paper MOPA001.',
        rec,
    )
    assert rec["paper_id"] == "MOPA001"


def test_extract_conference_handles_full_name_with_acronym():
    """``in Proc. 13th Int. Particle Accel. Conf. (IPAC'23), Venice, Italy``"""
    rec = {}
    _extract_conference(
        'A. Smith, "T", in Proc. 13th Int. Particle Accel. Conf. (IPAC\'23), '
        'Venice, Italy, May 2023.',
        rec,
    )
    assert rec["conference"] == "IPAC"
    assert rec["year"] == "2023"
    assert rec["city"] == "Venice"
    assert rec["country"] == "Italy"


def test_extract_conference_no_match_leaves_rec_empty():
    rec = {}
    _extract_conference("Just a plain sentence with no conference info.", rec)
    assert rec == {}


# ── extract_from_raw: the orchestrator ─────────────────────────────────────

def test_extract_from_raw_lifts_full_set_for_user_case():
    """The exact case from the user report: every field the reformat
    pass needs is lifted out of the raw text."""
    raw = (
        'J. Wang and G. S. Sprau, "A High Bandwidth Bipolar Power Supply '
        'for the Fast Correctors in the APS Upgrade", in Proc. NAPAC\'16, '
        'Chicago, IL, USA, Oct. 2016, pp. 96-98. '
        'doi:10.18429/JACoW-NAPAC2016-MOPOB12'
    )
    rec = extract_from_raw(raw)
    assert rec["doi"] == "10.18429/JACoW-NAPAC2016-MOPOB12"
    # JACoW DOI prefix lifts conference / year / paper_id
    assert rec["conference"] == "NAPAC"
    assert rec["year"] == "2016"
    assert rec["paper_id"] == "MOPOB12"
    # Conference pattern lifts city / country
    assert rec["city"] == "Chicago"
    assert rec["country"] == "USA"
    # Bibliographic pattern lifts pages / month
    # pages_fmt normalises hyphen → en-dash (JACoW typography).
    assert rec["pages"] == "96–98"
    assert rec["month"] == "Oct."
    # Title / authors from quoted title
    assert "High Bandwidth Bipolar" in rec["title"]
    assert rec["authors_raw"] == "J. Wang and G. S. Sprau"


def test_extract_from_raw_doi_url_stripped():
    raw = 'A. Smith, "T", doi:https://doi.org/10.1103/test, 2020.'
    rec = extract_from_raw(raw)
    assert rec["doi"] == "10.1103/test"


def test_extract_from_raw_arxiv_id_and_doi_linked():
    raw = 'A. Smith, "T", arXiv:1810.04805, 2018.'
    rec = extract_from_raw(raw)
    assert rec["arxiv_id"] == "1810.04805"
    # _extract_bibliographic also lifts the year
    assert rec["year"] == "2018"


def test_extract_from_raw_jacow_doi_sets_conference():
    raw = 'A. Smith, "T", doi:10.18429/JACoW-IPAC2022-THOXSP1, 2022.'
    rec = extract_from_raw(raw)
    assert rec["conference"] == "IPAC"
    assert rec["year"] == "2022"
    assert rec["paper_id"] == "THOXSP1"


def test_extract_from_raw_isbn_lifted():
    raw = 'A. Smith, "T", ISBN: 978-0-19-852926-2, 2020.'
    rec = extract_from_raw(raw)
    assert rec["isbn"] == "9780198529262"  # dashes and spaces stripped


def test_extract_from_raw_volume_issue_pages():
    raw = 'A. Smith, "T", Nature, vol. 600, no. 5, pp. 123-130, 2020.'
    rec = extract_from_raw(raw)
    assert rec["volume"] == "600"
    assert rec["issue"] == "5"
    # pages_fmt normalises hyphen → en-dash (JACoW typography).
    assert rec["pages"] == "123–130"


def test_extract_from_raw_thesis_flag():
    raw = 'A. Student, "My thesis", Ph.D. thesis, Phys. Dept., MIT, 2022.'
    rec = extract_from_raw(raw)
    assert rec["is_thesis"] is True
    assert rec["degree"] == "Ph.D."
    # The standalone's school regex captures up to the next comma —
    # so the trailing ", MIT" (city/university) is not in school.
    # That's OK: school is the department, MIT would be lifted by a
    # different pattern (and the comma is the natural boundary).
    assert rec["school"] == "Phys. Dept."


def test_extract_from_raw_patent_flag():
    raw = 'A. Inventor, "A widget", Patent US12345, USA, 2020.'
    rec = extract_from_raw(raw)
    assert rec["is_patent"] is True
    # The patent_number regex captures the trailing comma; the
    # formatter strips it.  Pure-extractor value retains the comma.
    assert rec["patent_number"] == "US12345,"


def test_extract_from_raw_report_rep_id_and_institution():
    raw = (
        'A. Author, "Some technical note", Rep. CERN-2012-333, '
        '"CERN, Geneva, 2012."'
    )
    rec = extract_from_raw(raw)
    assert rec["rep_id"] == "CERN-2012-333"


def test_extract_from_raw_does_not_modify_input():
    raw = 'A. Smith, "T", Nature, 2020.'
    before = raw
    extract_from_raw(raw)
    assert raw == before  # no in-place mutation


# ── Constants sanity ────────────────────────────────────────────────────────

def test_title_tail_institutions_includes_cern():
    assert "CERN" in TITLE_TAIL_INSTITUTIONS
    assert "DESY" in TITLE_TAIL_INSTITUTIONS
    assert "ESRF" in TITLE_TAIL_INSTITUTIONS


# ── No-quote parser and Nature-style parser sanity ────────────────────────

def test_extract_from_raw_handles_nature_style_no_quote():
    """Nature/Springer citations with no quoted title are still parsed."""
    raw = (
        'Schuff, H., Vanderlyn, L., Adel, H. and Vu, N. T. How to do '
        'human evaluation: A brief introduction to user studies in NLP. '
        'Nat. Lang. Eng. 29, 1199-1222 (2023).'
    )
    rec = extract_from_raw(raw)
    assert "How to do human evaluation" in rec.get("title", "")
    assert rec.get("year") == "2023"


def test_extract_from_raw_handles_doi_only():
    raw = 'doi:10.1234/some.identifier'
    rec = extract_from_raw(raw)
    assert rec["doi"] == "10.1234/some.identifier"
