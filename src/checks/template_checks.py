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
        _add(paper, "JACOW-CLS-01", Severity.INFO,
             f"Could not detect the JACoW class version from template comments. "
             f"Latest version is v{JACOW_LATEST_VERSION} ({JACOW_LATEST_DATE}). "
             f"Download from https://jacow.org/Authors/Templates")
    elif ver != JACOW_LATEST_VERSION:
        # INFO, not WARNING: the template version is the same for every paper in
        # a conference, it is not something an editor fixes per submission, and
        # the "latest" value here is a hardcoded constant this tool does not
        # verify against jacow.org.  Reporting it as a warning on all 34 sample
        # papers was the single largest source of repeated noise.
        _add(paper, "JACOW-CLS-01", Severity.INFO,
             f"Template version v{ver}; this build of the agent knows about "
             f"v{JACOW_LATEST_VERSION} ({JACOW_LATEST_DATE}) — not verified against "
             f"jacow.org. Newer templates fix rendering bugs: "
             f"https://jacow.org/Authors/Templates",
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
        # Deliberately silent. Whether the references live in a .bib read by
        # BibLaTeX or are written out inside the .tex is the author's choice —
        # the JACoW class supports both, by commenting the biblatex option in
        # or out — and the editors do not treat either as a problem. Reporting
        # a preference here only spent an editor's attention on a decision that
        # was never theirs to make.
        pass
    elif pt.bibliography_env == "bibtex" and not pt.uses_biblatex:
        _add(paper, "JACOW-CLS-02", Severity.ERROR,
             "The paper uses classic BibTeX with a traditional style. Styles like "
             "ieeetr do not print the 'doi' field at all, so every DOI in the "
             ".bib file will be missing from the published PDF.",
             suggested="Use \\documentclass[biblatex,...]{jacow} + \\addbibresource{<paper>.bib}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all(paper: Paper) -> None:
    """Run every template/class check against *paper*."""
    check_jacow_class_version(paper)
    check_bibliography_style(paper)
