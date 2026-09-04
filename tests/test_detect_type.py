"""Tests for src.refs.detect_type — the 15-way reference-type classifier."""

import pytest

from src.refs.detect_type import detect_type


# ── type flags take precedence ──────────────────────────────────────────────

def test_thesis_flag_wins_over_other_markers():
    assert detect_type({"is_thesis": True}, "T, in Proc. IPAC'23, 2023.") == "thesis"


def test_patent_flag_wins_over_other_markers():
    assert detect_type(
        {"is_patent": True}, "T, Nature, 2020.",
    ) == "patent"


# ── raw-text sentinels ─────────────────────────────────────────────────────

def test_journal_submitted_marker():
    assert detect_type({}, "T, submitted for publication.") == "journal_submitted"


def test_journal_accepted_marker():
    assert detect_type({}, "T, to be published.") == "journal_accepted"


def test_conference_current_marker():
    assert detect_type({}, "T, this conference.") == "conference_current"


def test_conference_unpublished_marker():
    assert detect_type({}, "T, presented at IPAC'23, unpublished.") == "conference_unpublished"


def test_private_comm_marker():
    assert detect_type({}, "A. Smith, private communication, 2023.") == "private_comm"


def test_unpublished_marker():
    assert detect_type({}, "T, unpublished work, 2020.") == "unpublished"


# ── field-based detection ──────────────────────────────────────────────────

def test_conference_field():
    assert detect_type({"conference": "IPAC"}) == "conference_published"


def test_journal_field_via_journal_name():
    assert detect_type({"journal": "Nature"}) == "journal"


def test_journal_field_via_volume():
    """A ref with only ``volume`` (no ``journal``) is still a journal."""
    assert detect_type({"volume": "120"}) == "journal"


def test_arxiv_field():
    assert detect_type({"arxiv_id": "2101.00001"}) == "arxiv"


def test_arxiv_with_journal_still_classifies_as_journal():
    """Published venue takes precedence over arXiv ID."""
    assert detect_type(
        {"arxiv_id": "2101.00001", "journal": "Nature"},
    ) == "journal"


def test_book_chapter():
    assert detect_type(
        {"booktitle": "Handbook of Physics", "editor": "A. Ed"},
    ) == "book_chapter"


def test_book_chapter_with_pages_qualifies():
    assert detect_type(
        {"booktitle": "Handbook of Physics", "pages": "100-150"},
    ) == "book_chapter"


def test_bare_book():
    """booktitle without editor or pages → book (not book_chapter).
    Improvement over the standalone, which falls through to "journal"
    for this case — a ref with a booktitle that isn't a chapter is
    almost always a book reference."""
    assert detect_type(
        {"booktitle": "Handbook of Physics"},
    ) == "book"


def test_book_via_publisher():
    assert detect_type({"publisher": "Springer"}) == "book"


def test_web_via_url():
    assert detect_type({"url": "https://example.com/x"}) == "web"


def test_report_via_rep_id():
    assert detect_type({"rep_id": "CERN-2012-333"}) == "report"


def test_report_via_institution():
    assert detect_type({"institution": "CERN"}) == "report"


def test_report_via_title_keyword():
    assert detect_type(
        {"title": "TRAVEL v4.06 User Manual"},
    ) == "report"


# ── Fallback behaviour ────────────────────────────────────────────────────

def test_unknown_falls_back_to_journal():
    assert detect_type({}) == "journal"
    assert detect_type({}, "completely unstructured text") == "journal"


# ─- Title-quote exclusion ────────────────────────────────────────────────

def test_in_proc_inside_quoted_title_does_not_misclassify():
    """A title like ``\"Studies of in Proc. NAPAC'16 systems\"`` must not
    trigger the conference_unpublished branch."""
    raw = 'A. Smith, "Studies of in Proc. NAPAC\'16 systems", Nature, 2020.'
    assert detect_type({"journal": "Nature"}, raw) == "journal"


def test_submitted_for_publication_inside_quoted_title_does_not_trigger():
    raw = 'A. Smith, "Note: submitted for publication elsewhere", Nature, 2020.'
    assert detect_type({"journal": "Nature"}, raw) == "journal"
