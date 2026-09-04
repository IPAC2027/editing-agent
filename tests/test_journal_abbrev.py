"""Tests for src.refs.journal_abbrev (adapted from TestNormalizeJournal).

Network sources (JabRef L2, LTWA L2.5) are disabled in conftest.py so only the
L1 hand-curated table is exercised here.  L1 covers every journal listed in
JACoW ANNEX C, which is the publication-critical set.
"""

import pytest

from src.refs.journal_abbrev import normalize_journal


@pytest.mark.parametrize(
    "full,expected",
    [
        ("Physical Review Letters", "Phys. Rev. Lett."),
        ("Physical Review Accelerators and Beams", "Phys. Rev. Accel. Beams"),
        (
            "Physical Review Special Topics - Accelerators and Beams",
            "Phys. Rev. Spec. Top. Accel. Beams",
        ),
        (
            "Nuclear Instruments and Methods in Physics Research Section A",
            "Nucl. Instrum. Methods Phys. Res. A",
        ),
        (
            "Nuclear Instruments and Methods in Physics Research Section B",
            "Nucl. Instrum. Methods Phys. Res. B",
        ),
        ("The Physical Review Letters", "Phys. Rev. Lett."),  # strips "The"
        ("IEEE Transactions on Nuclear Science", "IEEE Trans. Nucl. Sci."),
        ("Nature", "Nature"),
        ("Optics Express", "Opt. Express"),
    ],
)
def test_known_journals(full, expected):
    assert normalize_journal(full) == expected


def test_unknown_journal_passthrough():
    name = "Totally Unknown Journal of Nothing XYZ"
    assert normalize_journal(name) == name


def test_empty_string_passthrough():
    assert normalize_journal("") == ""


def test_case_insensitive():
    assert normalize_journal("physical review letters") == "Phys. Rev. Lett."


def test_invalid_placeholder_returns_empty():
    # 'Proc.' alone is not a journal name — formatter should treat it as empty
    assert normalize_journal("Proc.") == ""
    assert normalize_journal("Conf.") == ""


def test_strips_embedded_url():
    # URLs that bleed into the field are stripped before lookup
    assert normalize_journal(
        "Physical Review Letters https://doi.org/10.1/x",
    ) == "Phys. Rev. Lett."


def test_strips_trailing_year():
    assert normalize_journal("Nature 2024") == "Nature"
