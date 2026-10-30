"""Regressions found in the October 2026 prescreening review.

The reference-formatting regressions (author counts, et al., journal table,
sentence case) moved to the reference formatter with the code they test; see
jacow-reference-formatter/tests/test_review_fixes_2026_10.py and
tests/test_verify_rewrite.py.  What stays here is the agent's own DOI check.
"""
from __future__ import annotations

from src.checks import reference_checks as rc
from src.models import Reference


def test_a_doi_without_metadata_is_not_offered_for_a_titled_reference(monkeypatch):
    monkeypatch.setattr(rc, "_fetch_doi_metadata", lambda doi: None)
    monkeypatch.setattr(rc, "_validate_doi_online", lambda doi: True)
    ref = Reference(n=1, key="r1", title="Lattice design of a booster", raw_text="…")
    assert rc._doi_matches_reference(ref, "10.18429/JACoW-IPAC2023-MOPA001") is False


def test_jacow_dois_are_matched_against_datacite_titles(monkeypatch):
    monkeypatch.setattr(rc, "_fetch_crossref_work", lambda doi: None)
    monkeypatch.setattr(rc, "_fetch_datacite_work", lambda doi: {
        "title": ["Lattice design of the Northbridge booster synchrotron"],
        "issued": {"date-parts": [[2023]]},
    })
    good = Reference(n=1, key="r1", title="Lattice design of the Northbridge booster synchrotron",
                     raw_text="… 2023 …")
    other = Reference(n=2, key="r2", title="Cryogenic distribution for a superconducting linac",
                      raw_text="… 2023 …")
    assert rc._doi_matches_reference(good, "10.18429/JACoW-IPAC2023-MOPA001") is True
    assert rc._doi_matches_reference(other, "10.18429/JACoW-IPAC2023-MOPA001") is False
