from src.models import Finding, Severity
from src.output.diff import write_diff


def test_html_diff_shows_fix_reason_on_hover(tmp_path):
    original = "The DOI is DOI: 10.1000/example.\n"
    modified = "The DOI is doi:10.1000/example.\n"
    findings = [
        Finding(
            check_id="DOI-FMT-01",
            severity=Severity.INFO,
            line=1,
            original="DOI: 10.1000/example.",
            suggested="doi:10.1000/example.",
            message="Normalised DOI prefix to 'doi:'.",
            auto_fixed=True,
        ),
    ]

    write_diff(original, modified, "paper.tex", tmp_path, findings)

    html = (tmp_path / "changes.html").read_text(encoding="utf-8")
    patch = (tmp_path / "changes.patch").read_text(encoding="utf-8")
    assert "Hover any highlighted edit to see its check ID and reason" in html
    assert "diff-highlight" in html
    assert 'data-repairs="repair-001"' in html
    assert "DOI-FMT-01: Normalised DOI prefix to &#x27;doi:&#x27;." in html
    assert "data-reason=" in html
    assert "Editor review" in html
    assert "Accept all" in html
    assert "review_decisions.json" in html
    assert "-The DOI is DOI: 10.1000/example." in patch
    assert "+The DOI is doi:10.1000/example." in patch


def test_html_diff_falls_back_to_finding_text_when_line_is_unavailable(tmp_path):
    original = "\\bibitem{key}\nOld reference\n"
    modified = "\\bibitem{key}\nNew reference\n"
    findings = [
        Finding(
            check_id="FMT-REF-01",
            severity=Severity.INFO,
            original="Old reference",
            suggested="New reference",
            message="Reformatted \\bibitem{key} per JACoW style.",
            auto_fixed=True,
        ),
    ]

    write_diff(original, modified, "paper.tex", tmp_path, findings)

    html = (tmp_path / "changes.html").read_text(encoding="utf-8")
    assert "FMT-REF-01: Reformatted \\bibitem{key} per JACoW style." in html
