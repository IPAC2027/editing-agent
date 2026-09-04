"""Tests for src.refs.text_utils (adapted from TestFmtAuthors / TestParseAuthors)."""

import pytest

from src.refs.text_utils import (
    clean_title,
    fmt_authors,
    norm_month,
    pages_fmt,
    parse_authors,
    sent_case,
    to_initials,
)


# ── fmt_authors ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ([{"given": "A.", "family": "Smith"}], "A. Smith"),
        (
            [{"given": "A.", "family": "Smith"}, {"given": "B.", "family": "Jones"}],
            "A. Smith and B. Jones",
        ),
        (
            [
                {"given": "A.", "family": "Alpha"},
                {"given": "B.", "family": "Beta"},
                {"given": "C.", "family": "Gamma"},
            ],
            "A. Alpha, B. Beta, and C. Gamma",
        ),
        (
            [
                {"given": "A.", "family": "A"},
                {"given": "B.", "family": "B"},
                {"given": "C.", "family": "C"},
                {"given": "D.", "family": "D"},
                {"given": "E.", "family": "E"},
                {"given": "F.", "family": "F"},
                {"given": "G.", "family": "G"},
            ],
            "A. A et al.",
        ),
    ],
)
def test_author_formatting(raw, expected):
    assert fmt_authors(raw) == expected


def test_et_al_string_passthrough():
    result = fmt_authors("Smith et al.")
    assert "Smith" in result


def test_none_returns_empty():
    assert fmt_authors(None) == ""


# ── parse_authors ────────────────────────────────────────────────────────────

def test_single_author_string():
    result = parse_authors("A. B. Smith")
    assert len(result) >= 1


def test_two_authors_with_and():
    result = parse_authors("A. Smith and B. Jones")
    assert len(result) == 2


def test_et_al_string():
    result = parse_authors("A. Smith et al.")
    assert result[0].endswith("et al.")


def test_crossref_list_format():
    result = parse_authors([
        {"given": "Alice", "family": "Wonder"},
        {"given": "Bob", "family": "Builder"},
    ])
    assert len(result) == 2
    assert "Wonder" in result[0]
    assert "Builder" in result[1]


# ── to_initials ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "given,expected",
    [
        ("Jean-Pierre", "J.-P."),
        ("J.-P.", "J.-P."),
        ("B.T.", "B.T."),
        ("Jean Pierre", "J.P."),
        ("Alice", "A."),
    ],
)
def test_to_initials(given, expected):
    assert to_initials(given) == expected


def test_to_initials_empty():
    assert to_initials("") == ""


# ── sent_case ────────────────────────────────────────────────────────────────

def test_sent_case_acronyms_preserved():
    assert sent_case("Studies of the LHC at CERN") == "Studies of the LHC at CERN"


def test_sent_case_first_word_capitalised():
    assert sent_case("studies of accelerator design") == "Studies of accelerator design"


def test_sent_case_after_colon():
    out = sent_case("Overview: status of the project")
    # Word after colon must be capitalised
    assert "Status" in out


def test_sent_case_mixed_case_preserved():
    # GeV and similar mixed-case tokens stay verbatim
    out = sent_case("Beam energy of 10 GeV at SwissFEL")
    assert "GeV" in out
    assert "SwissFEL" in out


def test_sent_case_all_caps_input():
    out = sent_case("BEAM DYNAMICS STUDIES IN THE LHC")
    assert out.startswith("Beam ")
    assert "LHC" in out          # short acronym preserved
    assert "DYNAMICS" not in out  # long token lowered


def test_sent_case_empty():
    assert sent_case("") == ""


# ── clean_title ──────────────────────────────────────────────────────────────

def test_clean_title_strips_arxiv():
    assert clean_title("My Paper arXiv:2401.12345 [cs.LG]") == "My Paper"


def test_clean_title_strips_trailing_year():
    assert clean_title("My Paper (2023).") == "My Paper"


def test_clean_title_rejects_venue_header():
    assert clean_title("in Proc. IPAC'23, Venice, Italy") == ""


def test_clean_title_rejects_bare_conf_acronym():
    assert clean_title("IPAC'23, Venice, Italy, pp. 100-103") == ""


# ── pages_fmt ────────────────────────────────────────────────────────────────

def test_pages_fmt_hyphen_to_en_dash():
    assert pages_fmt("1-5") == "1–5"


def test_pages_fmt_double_hyphen():
    assert pages_fmt("100--200") == "100–200"


def test_pages_fmt_already_en_dash():
    assert pages_fmt("1–5") == "1–5"


def test_pages_fmt_empty():
    assert pages_fmt("") == ""


# ── norm_month ───────────────────────────────────────────────────────────────

def test_norm_month_long():
    assert norm_month("September") == "Sep."


def test_norm_month_short():
    assert norm_month("sep") == "Sep."


def test_norm_month_with_period():
    assert norm_month("Sep.") == "Sep."


def test_norm_month_unknown_passthrough():
    assert norm_month("Lunar") == "Lunar"
