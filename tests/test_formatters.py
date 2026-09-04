"""Tests for src.refs.formatters (adapted from TestReferenceTypes / formatter tests)."""

import pytest

from src.refs.formatters import FORMATTERS, format_ref, split_refs


# ── Per-type formatters ──────────────────────────────────────────────────────

def test_journal_basic():
    rec = {
        "authors_raw": "A. Smith",
        "title": "Beam dynamics studies",
        "journal": "Phys. Rev. Lett.",
        "volume": "120",
        "issue": "5",
        "pages": "1–5",
        "year": "2020",
    }
    out = format_ref(rec, "journal")
    assert 'A. Smith, "Beam dynamics studies"' in out
    assert "Phys. Rev. Lett." in out
    assert "vol. 120" in out
    assert "no. 5" in out
    assert "pp. 1–5" in out
    assert "2020" in out


def test_journal_with_doi_indented_continuation():
    rec = {
        "authors_raw": "A. Smith", "title": "T",
        "journal": "Nature", "year": "2024",
        "doi": "10.1038/test",
    }
    out = format_ref(rec, "journal")
    assert "\n  doi:10.1038/test" in out  # 2-space indent preserved


def test_arxiv_contains_arxiv_id():
    rec = {
        "authors_raw": "A. Smith",
        "title": "A preprint", "year": "2021",
        "arxiv_id": "2101.00001",
    }
    out = format_ref(rec, "arxiv")
    assert "arXiv:2101.00001" in out
    # default DOI is derived from arxiv_id
    assert "10.48550/arXiv.2101.00001" in out


def test_arxiv_with_explicit_doi():
    rec = {
        "authors_raw": "A. Smith", "title": "T", "year": "2021",
        "arxiv_id": "2101.00001", "doi": "10.1234/explicit",
    }
    out = format_ref(rec, "arxiv")
    assert "10.1234/explicit" in out
    assert "10.48550/arXiv" not in out


def test_thesis_includes_degree():
    rec = {
        "authors_raw": "G. Student", "title": "A thesis",
        "year": "2021", "degree": "Ph.D.", "school": "CERN",
    }
    out = format_ref(rec, "thesis")
    assert "Ph.D. thesis" in out
    assert "CERN" in out


def test_thesis_with_doi():
    rec = {
        "authors_raw": "A. Grad", "title": "My Thesis",
        "year": "2023", "degree": "Ph.D.", "school": "CERN",
        "doi": "10.1234/thesis.001",
    }
    out = format_ref(rec, "thesis")
    assert "10.1234/thesis.001" in out


def test_thesis_without_doi_omits_doi_field():
    rec = {
        "authors_raw": "A. Grad", "title": "My Thesis",
        "year": "2023", "degree": "Ph.D.", "school": "CERN",
    }
    out = format_ref(rec, "thesis")
    assert "doi:" not in out


def test_thesis_default_degree_phd():
    rec = {
        "authors_raw": "A. S", "title": "T", "year": "2020", "school": "MIT",
    }
    out = format_ref(rec, "thesis")
    assert "Ph.D." in out


def test_report_with_doi():
    rec = {
        "authors_raw": "A. Author", "title": "Tech Note",
        "year": "2022", "institution": "CERN",
        "rep_id": "CERN-2022-001", "doi": "10.1234/cern.rep",
    }
    out = format_ref(rec, "report")
    assert "10.1234/cern.rep" in out
    assert "CERN-2022-001" in out


def test_report_without_doi():
    rec = {
        "authors_raw": "A. Author", "title": "Tech Note",
        "year": "2022", "institution": "CERN",
        "rep_id": "CERN-2022-001",
    }
    out = format_ref(rec, "report")
    assert "doi:" not in out


def test_conference_published_basic():
    rec = {
        "authors_raw": "A. S", "title": "A conf paper",
        "year": "2023", "conference": "IPAC",
        "city": "Venice", "country": "Italy",
        "pages": "1–3", "month": "May",
    }
    out = format_ref(rec, "conference_published")
    assert "IPAC'23" in out
    assert "Venice" in out
    assert "Italy" in out
    assert "May 2023" in out


def test_conference_published_strips_existing_year_suffix():
    """Regression: 'IPAC'24' input must not become 'IPAC'24'24'."""
    rec = {
        "authors_raw": "A. S", "title": "T",
        "year": "2024", "conference": "IPAC'24",
    }
    out = format_ref(rec, "conference_published")
    assert "IPAC'24'24" not in out
    assert "IPAC'24" in out


def test_conference_unpublished_includes_paper_id():
    rec = {
        "authors_raw": "A. S", "title": "T",
        "year": "2023", "conference": "IPAC",
        "paper_id": "MOPA001",
    }
    out = format_ref(rec, "conference_unpublished")
    assert "paper MOPA001" in out
    assert "unpublished" in out


def test_conference_current_says_this_conference():
    rec = {
        "authors_raw": "A. S", "title": "T",
        "year": "2023", "conference": "IPAC",
    }
    out = format_ref(rec, "conference_current")
    assert "this conference" in out


def test_book_no_quotes_around_title():
    rec = {
        "authors_raw": "A. S", "title": "Accelerator Physics",
        "year": "2018", "publisher": "World Scientific",
        "city": "Singapore",
    }
    out = format_ref(rec, "book")
    assert "World Scientific" in out
    assert "Singapore" in out
    # Book title is NOT wrapped in quotes
    assert '"Accelerator Physics"' not in out


def test_book_chapter_format():
    rec = {
        "authors_raw": "A. Author", "title": "Beam optics",
        "booktitle": "Handbook of Accelerator Physics",
        "editor": "B. Editor",
        "city": "Singapore", "publisher": "World Scientific",
        "year": "2018", "pages": "100–150",
    }
    out = format_ref(rec, "book_chapter")
    assert '"Beam optics"' in out         # chapter title quoted + sent-cased
    assert "in Handbook" in out
    assert "B. Editor, Ed." in out
    assert "Singapore: World Scientific" in out


def test_arxiv_with_category_tag():
    rec = {
        "authors_raw": "A. S", "title": "T",
        "year": "2021", "arxiv_id": "2101.00001", "arxiv_cat": "cs.LG",
    }
    out = format_ref(rec, "arxiv")
    assert "[cs.LG]" in out


def test_web_with_accessed_date():
    rec = {
        "authors_raw": "CERN", "title": "LHC",
        "year": "2023", "url": "https://home.cern/lhc",
        "accessed": "01-Jun-2023",
    }
    out = format_ref(rec, "web")
    assert "accessed: 01-Jun-2023" in out
    assert "https://home.cern/lhc" in out


def test_patent_basic():
    rec = {
        "authors_raw": "A. Inventor", "title": "Widget",
        "country": "USA", "patent_number": "12345",
        "year": "2020",
    }
    out = format_ref(rec, "patent")
    assert "Patent 12345" in out
    assert "USA" in out


def test_unpublished_minimal():
    rec = {"authors_raw": "A. S", "title": "T"}
    out = format_ref(rec, "unpublished")
    assert "unpublished" in out


def test_private_comm():
    rec = {"authors_raw": "A. S", "year": "2023", "month": "Jan."}
    out = format_ref(rec, "private_comm")
    assert "private communication" in out
    assert "2023" in out


def test_journal_accepted():
    rec = {"authors_raw": "A. S", "title": "T", "journal": "Nature"}
    out = format_ref(rec, "journal_accepted")
    assert "to be published" in out
    assert "Nature" in out


def test_journal_submitted():
    rec = {"authors_raw": "A. S", "title": "T"}
    out = format_ref(rec, "journal_submitted")
    assert "submitted for publication" in out


def test_format_ref_unknown_type_falls_back_to_journal():
    rec = {"authors_raw": "A. S", "title": "T", "year": "2020"}
    # Should not raise — falls back to _fmt_journal
    out = format_ref(rec, "totally_unknown_type")
    assert "A. S" in out


def test_formatters_table_has_15_entries():
    # Sanity check: the migrated dispatch table covers all the script's types.
    assert len(FORMATTERS) == 15


def test_format_ref_normalises_whitespace():
    rec = {
        "authors_raw": "A. S", "title": "T",
        "journal": "Nature", "year": "2020", "doi": "10.1/x",
    }
    out = format_ref(rec, "journal")
    # No double spaces on the main line
    main_line = out.split("\n")[0]
    assert "  " not in main_line


def test_format_ref_comma_after_period_collapsed():
    """',.' artefact (e.g. when a field is empty) must be cleaned up."""
    rec = {"authors_raw": "A. S", "title": "T", "year": "2020"}
    out = format_ref(rec, "journal")
    assert ",." not in out


# ── canonicalize_ref_type / REF_TYPE_ALIASES ───────────────────────────────

import pytest

from src.refs.formatters import (
    REF_TYPE_ALIASES,
    canonicalize_ref_type,
)


def test_canonicalize_maps_proceedings_aliases():
    """The dispatch used to miss 'proceedings' entirely, causing
    format_ref() to fall through to the journal formatter and silently
    drop the 'in Proc. ...' line.  Now mapped to conference_published."""
    assert canonicalize_ref_type("proceedings") == "conference_published"
    assert canonicalize_ref_type("proceedings_published") == "conference_published"
    assert canonicalize_ref_type("proceedings_unpublished") == "conference_unpublished"
    assert canonicalize_ref_type("proceedings_current") == "conference_current"


def test_canonicalize_maps_other_legacy_aliases():
    assert canonicalize_ref_type("conference") == "conference_published"
    assert canonicalize_ref_type("online") == "web"
    assert canonicalize_ref_type("phdthesis") == "thesis"
    assert canonicalize_ref_type("mastersthesis") == "thesis"


def test_canonicalize_passes_through_canonical_names():
    """Canonical names (already in FORMATTERS) pass through unchanged."""
    for name in (
        "journal", "journal_accepted", "journal_submitted",
        "conference_published", "conference_unpublished", "conference_current",
        "arxiv", "web", "book", "book_chapter", "report", "thesis",
        "patent", "unpublished", "private_comm",
    ):
        assert canonicalize_ref_type(name) == name, name


def test_canonicalize_unknown_returns_lowercase():
    """Unknown ref types are returned unchanged (lowercased) so the
    ``FORMATTERS.get(rt, _fmt_journal)`` fallback still works."""
    assert canonicalize_ref_type("totally_made_up") == "totally_made_up"
    assert canonicalize_ref_type("Journal") == "journal"  # case-folded


def test_canonicalize_empty_defaults_to_journal():
    assert canonicalize_ref_type("") == "journal"
    assert canonicalize_ref_type(None) == "journal"  # type: ignore[arg-type]


# ── regression: the user's exact case ───────────────────────────────────────

def test_format_ref_proceedings_ref_does_not_drop_in_proc():
    """Regression for the user-reported case: 'in Proc. NAPAC'16, Chicago,
    IL, USA, Oct. 2016, pp. 96-98' used to be re-rendered as a journal
    entry, dropping the 'in Proc. ...' line.  The dispatch alias maps
    'proceedings' to the conference_published formatter, which preserves
    it.
    """
    rec = {
        "authors_raw": "J. Wang and G. S. Sprau",
        "title": "A high bandwidth bipolar power supply for the fast correctors in the APS upgrade",
        "conference": "NAPAC'16",
        "year": "2016",
        "doi": "10.18429/JACoW-NAPAC2016-MOPOB12",
    }
    # 'proceedings' is what the Word parser actually emits
    out = format_ref(rec, "proceedings")
    assert "in Proc. NAPAC'16" in out
    # Without the alias fix this would have rendered as a journal:
    # "... A high bandwidth bipolar ... 2016. doi:..." with no "in Proc."
    assert "Wang and G. S. Sprau" in out
    assert "doi:10.18429/JACoW-NAPAC2016-MOPOB12" in out


def test_format_ref_online_alias_dispatches_to_web_formatter():
    """The bibitem parser emits 'online' but the formatter dispatch
    key is 'web'.  The alias keeps the two in sync."""
    rec = {
        "authors_raw": "JACoW",
        "title": "JACoW home",
        "url": "https://www.jacow.org",
    }
    out = format_ref(rec, "online")
    # _fmt_online renders "JACoW, https://www.jacow.org"
    assert "JACoW" in out
    assert "https://www.jacow.org" in out


# ── split_refs ───────────────────────────────────────────────────────────────

def test_split_numbered_square_brackets():
    text = '[1] A. Smith, "Paper one", 2020.\n[2] B. Jones, "Paper two", 2021.'
    parts = split_refs(text)
    assert len(parts) == 2
    assert "Paper one" in parts[0]
    assert "Paper two" in parts[1]


def test_split_numbered_dots():
    text = '1. A. Smith, "Paper one", 2020.\n2. B. Jones, "Paper two", 2021.'
    parts = split_refs(text)
    assert len(parts) == 2


def test_split_blank_line_separation():
    text = 'A. Alpha, "First", 2020.\n\nB. Beta, "Second", 2021.'
    parts = split_refs(text)
    assert len(parts) == 2


def test_split_single_ref_no_split():
    text = 'A. Author, "A single paper", Nature, vol. 1, 2020.'
    parts = split_refs(text)
    assert len(parts) == 1


def test_split_empty_string():
    assert split_refs("") == []


def test_split_strips_reference_numbers():
    text = '[1] A. Smith, "Paper", 2020.'
    parts = split_refs(text)
    assert not parts[0].startswith("[1]")
