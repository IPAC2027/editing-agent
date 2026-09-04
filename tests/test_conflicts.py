"""Tests for src.refs.conflicts — detect_conflicts."""

import pytest

from src.refs.conflicts import detect_conflicts


def test_no_conflict_when_other_is_none():
    """Per spec: if the secondary source returned nothing, we trivially
    return no conflicts (no point raising a ValidationError)."""
    assert detect_conflicts({"doi": "10.1/a", "year": "2020"}, None) == []


def test_no_conflict_when_data_matches():
    cr = {"doi": "10.1/a", "year": "2020", "volume": "5"}
    other = {"doi": "10.1/a", "year": "2020", "volume": "5"}
    assert detect_conflicts(cr, other) == []


def test_doi_mismatch_flagged():
    cr = {"doi": "10.1/a", "year": "2020"}
    other = {"doi": "10.1/b", "year": "2020"}
    conflicts = detect_conflicts(cr, other)
    assert any("DOI" in c for c in conflicts)
    assert any("10.1/a" in c and "10.1/b" in c for c in conflicts)


def test_year_mismatch_flagged():
    cr = {"doi": "10.1/a", "year": "2020"}
    other = {"doi": "10.1/a", "year": "2021"}
    conflicts = detect_conflicts(cr, other)
    assert any("Year" in c for c in conflicts)


def test_volume_mismatch_flagged():
    cr = {"doi": "10.1/a", "volume": "5"}
    other = {"doi": "10.1/a", "volume": "9"}
    conflicts = detect_conflicts(cr, other)
    assert any("Volume" in c for c in conflicts)


def test_volume_mismatch_with_long_record_id_ignored():
    """InspireHEP sometimes stores record IDs in the journal_volume
    field — those are long (e.g. '950501') and should not be flagged
    as a volume conflict."""
    cr = {"doi": "10.1/a", "volume": "5"}
    other = {"doi": "10.1/a", "volume": "950501"}  # too long
    assert detect_conflicts(cr, other) == []


def test_doi_mismatch_ignores_case_and_punctuation():
    """Normalisation: ``10.1/A`` and ``10.1-a`` should be considered equal."""
    cr = {"doi": "10.1/A"}
    other = {"doi": "10.1-a"}
    assert detect_conflicts(cr, other) == []


def test_no_conflict_when_one_source_lacks_a_field():
    cr = {"doi": "10.1/a"}  # no year
    other = {"doi": "10.1/a", "year": "2020"}
    assert detect_conflicts(cr, other) == []


def test_returns_empty_list_when_only_dois_match():
    """The DOI is the same; year and volume are absent from both — no
    conflict to flag."""
    cr = {"doi": "10.1/a"}
    other = {"doi": "10.1/a"}
    assert detect_conflicts(cr, other) == []


def test_all_three_conflicts_at_once():
    cr = {"doi": "10.1/a", "year": "2020", "volume": "5"}
    other = {"doi": "10.1/b", "year": "2021", "volume": "9"}
    conflicts = detect_conflicts(cr, other)
    # Expect exactly one conflict per mismatching field
    assert len(conflicts) == 3
    assert any("DOI" in c for c in conflicts)
    assert any("Year" in c for c in conflicts)
    assert any("Volume" in c for c in conflicts)
