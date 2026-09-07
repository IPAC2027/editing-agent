r"""House style, as the editors settled it.

Four decisions taken after measuring the agent against HIAT2025 and NAPAC2025,
where the editors' own corrections showed the agent's fixes were incomplete
rather than wrong:

1. A DOI is written ``\doi{10.xxxx/yyyy}``.
2. A measurement is written ``\qty{284.5}{ms}``.
3. ``et al.`` is italicised: ``\emph{et al.}``.
4. Whether the bibliography lives in a .bib or inside the .tex is the author's
   choice and not a finding.

The tests that matter most here are the ones about *not* emitting a macro the
paper cannot render. A formatting fix that breaks the build is the most
expensive mistake this tool can make.
"""

from __future__ import annotations

import pytest

from src.autofix.latex_edits import (
    doi_format_edits,
    etal_edits,
    has_doi_macro,
    has_siunitx,
    unit_edits,
)

JACOW = "\\documentclass[keeplastbox]{jacow}\n"
SIUNITX = "\\usepackage{siunitx}\n"


def _pairs(edits):
    return [(e.before, e.after) for e in edits]


# ---------------------------------------------------------------------------
# 1. \doi{...}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written", [
    "DOI: 10.1109/PAC.2007.4440878",
    "doi: 10.1109/PAC.2007.4440878",
    "DOI:10.1109/PAC.2007.4440878",
])
def test_a_written_out_doi_becomes_the_macro(written: str):
    source = f"{JACOW}A. Author, Title, 2007. {written}\n"

    assert _pairs(doi_format_edits(source)) == [
        (written, "\\doi{10.1109/PAC.2007.4440878}")]


def test_the_full_stop_goes_when_the_doi_ends_the_entry():
    """JACoW writes no full stop after the DOI, and every editor in the corpus
    who touched one of these removed it."""
    source = f"{JACOW}\\bibitem{{a}} A. Author, Title. doi: 10.1063/1.4926994.\n"

    assert _pairs(doi_format_edits(source))[0][1] == "\\doi{10.1063/1.4926994}"


def test_the_full_stop_stays_when_the_sentence_continues():
    """Mid-sentence it is punctuation about the prose, not about the DOI, and
    removing it would be an edit nobody asked for."""
    source = f"{JACOW}See doi: 10.1063/1.4926994. The result was confirmed.\n"

    assert _pairs(doi_format_edits(source))[0][1] == "\\doi{10.1063/1.4926994}."


def test_an_already_correct_macro_produces_nothing():
    source = f"{JACOW}A. Author, \\doi{{10.1063/1.4926994}}\n"
    assert doi_format_edits(source) == []


def test_a_paper_that_cannot_render_the_macro_gets_the_safe_form_instead():
    """Emitting \\doi{} where it is undefined turns a formatting fix into a
    build failure. The prefix is normalised instead, and the message says why."""
    source = "\\documentclass{article}\nA. Author. DOI: 10.1109/PAC.2007.4440878\n"

    edits = doi_format_edits(source)

    assert _pairs(edits) == [("DOI: 10.1109/PAC.2007.4440878",
                          "doi:10.1109/PAC.2007.4440878")]
    assert "does not provide" in edits[0].message


@pytest.mark.parametrize(("source", "available"), [
    (JACOW, True),
    ("\\documentclass{article}\n\\providecommand{\\doi}[1]{}\n", True),
    ("\\documentclass{article}\nsee \\doi{10.1109/PAC.2007.4440878}\n", True),
    ("\\documentclass{article}\n", False),
])
def test_the_doi_macro_is_only_assumed_where_it_exists(source: str, available: bool):
    assert has_doi_macro(source) is available


# ---------------------------------------------------------------------------
# 2. \qty{N}{unit}
# ---------------------------------------------------------------------------

def test_a_measurement_becomes_qty_where_siunitx_is_loaded():
    source = f"{JACOW}{SIUNITX}A pulse of 284.5 ms was measured.\n"

    assert _pairs(unit_edits(source)) == [("284.5 ms", "\\qty{284.5}{ms}")]


def test_unit_case_is_still_corrected_inside_qty():
    source = f"{JACOW}{SIUNITX}running at 5 mhz today\n"

    edits = unit_edits(source)

    assert _pairs(edits) == [("5 mhz", "\\qty{5}{MHz}")]
    assert edits[0].check_id == "FMT-UNIT-02"       # still a decision, not auto


def test_without_siunitx_the_non_breaking_space_is_used():
    """Same reason as the DOI macro: \\qty{} would not compile."""
    source = f"{JACOW}A pulse of 284.5 ms was measured.\n"

    assert _pairs(unit_edits(source)) == [("284.5 ms", "284.5~ms")]


def test_an_ambiguous_unit_is_not_case_corrected_even_inside_qty():
    """The milligauss lesson survives the change of output form."""
    source = f"{JACOW}{SIUNITX}a stray field of 0.5 mG at the wall\n"

    for before, after in _pairs(unit_edits(source)):
        assert "mG" in after, f"{before} -> {after} changed the unit's meaning"


def test_a_measurement_that_is_already_correct_is_left_alone():
    """Converting every correct '10~MeV' as well would put sixty edits on a
    paper with nothing wrong with it."""
    source = f"{JACOW}{SIUNITX}a beam of 10~MeV protons\n"

    assert unit_edits(source) == []


@pytest.mark.parametrize(("source", "available"), [
    (SIUNITX, True),
    ("a value of \\qty{3}{m}\n", True),
    ("\\documentclass{article}\n", False),
])
def test_siunitx_is_only_assumed_where_it_exists(source: str, available: bool):
    assert has_siunitx(source) is available


# ---------------------------------------------------------------------------
# 3. \emph{et al.}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["et al", "et. al", "et. al.", "et al"])
def test_et_al_is_italicised(written: str):
    source = f"A. Author {written}, Title\n"

    assert _pairs(etal_edits(source)) == [(written, "\\emph{et al.}")]


def test_an_already_italicised_et_al_is_not_wrapped_twice():
    """Nesting \\emph{\\emph{...}} is a defect, not a stronger italic."""
    source = "A. Author \\emph{et al}, Title\n"

    assert _pairs(etal_edits(source)) == [("et al", "et al.")]


def test_a_correct_emphasised_et_al_produces_nothing():
    assert etal_edits("A. Author \\emph{et al.}, Title\n") == []


# ---------------------------------------------------------------------------
# 4. The bibliography mechanism is the author's business
# ---------------------------------------------------------------------------

def test_a_hand_written_reference_list_is_not_reported(tmp_path):
    """The JACoW class supports both, by commenting the biblatex option in or
    out, and the editors treat neither as a problem."""
    from src.parser.latex_parser import parse_latex

    source = (JACOW + "\\begin{document}\n\\title{T}\n\\maketitle\n"
              "\\begin{thebibliography}{9}\n"
              "\\bibitem{a} A. Author, Title, 2024.\n"
              "\\end{thebibliography}\n\\end{document}\n")
    path = tmp_path / "P.tex"
    path.write_text(source, encoding="utf-8")

    paper = parse_latex(path)
    from src.checks import template_checks

    template_checks.run_all(paper)

    assert not [f for f in paper.findings if f.check_id == "JACOW-CLS-03"]


def test_classic_bibtex_with_a_doi_dropping_style_is_still_an_error(tmp_path):
    """The neighbouring check must not be switched off with it: ieeetr really
    does drop every DOI from the PDF."""
    from src.parser.latex_parser import parse_latex

    source = (JACOW + "\\begin{document}\n\\title{T}\n\\maketitle\n"
              "\\bibliographystyle{ieeetr}\n\\bibliography{P}\n\\end{document}\n")
    path = tmp_path / "Q.tex"
    path.write_text(source, encoding="utf-8")

    from src.checks import template_checks

    paper = parse_latex(path)
    template_checks.run_all(paper)

    assert [f for f in paper.findings if f.check_id == "JACOW-CLS-02"]
