"""JACoW template / class-file checks (JACOW-CLS-*)."""

from __future__ import annotations

from src.models import Finding, Paper, Severity
from src.parser.latex_parser import JACOW_LATEST_VERSION, JACOW_LATEST_DATE, ParsedTex


def _pt(paper: Paper) -> ParsedTex:
    return paper.__dict__.get('_pt')  # type: ignore[return-value]


def _add(paper: Paper, check_id: str, sev: Severity, msg: str,
         line: int | None = None, original: str | None = None,
         suggested: str | None = None) -> None:
    paper.findings.append(Finding(
        check_id=check_id,
        severity=sev,
        line=line,
        original=original,
        suggested=suggested,
        message=msg,
    ))


# ---------------------------------------------------------------------------
# JACOW-CLS-01 — template version must be latest
# ---------------------------------------------------------------------------

def check_jacow_class_version(paper: Paper) -> None:
    """JACOW-CLS-01: warn if the template is not the latest version."""
    pt = _pt(paper)
    if not pt:
        return
    ver = pt.template_version
    if not ver:
        _add(paper, "JACOW-CLS-01", Severity.WARNING,
             f"Could not detect the JACoW class version from template comments. "
             f"Latest version is v{JACOW_LATEST_VERSION} ({JACOW_LATEST_DATE}). "
             f"Download from https://jacow.org/Authors/Templates")
    elif ver != JACOW_LATEST_VERSION:
        _add(paper, "JACOW-CLS-01", Severity.WARNING,
             f"Template version v{ver} detected. Latest is v{JACOW_LATEST_VERSION} "
             f"({JACOW_LATEST_DATE}). Update from https://jacow.org/Authors/Templates",
             original=f"% v {ver}",
             suggested=f"% v {JACOW_LATEST_VERSION}  {JACOW_LATEST_DATE}")


# ---------------------------------------------------------------------------
# JACOW-CLS-02 — prefer BibLaTeX over manual \bibitem
# ---------------------------------------------------------------------------

def check_bibliography_style(paper: Paper) -> None:
    """JACOW-CLS-02: manual \\thebibliography is discouraged; prefer BibLaTeX.
    Also warn when classic BibTeX (\\bibliographystyle) is used because common
    styles like ieeetr do not render the doi field."""
    pt = _pt(paper)
    if not pt:
        return
    if pt.bibliography_env == "thebibliography" and not pt.uses_biblatex:
        _add(paper, "JACOW-CLS-02", Severity.WARNING,
             "Manual \\thebibliography / \\bibitem detected. "
             "JACoW class ≥ v2.10 supports BibLaTeX which is strongly preferred "
             "for consistent reference formatting. Consider switching.",
             suggested="Use \\documentclass[biblatex,...]{jacow} + \\addbibresource{<paper>.bib}")
    elif pt.bibliography_env == "bibtex" and not pt.uses_biblatex:
        _add(paper, "JACOW-CLS-02", Severity.ERROR,
             "Classic BibTeX (\\bibliographystyle + \\bibliography) detected. "
             "Most traditional styles (e.g. ieeetr) do not render the 'doi' field, "
             "so DOIs stored in your .bib will not appear in the PDF. "
             "Switch to BibLaTeX for correct DOI rendering.",
             suggested="Use \\documentclass[biblatex,...]{jacow} + \\addbibresource{<paper>.bib}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all(paper: Paper) -> None:
    """Run every template/class check against *paper*."""
    check_jacow_class_version(paper)
    check_bibliography_style(paper)
