"""Reference formatting & enrichment subpackage.

Migrated from the standalone JACoW Reference Formatter (v1.0.0).
Each module is import-light; network features (JabRef CSVs, LTWA, jacow-events.bib)
are lazily fetched and gracefully degrade when offline.

Public surface
--------------
- :func:`title_similarity` – Jaccard+Dice token/bigram similarity for titles.
- :func:`normalize_journal` – L1/L2/L3 cascade to JACoW ISO 4 abbreviation.
- :class:`JacoWConnector` – conference metadata (city, country, month).
- :func:`format_ref` – per-type JACoW formatter dispatch (15 ref types).
- :func:`fmt_authors`, :func:`parse_authors` – author-list utilities.
- :func:`split_refs` – split a multi-reference block into individual strings.
"""

from src.refs.conference_db import JacoWConnector
from src.refs.conflicts import detect_conflicts
from src.refs.detect_type import detect_type
from src.refs.extract import extract_conference, extract_from_raw
from src.refs.formatters import (
    FORMATTERS,
    REF_TYPE_ALIASES,
    canonicalize_ref_type,
    format_ref,
    split_refs,
)
from src.refs.journal_abbrev import list_jabref_csvs, normalize_journal
from src.refs.lookup import isbn_publisher_lookup
from src.refs.merge import merge_crossref
from src.refs.similarity import title_similarity
from src.refs.text_utils import clean_title, fmt_authors, parse_authors, sent_case

__all__ = [
    "FORMATTERS",
    "JacoWConnector",
    "REF_TYPE_ALIASES",
    "canonicalize_ref_type",
    "clean_title",
    "detect_conflicts",
    "detect_type",
    "extract_conference",
    "extract_from_raw",
    "fmt_authors",
    "format_ref",
    "isbn_publisher_lookup",
    "list_jabref_csvs",
    "merge_crossref",
    "normalize_journal",
    "parse_authors",
    "sent_case",
    "split_refs",
    "title_similarity",
]
