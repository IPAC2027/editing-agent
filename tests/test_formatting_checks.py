"""Formatting checks: what stays a *finding* and what became an *edit*.

Number/unit spacing used to be reported as a warning per occurrence (231 of
them across the sample corpus, all correct, none applied).  It is now an AUTO
edit produced by ``src.autofix.latex_edits``, so these tests assert the split:
findings carry things a human must decide, edits carry things the tool should
just do.
"""

from pathlib import Path

import pytest

from src.autofix.latex_edits import all_source_edits
from src.checks.formatting_checks import run_all
from src.edits import EditSet, Tier
from src.parser.latex_parser import parse_latex


def _parse(tmp_path: Path, source: str):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(source, encoding="utf-8")
    return parse_latex(tex_path)


def _editset(paper):
    source = paper.source_path.read_text(encoding="utf-8")
    parsed = paper.__dict__["_pt"]
    editset, _ = EditSet.build(
        source,
        paper.source_path.name,
        all_source_edits(
            source,
            file=paper.source_path.name,
            author_span=parsed.author_names_span,
            title_span=parsed.title_text_span,
        ),
    )
    return source, editset


def test_title_punctuation_and_author_initials_are_findings(tmp_path: Path):
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{Beam dynamics study.}
\author{John Smith, A. Doe\\
Institute of Physics}
\begin{document}
The beam energy is 10 MeV and the frequency is 5 mhz.
The length remains 2~m.
\end{document}
""",
    )

    run_all(paper)
    check_ids = [finding.check_id for finding in paper.findings]

    assert "FMT-TITLE-02" in check_ids
    # One finding for the whole author list, not one per name.
    assert check_ids.count("FMT-AUTH-01") == 1
    # Units are no longer findings at all.
    assert "FMT-UNIT-01" not in check_ids


def test_units_become_auto_edits_not_warnings(tmp_path: Path):
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{Beam dynamics study}
\author{A. B. Smith\\
Institute of Physics}
\begin{document}
The beam energy is 10 MeV and the frequency is 5 mhz.
The length remains 2~m.
\end{document}
""",
    )
    source, editset = _editset(paper)

    spacing = [e for e in editset.edits if e.check_id == "FMT-UNIT-01"]
    # The JACoW class loads siunitx, so the house form is available.
    assert [e.after for e in spacing] == ["\\qty{10}{MeV}"]
    assert all(e.tier is Tier.AUTO for e in spacing)

    # "5 mhz" needs a case change as well, so it is one SUGGEST edit that does
    # both rather than a silent AUTO rewrite of the unit.
    cased = [e for e in editset.edits if e.check_id == "FMT-UNIT-02"]
    assert [e.after for e in cased] == ["\\qty{5}{MHz}"]
    assert cased[0].tier is Tier.SUGGEST

    applied = editset.apply(source)
    assert "\\qty{10}{MeV}" in applied
    # An already-correct "2~m" is untouched — and, crucially, not reported.
    # Rewriting every correct non-breaking space into \qty{} as well would put
    # dozens of edits on a paper with nothing wrong with it.
    assert "2~m" in applied
    assert not any(e.before == "2~m" for e in editset.edits)


def test_unit_case_is_only_ever_suggested(tmp_path: Path):
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{Case check}
\author{A. B. Smith\\
Institute of Physics}
\begin{document}
A 1.3 Gev proton and a 0.4 MT/m gradient.
\end{document}
""",
    )
    source, editset = _editset(paper)

    case_edits = [e for e in editset.edits if e.check_id == "FMT-UNIT-02"]
    assert len(case_edits) == 1
    assert case_edits[0].after == "\\qty{1.3}{GeV}"
    assert case_edits[0].tier is Tier.SUGGEST, "unit case can change a quantity"

    # "MT" (megatesla) must never be rewritten to "mT": the spelling is
    # ambiguous, so only the spacing is corrected.
    assert not any("mT" in e.after for e in editset.edits)
    assert any(e.after == "\\qty{0.4}{MT}" for e in editset.edits)


def test_deterministic_formatting_accepts_jacow_conventions(tmp_path: Path):
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{BEAM DYNAMICS STUDY}
\author{A. B. Smith, C. Doe\\
Institute of Physics}
\begin{document}
The beam energy is 10~MeV and the frequency is 5\,MHz.
\end{document}
""",
    )

    run_all(paper)
    _, editset = _editset(paper)

    assert paper.findings == []
    assert editset.edits == []


def test_superscript_affiliations_do_not_produce_author_findings(tmp_path: Path):
    """The 32-false-positive regression, pinned.

    Every one of these names is correctly formatted; the previous parser split
    the block on commas before stripping ``\\textsuperscript``, turning
    ``S. Kongtawong\\textsuperscript{1,2}`` into two bogus "authors" and
    flattening ``K. Ha\\textsuperscript{1}`` to ``K. Ha1``.
    """
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{Fast orbit feedback}
\author{S. Kongtawong\textsuperscript{1,2}, K. Ha\textsuperscript{1},
Y. Hidaka\textsuperscript{1}, T. Shaftan\textsuperscript{1}\\
Brookhaven National Laboratory, Upton, NY, USA}
\begin{document}
\end{document}
""",
    )

    run_all(paper)

    assert [f.check_id for f in paper.findings] == []
    assert paper.authors == [
        "S. Kongtawong", "K. Ha", "Y. Hidaka", "T. Shaftan",
    ]
    assert "USA" not in paper.authors


def test_title_case_is_rendered_by_jacow_class(tmp_path: Path):
    paper = _parse(
        tmp_path,
        r"""\documentclass{jacow}
\title{The 3 \NoCaseChange{GeV} Taiwan Light Source}
\author{A. B. Smith\\
Institute of Physics}
\begin{document}
\end{document}
""",
    )

    run_all(paper)

    assert paper.findings == []


# ---------------------------------------------------------------------------
# Unit case: the pairs that must never be resolved by guessing
#
# Found by measuring against NAPAC2025, where the agent proposed rewriting
# "0.5 mG" (milligauss) to "0.5 mg" (milligrams) and the editors had written
# "0.5\,mG". Gauss was in the table but its prefixed forms were not, so "mG"
# lowercased to the unique key "mg" and was "corrected" into a different
# physical quantity.
# ---------------------------------------------------------------------------

DANGEROUS_PAIRS = [
    ("mG", "mg"),   # milligauss vs milligrams
    ("kG", "kg"),   # kilogauss vs kilograms
    ("uG", "ug"),   # microgauss vs micrograms
    ("mV", "MV"),   # millivolts vs megavolts
    ("mT", "MT"),   # millitesla vs megatesla
    ("mA", "MA"),   # milliamps vs megaamps
]


@pytest.mark.parametrize(("one", "other"), DANGEROUS_PAIRS)
def test_units_that_differ_only_by_case_are_both_known(one: str, other: str):
    """Both spellings must be in the table, or the collision is invisible."""
    from src.autofix.latex_edits import _CANONICAL_UNITS

    assert one in _CANONICAL_UNITS, f"{one} missing — {other} would swallow it"
    assert other in _CANONICAL_UNITS, f"{other} missing — {one} would swallow it"


@pytest.mark.parametrize(("one", "other"), DANGEROUS_PAIRS)
def test_a_unit_that_could_be_two_things_is_never_case_corrected(one: str, other: str):
    from src.autofix.latex_edits import _AMBIGUOUS_UNIT_KEYS, _UNIT_BY_LOWER

    assert one.lower() in _AMBIGUOUS_UNIT_KEYS
    assert _UNIT_BY_LOWER.get(one.lower()) is None


@pytest.mark.parametrize("written", ["0.5 mG", "200 kG", "1.5 mg", "12 kg"])
def test_a_gauss_or_gram_measurement_keeps_the_case_the_author_wrote(
        written: str, tmp_path: Path):
    """Spacing is still fixed; the letters are left exactly as submitted."""
    from src.autofix.latex_edits import unit_edits

    source = f"The stray field was {written} at the wall.\n"
    edits = unit_edits(source)

    unit = written.split()[1]
    for edit in edits:
        assert unit in edit.after, (
            f"{written}: the agent rewrote the unit to {edit.after!r}")
