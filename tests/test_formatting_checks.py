from pathlib import Path

from src.checks.formatting_checks import run_all
from src.parser.latex_parser import parse_latex


def _parse(tmp_path: Path, source: str):
    tex_path = tmp_path / "paper.tex"
    tex_path.write_text(source, encoding="utf-8")
    return parse_latex(tex_path)


def test_deterministic_formatting_checks_title_author_and_units(tmp_path: Path):
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
    assert check_ids.count("FMT-AUTH-01") == 1
    assert check_ids.count("FMT-UNIT-01") == 2
    assert "FMT-UNIT-02" in check_ids
    assert not any(finding.original == "2~m" for finding in paper.findings)


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

    assert paper.findings == []


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
