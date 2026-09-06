"""Where a correction lives, and what that licenses you to say about it.

Editors are strict about front matter and references, variable about figures
and tables, and inconsistent with each other in running text. That is not a
detail — it decides whether a confirmation rate is evidence about the agent or
evidence about editorial appetite, so it is encoded and tested.
"""

from __future__ import annotations

import pytest

from src.corpus.diff import Hunk
from src.corpus.score import CheckScore, by_zone, PaperScore, Judged, Proposal
from src.corpus.zones import (
    BODY,
    DOCUMENT,
    FLOATS,
    FRONT,
    REFERENCES,
    reading,
    zone_of_check,
    zone_of_hunk,
    zone_of_text,
)


@pytest.mark.parametrize(("text", "zone"), [
    (r"\bibitem{a} A. Author, in Proc. IPAC'24, pp. 10-12", REFERENCES),
    (r"a DOI written as doi:10.1/x in the list", REFERENCES),
    (r"\title{A paper about beams}", FRONT),
    (r"\author{Y. Hao\thanks{yh@example.org}}", FRONT),
    (r"\caption{The layout of the injector}", FLOATS),
    (r"\begin{table} \hline", FLOATS),
    ("the beam reached 10 MeV in the second cavity", BODY),
    (r"\usepackage{amsmath}", DOCUMENT),
])
def test_text_is_placed_in_the_right_zone(text: str, zone: str):
    assert zone_of_text(text) == zone


def test_front_matter_beats_references_when_both_look_present():
    """An author block carrying a URL in a \\thanks is still front matter."""
    assert zone_of_text(r"\author{A. B.\thanks{see doi:10.1/x}}") == FRONT


def test_a_hunk_is_classified_by_the_text_around_it_not_just_the_change():
    """'2004,' -> '2018,' is a year: meaningless alone, obvious in context."""
    bare = Hunk(paper="P", kind="replace", before="2004,", after="2018,", unit=0)
    in_reference = Hunk(paper="P", kind="replace", before="2004,", after="2018,",
                        unit=0, context=r"\bibitem{x} A. Author, Title, 2004,")

    assert zone_of_hunk(bare) == BODY
    assert zone_of_hunk(in_reference) == REFERENCES


def test_unit_spacing_is_a_running_text_check_and_reference_work_is_not():
    assert zone_of_check("FMT-UNIT-01") == BODY
    assert zone_of_check("FMT-REF-01") == REFERENCES
    assert zone_of_check("FMT-AUTH-01") == FRONT
    assert zone_of_check("PAGE-LIMIT-01") == DOCUMENT


def test_an_unknown_check_defaults_to_the_loose_zone():
    """The conservative default: assume the weaker claim about the evidence."""
    assert zone_of_check("SOMETHING-NEW-01") == BODY


# ---------------------------------------------------------------------------
# What a rate is allowed to mean
# ---------------------------------------------------------------------------

def test_a_low_rate_in_running_text_is_not_reported_as_a_problem():
    """FMT-UNIT-01: 1153 proposals, 14% confirmed.

    Under a single global threshold that reads as a failing check. It is not —
    it is a check operating where the editors themselves disagree, and demoting
    it on that number would delete something useful for no reason.
    """
    verdict = reading(BODY, 0.14, 1153)

    assert "editors vary" in verdict
    assert "investigate" not in verdict


def test_a_low_rate_in_a_strict_zone_does_ask_for_attention():
    assert "investigate" in reading(REFERENCES, 0.22, 45)


def test_a_high_rate_in_a_strict_zone_is_the_only_thing_called_strong():
    assert reading(REFERENCES, 0.95, 100).startswith("strong")
    assert not reading(BODY, 0.95, 100).startswith("strong")


def test_a_small_sample_is_never_read_at_all():
    assert reading(REFERENCES, 1.0, 3) == "too few to say"


def test_a_check_reports_the_zone_it_works_in():
    assert CheckScore(check_id="FMT-UNIT-01").zone == BODY
    assert CheckScore(check_id="DOI-FMT-02").zone == REFERENCES


def test_the_zone_split_separates_rates_that_mean_different_things():
    """Averaging across zones flatters the strict ones and condemns the loose."""
    scores = [PaperScore(
        paper="P", source="latex",
        judged=[
            Judged(proposal=Proposal(paper="P", check_id="FMT-REF-01",
                                     tier="suggest", before="a", after="b"),
                   how="exact", hunk=0),
            Judged(proposal=Proposal(paper="P", check_id="FMT-UNIT-01",
                                     tier="auto", before="1 m", after="1~m")),
        ],
        hunks=[Hunk(paper="P", kind="replace", before="a", after="b", unit=0,
                    context=r"\bibitem{x}")],
        explained={0},
    )]

    table = {z.zone: z for z in by_zone(scores)}

    assert table[REFERENCES].rate == 1.0
    assert table[BODY].rate == 0.0
    assert table[REFERENCES].corrections == 1
    assert BODY not in table or table[BODY].corrections == 0
