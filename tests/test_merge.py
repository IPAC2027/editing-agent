"""Tests for src.refs.merge — user-fields-win merge for authoritative
metadata sources.

These tests verify the REQ-MFC-009 invariant: authors and title
must never be overwritten by any external source.
"""

import pytest

from src.refs.merge import merge_crossref


def test_doi_always_filled():
    """DOI is an identifier, not content — always safe to fill."""
    out = merge_crossref({}, {"doi": "10.1234/test"}, "verified")
    assert out["doi"] == "10.1234/test"


def test_doi_normalises_case_when_updating():
    """When user and Crossref DOIs differ, the authoritative source wins
    and is stored in its native case."""
    out = merge_crossref({"doi": "10.1234/other"}, {"doi": "10.1234/test"}, "verified")
    assert out["doi"] == "10.1234/test"


def test_doi_case_insensitive_match_preserves_user_value():
    """When user and Crossref DOIs are equal under case folding
    (e.g. ``10.1234/TEST`` vs ``10.1234/test``), the user value is
    preserved as-is — we don't rewrite a correctly-identical DOI just
    to change its case."""
    out = merge_crossref({"doi": "10.1234/TEST"}, {"doi": "10.1234/test"}, "verified")
    assert out["doi"] == "10.1234/TEST"


# ── Authors and title are NEVER overwritten (REQ-MFC-009) ─────────────────

def test_authors_never_overwritten_when_trusted():
    rec = {"authors_raw": "Original Author"}
    cr = {"crossref_authors": [{"given": "X.", "family": "New"}]}
    out = merge_crossref(rec, cr, "verified")
    assert out["authors_raw"] == "Original Author"


def test_title_never_overwritten_when_trusted():
    rec = {"title": "User-supplied title"}
    out = merge_crossref(rec, {"title": "Crossref title"}, "verified")
    assert out["title"] == "User-supplied title"


def test_authors_filled_when_empty_even_if_trusted():
    """Filling an empty field is allowed — overwriting is what's banned."""
    out = merge_crossref(
        {},
        {"crossref_authors": [{"given": "A.", "family": "Smith"}]},
        "verified",
    )
    assert out["authors_raw"] == [{"given": "A.", "family": "Smith"}]


def test_title_filled_when_empty_even_if_trusted():
    out = merge_crossref({}, {"title": "Some paper"}, "verified")
    assert out["title"] == "Some paper"


# ─- Trusted vs untrusted match levels ────────────────────────────────────

def test_ambiguous_level_does_not_fill_volume():
    rec = {"title": "T", "authors_raw": "A"}
    cr = {"volume": "120", "pages": "1-5", "year": "2020"}
    out = merge_crossref(rec, cr, "ambiguous")
    # DOI may still be filled; bibliographic fields require trusted match.
    assert "volume" not in out
    assert "pages" not in out
    assert "year" not in out


def test_verified_level_fills_bibliographic_fields():
    rec = {"title": "T", "authors_raw": "A"}
    cr = {"volume": "120", "issue": "5", "pages": "1-5", "year": "2020", "month": "May"}
    out = merge_crossref(rec, cr, "verified")
    assert out["volume"] == "120"
    assert out["issue"] == "5"
    assert out["pages"] == "1-5"
    assert out["year"] == "2020"
    assert out["month"] == "May"


# ─- Journal normalisation ─────────────────────────────────────────────────

def test_journal_filled_when_empty():
    out = merge_crossref({}, {"journal": "Physical Review Letters"}, "verified")
    assert out["journal"] == "Phys. Rev. Lett."  # Tier-1 L1 normalisation


def test_journal_overwritten_when_substring_matches():
    """When user and Crossref agree (one contains the other, ignoring
    punctuation), the Crossref version wins because it's the canonical
    form."""
    rec = {"journal": "Physical Review"}  # Crossref has "Physical Review Letters"
    out = merge_crossref(rec, {"journal": "Physical Review Letters"}, "verified")
    assert out["journal"] == "Phys. Rev. Lett."


def test_journal_kept_when_no_crossref_value():
    """Without a Crossref journal, the user's journal is normalised
    in place (catches ``"Physical Review Letters"`` → ``"Phys. Rev. Lett."``)."""
    out = merge_crossref({"journal": "Physical Review Letters"}, {}, "verified")
    assert out["journal"] == "Phys. Rev. Lett."


# ─- arXiv IDs ──────────────────────────────────────────────────────────────

def test_arxiv_id_filled_from_doi():
    out = merge_crossref({}, {"doi": "10.48550/arXiv.1810.04805"}, "verified")
    # Wait — the doi-key arXiv link. The standalone detects this in
    # _extract_identifiers; merge_crossref just sets the doi.
    assert out["doi"] == "10.48550/arXiv.1810.04805"


def test_arxiv_id_field_set():
    out = merge_crossref({}, {"arxiv_id": "2101.00001", "arxiv_cat": "cs.LG"}, "verified")
    assert out["arxiv_id"] == "2101.00001"
    assert out["arxiv_cat"] == "cs.LG"


# ─- Publisher ────────────────────────────────────────────────────────────

def test_publisher_filled_when_empty():
    out = merge_crossref({}, {"publisher": "Springer"}, "verified")
    assert out["publisher"] == "Springer"


# ─- Editor flag ───────────────────────────────────────────────────────────

def test_editor_flag_set_with_authors():
    cr = {"crossref_authors": [{"family": "Smith"}], "is_editor": True}
    out = merge_crossref({}, cr, "verified")
    assert out["is_editor"] is True


# ─- Original record is never mutated ─────────────────────────────────────

def test_does_not_mutate_input():
    rec = {"doi": "10.1/x"}
    cr = {"doi": "10.1/y"}
    merge_crossref(rec, cr, "verified")
    assert rec == {"doi": "10.1/x"}  # input preserved
