"""The invariants that make an edit trackable.

Each test here pins one property that a previous version of this tool violated
on real submissions, so a regression is a test failure rather than a surprise
in an editor's inbox.
"""

import pytest
from pydantic import ValidationError

from src.edits import (
    Confidence,
    Decisions,
    Edit,
    EditConflict,
    EditSet,
    Evidence,
    Tier,
    make_edit,
    sha256,
)

SOURCE = "The beam energy is 10 MeV.\nA DOI: 10.1/x appears here.\nAnd 5 nm too.\n"


def _edit(**kwargs) -> Edit:
    defaults = dict(
        check_id="TEST-01",
        tier=Tier.AUTO,
        file="paper.tex",
        message="test",
    )
    return Edit(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# An edit that changes nothing cannot exist
# ---------------------------------------------------------------------------

def test_no_op_edit_is_rejected_at_construction():
    """The phantom-auto-fix bug, made structurally impossible.

    The previous DOI fix tested the regex substitution *count* rather than
    whether the text changed, so an already-correct ``doi:10.1103/...`` still
    produced a Finding with ``auto_fixed=True``. On THP017 that reported seven
    repairs against a file whose two SHA-256 hashes matched.
    """
    with pytest.raises(ValidationError, match="no-op edit"):
        _edit(start=4, end=8, before="beam", after="beam")


def test_make_edit_returns_none_for_a_no_op():
    import re

    match = re.search(r"10 MeV", SOURCE)
    assert make_edit(SOURCE, match, "10 MeV", check_id="X", tier=Tier.AUTO,
                     message="m") is None
    assert make_edit(SOURCE, match, "10~MeV", check_id="X", tier=Tier.AUTO,
                     message="m") is not None


def test_span_and_before_must_agree():
    with pytest.raises(ValidationError, match="span"):
        _edit(start=0, end=3, before="The beam", after="A beam")


def test_auto_tier_requires_verified_external_evidence():
    """An unverified external fact may be suggested, never applied silently."""
    with pytest.raises(ValidationError, match="verified evidence"):
        _edit(
            start=4, end=8, before="beam", after="bunch",
            evidence=Evidence(source="crossref", checked=False),
        )
    # The same edit is fine as a suggestion.
    _edit(
        start=4, end=8, before="beam", after="bunch",
        tier=Tier.SUGGEST,
        evidence=Evidence(source="crossref", checked=False),
    )


def test_uncertain_edits_cannot_be_auto():
    with pytest.raises(ValidationError, match="uncertain"):
        _edit(start=4, end=8, before="beam", after="bunch",
              confidence=Confidence.UNCERTAIN)


# ---------------------------------------------------------------------------
# EditSet: verification, overlap, application
# ---------------------------------------------------------------------------

def test_build_drops_edits_whose_before_does_not_match():
    good = _edit(start=19, end=25, before="10 MeV", after="10~MeV")
    bad = _edit(start=0, end=6, before="XXXXXX", after="YYYYYY")
    editset, dropped = EditSet.build(SOURCE, "paper.tex", [good, bad])
    assert [e.before for e in editset.edits] == ["10 MeV"]
    assert dropped == [bad]


def test_build_resolves_overlaps_by_priority():
    """A narrower, better-trusted edit wins the span; the other is dropped."""
    wide = _edit(check_id="FMT-REF-01", start=19, end=25,
                 before="10 MeV", after="10~MeV (reformatted)")
    narrow = _edit(check_id="FMT-UNIT-01", start=19, end=25,
                   before="10 MeV", after="10~MeV")
    editset, dropped = EditSet.build(SOURCE, "paper.tex", [wide, narrow])
    assert [e.check_id for e in editset.edits] == ["FMT-UNIT-01"]
    assert [e.check_id for e in dropped] == ["FMT-REF-01"]


def test_ids_and_lines_are_assigned_in_source_order():
    edits = [
        _edit(start=59, end=63, before="5 nm", after="5~nm"),
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
    ]
    editset, _ = EditSet.build(SOURCE, "paper.tex", edits)
    assert [e.id for e in editset.edits] == ["E001", "E002"]
    assert [e.line for e in editset.edits] == [1, 3]


def test_apply_only_the_named_subset():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
        _edit(start=59, end=63, before="5 nm", after="5~nm"),
    ])
    only_first = editset.apply(SOURCE, ["E001"])
    assert "10~MeV" in only_first
    assert "5 nm" in only_first          # untouched
    both = editset.apply(SOURCE, ["E001", "E002"])
    assert "10~MeV" in both and "5~nm" in both
    assert editset.apply(SOURCE, []) == SOURCE


def test_apply_is_exactly_reversible():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
    ])
    applied = editset.apply(SOURCE, ["E001"])
    edit = editset.edits[0]
    restored = applied[:edit.start] + edit.before + applied[edit.start + len(edit.after):]
    assert restored == SOURCE


def test_apply_refuses_a_source_that_has_drifted():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
    ])
    drifted = SOURCE.replace("10 MeV", "12 GeV")
    with pytest.raises(EditConflict, match="changed since"):
        editset.apply(drifted, ["E001"])


def test_unknown_edit_id_is_an_error_not_a_silent_skip():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
    ])
    with pytest.raises(KeyError, match="E999"):
        editset.apply(SOURCE, ["E999"])


def test_per_edit_patches_apply_independently():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
        _edit(start=59, end=63, before="5 nm", after="5~nm"),
    ])
    patches = editset.per_edit_patches(SOURCE)
    assert set(patches) == {"E001", "E002"}
    for patch in patches.values():
        assert patch.startswith("---")
        assert patch.count("@@") == 2      # exactly one hunk


def test_roundtrip_through_json():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
    ])
    restored = EditSet.model_validate_json(editset.model_dump_json())
    assert restored.source_sha256 == sha256(SOURCE)
    assert restored.apply(SOURCE, ["E001"]) == editset.apply(SOURCE, ["E001"])


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def test_decisions_take_auto_plus_explicitly_accepted():
    editset, _ = EditSet.build(SOURCE, "paper.tex", [
        _edit(start=19, end=25, before="10 MeV", after="10~MeV"),
        _edit(start=59, end=63, before="5 nm", after="5~nm", tier=Tier.SUGGEST),
    ])
    auto_id = editset.auto[0].id
    suggest_id = editset.suggested[0].id

    assert Decisions().accepted(editset) == [auto_id]
    assert Decisions(decisions={suggest_id: "accepted"}).accepted(editset) == [
        auto_id, suggest_id,
    ]
    assert Decisions(decisions={suggest_id: "rejected"}).accepted(editset) == [auto_id]


def test_decisions_tolerate_the_browser_download_shape(tmp_path):
    path = tmp_path / "review_decisions.json"
    path.write_text('{"E002": "accepted"}', encoding="utf-8")
    assert Decisions.read(path).decisions == {"E002": "accepted"}
