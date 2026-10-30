"""Body-text and reference-form checks shared by Word and LaTeX."""
from __future__ import annotations

from src.checks import body_checks as bc


def _ids(findings):
    return sorted(f.check_id for f in findings)


def test_a_citation_in_the_abstract_is_reported():
    assert _ids(bc.check_body_text([], "We report results [1].")) == ["TXT-ABS-01"]
    assert bc.check_body_text([], "We report results.") == []


def test_callouts_follow_the_style_guide():
    text = ("The parameters are listed in Tab. 1. Fig. 2 shows the orbit. "
            "As seen in Fig. 3, the orbit is flat. As shown in equation 1, it "
            "converges, and Eq. 2 gives the size. Equation (3) is exact.")
    findings = bc.check_body_text([text], None)
    by_id = {(f.check_id, f.original): f.suggested for f in findings}
    assert by_id[("TXT-TAB-01", "Tab. 1")] == "Table 1"
    assert by_id[("TXT-FIG-01", "Fig. 2")] == "Figure 2"
    assert ("TXT-FIG-01", "Fig. 3") not in by_id          # mid-sentence is correct
    assert by_id[("TXT-EQ-01", "equation 1")] == "Eq. (1)"
    assert by_id[("TXT-EQ-01", "Eq. 2")] == "Eq. (2)"
    assert not any(orig.startswith("Equation (3)") for _, orig in by_id)


def test_correct_text_produces_nothing():
    text = "Figure 1 shows the layout. Table 1 lists it, and Eq. (1) gives it, see Fig. 2."
    assert bc.check_body_text([text], "A stand-alone abstract.") == []


def test_latex_is_flattened_before_checking():
    source = r"""
\begin{document}
\begin{abstract}A stand-alone abstract~\cite{x}.\end{abstract}
Results are in Tab.~\ref{tab:a}. Fig.~\ref{fig:b} shows them. % Tab. 9 in a comment
\begin{thebibliography}{9}\end{thebibliography}
"""
    abstract = bc.latex_to_text(bc.latex_abstract(source))
    body = bc.latex_to_text(bc.latex_body(source))
    ids = _ids(bc.check_body_text([body], abstract))
    assert ids == ["TXT-ABS-01", "TXT-FIG-01", "TXT-TAB-01"]


def test_unpublished_and_submitted_reference_forms():
    refs = [
        (1, "H. Nakamura, “A cryomodule”, in Proc. LINAC’22, Liverpool, UK, Aug. 2022, unpublished."),
        (2, "D. Okonkwo and S. Quist, “Thermal shields”, submitted to Cryogenics."),
        (3, "A. Alpha, “Title of talk”, presented at IPAC’14, Dresden, Germany, Jun. 2014, unpublished."),
        (4, "G. D. Read, “Title of paper”, submitted for publication."),
    ]
    findings = bc.check_reference_forms(refs)
    assert [(f.check_id, f.line) for f in findings] == [("REF-FORM-01", 1), ("REF-FORM-02", 2)]
    assert all(f.line is None for f in bc.check_reference_forms(refs, attach_to_reference=False))


def test_citations_in_separate_brackets_are_merged():
    findings = bc.check_body_text(["As described previously [1], [2] and [4][5]."], None)
    merged = {f.original: f.suggested for f in findings if f.check_id == "TXT-CITE-01"}
    assert merged == {"[1], [2]": "[1, 2]", "[4][5]": "[4, 5]"}
