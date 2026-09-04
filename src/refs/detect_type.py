"""Reference-type classifier.

Migrated from the v1.0.0 standalone formatter (line 3146).  Inspects
both the parsed ``rec`` dict and the raw citation string to choose
one of 15 JACoW reference types.

Public surface: :func:`detect_type`.  Pure function, no I/O.

The classification order matters — type flags (thesis/patent) and
"this conference" / "to be published" / "submitted for publication"
markers in the raw text take precedence over field-based heuristics,
so a thesis flag always classifies as ``thesis`` regardless of any
other markers the raw text carries.
"""

from __future__ import annotations

import re


def detect_type(rec: dict, raw: str = "") -> str:
    """Classify a parsed *rec* (and optionally the *raw* citation text)
    into one of the 15 JACoW reference types.

    Returns one of:
    ``journal``, ``journal_accepted``, ``journal_submitted``,
    ``conference_published``, ``conference_unpublished``,
    ``conference_current``, ``arxiv``, ``web``, ``book``,
    ``book_chapter``, ``report``, ``thesis``, ``patent``,
    ``unpublished``, ``private_comm``.

    Decision order
    --------------
    1. Explicit type flags (``is_thesis`` / ``is_patent``).
    2. Sentinels in the raw text (``submitted for publication``,
       ``to be published``, ``this conference``, ``presented at``,
       ``private communication``, ``unpublished``).
    3. Conference or journal markers in the *rec* dict.
    4. Book / book-chapter distinction based on
       ``booktitle`` + ``(editor or pages)``.
    5. URL-only or publisher-only refs.
    6. Report-detection by ``rep_id`` / ``institution`` or title
       keywords (``user manual``, ``technical note``, etc.).
    7. Fallback: ``journal``.
    """
    if rec.get("is_thesis"):
        return "thesis"
    if rec.get("is_patent"):
        return "patent"

    # The title quote is excluded so a "Title: in Proc. NAPAC'16" line
    # inside a quoted title doesn't get mis-classified as a conf paper.
    raw_no_title = re.sub(
        r'["“«].*?["”»]', "", raw or "", flags=re.DOTALL,
    )
    raw_lo = raw_no_title.lower()

    if "submitted for publication" in raw_lo:
        return "journal_submitted"
    if "to be published" in raw_lo:
        return "journal_accepted"
    if "this conference" in raw_lo:
        return "conference_current"
    if "presented at" in raw_lo:
        return "conference_unpublished"
    if rec.get("conference"):
        return "conference_published"
    if "private communication" in raw_lo:
        return "private_comm"
    if re.search(r"\bunpublished\b", raw_lo):
        return "unpublished"

    # Published venue takes precedence over arXiv ID — a paper with
    # both an arXiv preprint and a journal DOI is classified as journal.
    if rec.get("journal") or rec.get("volume"):
        return "journal"
    if rec.get("arxiv_id"):
        return "arxiv"

    # Book chapter: has a booktitle (the containing book) AND either
    # an editor or page range.  Without those, treat it as a bare book
    # reference (the standalone falls through to "journal" here, which
    # is a misclassification — a ref with a booktitle that isn't a
    # chapter is a book, not a journal).
    if rec.get("booktitle"):
        if rec.get("editor") or rec.get("pages"):
            return "book_chapter"
        return "book"
    if rec.get("publisher"):
        return "book"
    if rec.get("url"):
        return "web"

    # Technical reports: explicit report fields or report-like title
    # keywords.
    if rec.get("rep_id") or rec.get("institution"):
        return "report"
    title_lo = (rec.get("title") or "").lower()
    if re.search(
        r"\b(?:user\s+manual|technical\s+(?:note|report)|design\s+report|"
        r"internal\s+note|engineer(?:ing)?\s+note)\b",
        title_lo,
    ):
        return "report"

    return "journal"
