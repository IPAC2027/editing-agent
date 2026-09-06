"""Scoring the agent against real editorial behaviour.

The arithmetic is trivial. What these tests protect is the *meaning* of the
three columns, because a misleading metric here would be worse than none: it
would be used to promote or kill checks.

  confirmed     — the editors made this change too.
  contradicted  — the editors changed this very text into something else.
  unconfirmed   — the editors did not make it. NOT evidence that it is wrong.
"""

from __future__ import annotations

import pytest

from src.corpus.diff import Hunk
from src.corpus.score import CheckScore, Judged, PaperScore, Proposal, by_check, match


def _hunk(before: str, after: str, *, paper: str = "P") -> Hunk:
    return Hunk(paper=paper, kind="replace", before=before, after=after, unit=0)


def _proposal(before: str, after: str, *, check: str = "FMT-UNIT-01",
              tier: str = "auto") -> Proposal:
    return Proposal(paper="P", check_id=check, tier=tier, before=before, after=after)


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------

def test_the_same_edit_is_confirmed():
    judged = match(_proposal("10 MeV", "10~MeV"), [_hunk("10 MeV", "10~MeV")])

    assert judged.how == "exact"
    assert judged.confirmed is True


def test_a_small_edit_inside_a_larger_editorial_rewrite_counts():
    """An editor who retyped a whole reference still made the DOI fix in it."""
    judged = match(_proposal(r"\url{doi:10.1/x}", r"\doi{10.1/x}"),
                   [_hunk(r"A. Author, Title, \url{doi:10.1/x} 2024",
                          r"A. Author, Title, \doi{10.1/x} 2024")])

    assert judged.how == "inside-hunk"


def test_a_paragraph_wide_proposal_matches_a_word_level_hunk():
    """The Word side proposes whole paragraphs; the diff is word-level."""
    judged = match(_proposal("Ref 1, vol 2, p 3.", "Ref 1, vol. 2, pp. 3."),
                   [_hunk("p 3.", "pp. 3.")])

    assert judged.how == "covers-hunk"


def test_a_difference_of_spacing_convention_is_agreement_not_disagreement():
    """The finding this rescued: the agent writes X. Du, the editors X.~Du.

    Those are the same decision about the name and a different choice of
    non-breaking space. Counting it as a contradiction would have buried the
    agreement and invented a defect.
    """
    judged = match(_proposal("Xiaonan Du", "X. Du", check="FMT-AUTH-01"),
                   [_hunk("Xiaonan Du", "X.~Du")])

    assert judged.confirmed is True
    assert judged.how.startswith("near")
    assert judged.contradicted is False


def test_a_thin_space_is_also_the_same_decision():
    judged = match(_proposal("5 GHz", "5~GHz"), [_hunk("5 GHz", r"5\,GHz")])
    assert judged.confirmed is True


# ---------------------------------------------------------------------------
# Disagreement — and the guard that keeps it meaningful
# ---------------------------------------------------------------------------

def test_the_editors_doing_something_else_to_the_same_text_is_a_contradiction():
    """The real one from HIAT2025: editors lowercase the DOI suffix."""
    judged = match(_proposal(r"\url{doi:10.1038/NPHYS3735}", r"\doi{10.1038/NPHYS3735}",
                             check="DOI-FMT-02"),
                   [_hunk(r"\url{doi:10.1038/NPHYS3735}", r"\doi{10.1038/nphys3735}")])

    assert judged.contradicted is True
    assert judged.confirmed is False
    assert "nphys3735" in judged.editors_did


def test_a_short_proposal_inside_a_big_rewrite_is_not_a_contradiction():
    """Without this guard the report fills with contradictions that are nothing
    of the kind — an edit the editors never considered, sitting inside a
    paragraph they happened to retype.

    This is not hypothetical: it turned 19 real disagreements into 90.
    """
    rewrite = _hunk("we ran the machine at 10 MeV for a while and then " * 4,
                    "a completely different sentence " * 6)
    assert rewrite.large is True

    judged = match(_proposal("10 MeV", "10~MeV"), [rewrite])

    assert judged.contradicted is False
    assert judged.confirmed is False


def test_a_much_longer_hunk_does_not_count_as_a_contradiction_either():
    judged = match(_proposal("10 MeV", "10~MeV"),
                   [_hunk("at 10 MeV in the second cavity of the linac", "elsewhere")])
    assert judged.contradicted is False


def test_an_edit_the_editors_never_touched_is_unconfirmed_not_contradicted():
    """The most important distinction in the whole module."""
    judged = match(_proposal("10 MeV", "10~MeV"), [_hunk("Figure", "Fig.")])

    assert judged.confirmed is False
    assert judged.contradicted is False
    assert judged.how == ""


def test_an_empty_proposal_matches_nothing():
    assert match(_proposal("", ""), [_hunk("a", "b")]).how == ""


# ---------------------------------------------------------------------------
# What the numbers are allowed to say
# ---------------------------------------------------------------------------

def _score(judgements: list[Judged]) -> PaperScore:
    return PaperScore(paper="P", source="latex", judged=judgements)


def test_a_contradiction_outranks_a_good_rate_in_the_verdict():
    """One contradiction is worth reading even at 95% agreement."""
    check = CheckScore(check_id="X", proposals=100, confirmed=95, contradicted=1)
    assert "contradicted" in check.verdict


def test_a_small_sample_is_never_called_strong():
    check = CheckScore(check_id="X", proposals=3, confirmed=3)
    assert check.verdict == "too few to say"


def test_a_high_rate_over_a_real_sample_is_stated_as_agreement_not_correctness():
    check = CheckScore(check_id="X", proposals=40, confirmed=39)
    assert check.verdict == "editors agree"


def test_a_low_rate_says_the_editors_rarely_did_it_not_that_it_is_wrong():
    """Wording matters: absence is weak evidence and must not read as a defect."""
    check = CheckScore(check_id="X", proposals=40, confirmed=2)

    assert check.verdict == "editors rarely did this"
    assert "wrong" not in check.verdict
    assert "false" not in check.verdict


def test_per_check_aggregation_counts_papers_not_just_proposals():
    """184 proposals across 15 papers is a different claim from across 2."""
    scores = [
        PaperScore(paper="A", source="latex", judged=[
            Judged(proposal=_proposal("a", "b"), how="exact", hunk=0),
            Judged(proposal=_proposal("c", "d")),
        ]),
        PaperScore(paper="B", source="latex", judged=[
            Judged(proposal=_proposal("e", "f"), how="exact", hunk=0),
        ]),
    ]

    table = {c.check_id: c for c in by_check(scores)}
    unit = table["FMT-UNIT-01"]

    assert unit.proposals == 3
    assert unit.confirmed == 2
    assert unit.papers == {"A", "B"}
    assert unit.rate == pytest.approx(2 / 3)


def test_missed_corrections_exclude_the_ones_something_explained():
    from src.corpus.score import missed_signatures

    score = PaperScore(
        paper="P", source="latex",
        hunks=[_hunk("10 MeV", "10~MeV"), _hunk("Figure", "Fig.")],
        explained={0},
    )

    assert missed_signatures([score]) == [("Figure -> Fig.", 1)]

