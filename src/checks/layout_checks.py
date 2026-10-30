"""Layout and page-count checks (PAGE-*)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.models import Finding, Paper, Severity


def _add(paper: Paper, check_id: str, sev: Severity, msg: str,
         suggested: str | None = None) -> None:
    paper.findings.append(Finding(
        check_id=check_id, severity=sev, message=msg, suggested=suggested,
    ))


# ---------------------------------------------------------------------------
# PAGE-LIMIT-01 — body pages limit; only references may run onto the next page
# ---------------------------------------------------------------------------

DEFAULT_BODY_PAGES = 3


def body_page_limit() -> int:
    """The conference's body-page limit: ``JACOW_BODY_PAGES`` in .env, default 3.

    Page limits differ between JACoW conferences, so this is a setting rather
    than a constant.  An invalid value falls back to the default.
    """
    try:
        value = int(os.getenv("JACOW_BODY_PAGES", "").strip() or DEFAULT_BODY_PAGES)
    except ValueError:
        return DEFAULT_BODY_PAGES
    return value if value > 0 else DEFAULT_BODY_PAGES


def _pages(n: int) -> str:
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    return f"{words.get(n, n)} page{'s' if n != 1 else ''}"


def check_page_limit(paper: Paper, pdf_path: Path, *, body_pages: int | None = None) -> None:
    """PAGE-LIMIT-01: body content must fit in *body_pages* pages; only the
    reference list may continue onto the page after that."""
    limit = body_pages or body_page_limit()
    overflow_page = limit + 1
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        _add(paper, "PAGE-LIMIT-01", Severity.INFO,
             "NOT CHECKED — the page limit was not checked: the PDF library "
             "(pdfplumber) is not installed.")
        return

    try:
        with pdfplumber.open(pdf_path) as pdf:
            n_pages = len(pdf.pages)
            if n_pages <= limit:
                return
            if n_pages > overflow_page:
                _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                     f"Paper is {n_pages} pages. Body content must fit in {_pages(limit)}; "
                     f"only the reference list may continue onto page {overflow_page}.",
                     suggested=f"Shorten body text to fit within {_pages(limit)}.")
                return

            # Exactly one page over: allowed only if the references start
            # on or before the last body page.
            refs_heading_page: int | None = None
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if re.search(r'(?:^|\n)\s*REFERENCES\s*(?:\n|$)', text, re.IGNORECASE):
                    refs_heading_page = page_num
                    break

            if refs_heading_page is None:
                last_text = (pdf.pages[limit].extract_text() or "").strip()
                if re.search(r'(?:^|\n)\s*[A-Z][A-Z ]{3,}\s*(?:\n|$)', last_text):
                    _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                         f"Page {overflow_page} appears to contain body content (section "
                         f"heading detected). Only the reference list may be on page "
                         f"{overflow_page}.",
                         suggested=f"Shorten body text to fit within {_pages(limit)}.")
                return

            if refs_heading_page >= overflow_page:
                _add(paper, "PAGE-LIMIT-01", Severity.WARNING,
                     f"Body content overflows onto page {overflow_page}. Only the reference "
                     f"list may be on page {overflow_page}. Shorten the body text so the "
                     f"REFERENCES section starts on page {limit} or earlier.",
                     suggested=f"Reduce body text to fit within {_pages(limit)}.")
    except Exception as exc:  # noqa: BLE001
        # Previously swallowed silently, which looked exactly like a pass.
        _add(paper, "PAGE-LIMIT-01", Severity.INFO,
             f"NOT CHECKED — the page limit was not checked: the PDF could not be read "
             f"({type(exc).__name__}).")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all(paper: Paper, pdf_path: Path) -> None:
    """Run all layout checks that require a compiled PDF."""
    check_page_limit(paper, pdf_path)
