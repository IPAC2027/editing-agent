"""Layout and page-count checks (PAGE-*)."""

from __future__ import annotations

import re
from pathlib import Path

from src.models import Finding, Paper, Severity


def _add(paper: Paper, check_id: str, sev: Severity, msg: str,
         suggested: str | None = None) -> None:
    paper.findings.append(Finding(
        check_id=check_id, severity=sev, message=msg, suggested=suggested,
    ))


# ---------------------------------------------------------------------------
# PAGE-LIMIT-01 — 3-page body limit; only references may appear on page 4
# ---------------------------------------------------------------------------

def check_page_limit(paper: Paper, pdf_path: Path) -> None:
    """PAGE-LIMIT-01: body content must fit in 3 pages; only the reference list
    is allowed to overflow onto page 4."""
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        return  # pdfplumber unavailable

    try:
        with pdfplumber.open(pdf_path) as pdf:
            n_pages = len(pdf.pages)

            if n_pages <= 3:
                return  # within limit

            if n_pages >= 5:
                _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                     f"Paper is {n_pages} pages. Body content must fit in 3 pages; "
                     "only the reference list is allowed on page 4.",
                     suggested="Shorten body text to fit within 3 pages.")
                return

            # ---- exactly 4 pages ----------------------------------------
            # Find which page the REFERENCES section heading appears on.
            # A heading extracted from the PDF is typically its own line.
            refs_heading_page: int | None = None
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if re.search(r'(?:^|\n)\s*REFERENCES\s*(?:\n|$)', text,
                             re.IGNORECASE):
                    refs_heading_page = page_num
                    break

            if refs_heading_page is None:
                # No heading found; fall back to a heuristic on page 4.
                # If page 4 has an all-caps section heading (other than a
                # reference-list continuation) it is likely body content.
                page4_text = (pdf.pages[3].extract_text() or "").strip()
                if re.search(r'(?:^|\n)\s*[A-Z][A-Z ]{3,}\s*(?:\n|$)',
                             page4_text):
                    _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                         "Page 4 appears to contain body content (section heading "
                         "detected). Only the reference list is allowed on page 4.",
                         suggested="Shorten body text to fit within 3 pages.")
                # Cannot determine further without finding the heading; skip.
                return

            if refs_heading_page >= 4:
                # The REFERENCES heading itself is on page 4, meaning body text
                # (conclusion, acknowledgements, etc.) also occupies page 4.
                _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                     "Body content overflows onto page 4. "
                     "Only the reference list is allowed on page 4. "
                     "Shorten body text so the REFERENCES section starts on "
                     "page 3 or earlier.",
                     suggested="Reduce body text to fit within 3 pages.")

            # refs_heading_page <= 3: references begin on page 3 (or earlier)
            # and naturally continue onto page 4 — this is within the rules.

    except Exception:
        return  # any PDF parsing failure: skip silently


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all(paper: Paper, pdf_path: Path) -> None:
    """Run all layout checks that require a compiled PDF."""
    check_page_limit(paper, pdf_path)
