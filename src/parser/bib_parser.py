"""BibTeX file parser — Phase 1 implementation."""

from __future__ import annotations

import re
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

from src.models import Reference

# Map BibTeX entry types to our internal type names
_ENTRYTYPE_MAP: dict[str, str] = {
    "inproceedings": "proceedings",
    "proceedings":   "proceedings",
    "article":       "journal",
    "book":          "book",
    "incollection":  "chapter",
    "techreport":    "report",
    "phdthesis":     "thesis",
    "mastersthesis": "thesis",
    "patent":        "patent",
    "misc":          "misc",   # refined below
    "unpublished":   "unpublished",
}


def _customise(record: dict) -> dict:
    """bibtexparser customisation hook."""
    return convert_to_unicode(record)


def _strip_inline_bib_comments(text: str) -> str:
    """Remove %-commented lines from inside BibTeX entry bodies.

    BibTeX does not define ``%`` as a comment character, but many authors use
    it to comment-out alternative field values.  bibtexparser v1 chokes on
    these and silently drops the entire entry.  We strip any line whose
    non-whitespace content starts with ``%`` while we are inside an ``@``
    entry block, preserving all other content unchanged.
    """
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    depth = 0          # brace depth; > 0 means we're inside an @entry{...}
    in_entry = False

    for line in lines:
        stripped = line.lstrip()

        # Detect start of a @type{ entry
        if not in_entry and stripped.startswith('@') and '{' in line:
            in_entry = True

        if in_entry:
            # Count braces to track when the entry closes
            for ch in line:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            if depth <= 0:
                in_entry = False
                depth = 0

            # Drop lines that are commented-out field definitions
            if stripped.startswith('%'):
                continue   # skip this line

        result.append(line)
    return ''.join(result)


def parse_bib(bib_path: Path) -> list[Reference]:
    """Parse *bib_path* and return one :class:`~src.models.Reference` per entry."""
    text = bib_path.read_text(encoding="utf-8", errors="replace")

    # bibtexparser v1 silently drops entries that contain %-commented lines
    # inside the entry body (e.g. % booktitle = {...}).  Strip those lines
    # before handing off to the parser.
    text = _strip_inline_bib_comments(text)

    parser = BibTexParser(common_strings=True)
    # bibtexparser only defines month abbreviations (jan, feb, …).
    # Some .bib files use full unquoted names (month = february) which
    # cause UndefinedString exceptions.  Add them here.
    parser.bib_database.strings.update({
        'january': 'January', 'february': 'February', 'march': 'March',
        'april': 'April', 'may': 'May', 'june': 'June',
        'july': 'July', 'august': 'August', 'september': 'September',
        'october': 'October', 'november': 'November', 'december': 'December',
    })
    parser.customization = _customise
    parser.ignore_nonstandard_types = False

    db = bibtexparser.loads(text, parser=parser)

    refs: list[Reference] = []
    for n, entry in enumerate(db.entries, start=1):
        etype = entry.get("ENTRYTYPE", "misc").lower()
        ref_type = _ENTRYTYPE_MAP.get(etype, "unknown")

        # Refine @misc: check for eprint/arxiv, url, note
        if ref_type == "misc":
            if entry.get("eprint") or "arxiv" in entry.get("note", "").lower():
                ref_type = "arxiv"
            elif entry.get("url") or entry.get("howpublished", "").startswith("\\url"):
                ref_type = "online"

        # Authors
        raw_authors = entry.get("author", "")
        authors = _split_authors(raw_authors)

        # Pages normalisation: "269--292" → "269-292" (we keep as-is; linter checks)
        pages = entry.get("pages", "") or None

        # DOI: strip any leading "https://doi.org/" prefix for storage
        doi_raw = entry.get("doi", "") or ""
        doi = _normalise_doi(doi_raw) or None

        # URL
        url = entry.get("url", "") or entry.get("bdsk-url-1", "") or None

        # Venue location: from "venue" field (JACoW-specific) or "address"
        venue_location = entry.get("venue") or entry.get("address") or None

        # Container title
        container = (
            entry.get("booktitle")
            or entry.get("journal")
            or entry.get("series")
            or None
        )

        # Date
        year = entry.get("year", "")
        month = entry.get("month", "")
        date = f"{month} {year}".strip() if month else year or None

        # Raw text: rebuild a minimal one-line summary
        raw_text = _build_raw(entry)

        refs.append(Reference(
            n=n,
            key=entry.get("ID", f"ref{n}"),
            ref_type=ref_type,
            authors=authors,
            title=entry.get("title", "").strip("{}"),
            container_title=container.strip("{}") if container else None,
            venue_location=venue_location,
            date=date or None,
            volume=entry.get("volume") or None,
            issue=entry.get("number") or None,
            pages=pages,
            doi=doi,
            url=url,
            paper_id=entry.get("paper") or None,
            notes=[entry.get("note", "")] if entry.get("note") else [],
            raw_text=raw_text,
        ))
    return refs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_authors(raw: str) -> list[str]:
    """Split a BibTeX author string on ' and ' into individual name strings."""
    if not raw:
        return []
    parts = re.split(r'\s+and\s+', raw, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _normalise_doi(doi: str) -> str:
    """Return just the DOI token (strip URL prefix if present)."""
    doi = doi.strip()
    doi = re.sub(r'^https?://doi\.org/', '', doi)
    doi = re.sub(r'^https?://dx\.doi\.org/', '', doi)
    return doi


def _build_raw(entry: dict) -> str:
    """Build a short single-line description of an entry for display."""
    authors = entry.get("author", "")
    title = entry.get("title", "").strip("{}")
    year = entry.get("year", "")
    return f"{authors}, \"{title}\", {year}".strip(", ")
