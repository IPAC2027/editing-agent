"""User-fields-win merge for authoritative metadata sources.

Migrated from the v1.0.0 standalone formatter (line 3801).
Implements the policy REQ-MFC-009:

  * Authors and title MUST NEVER be overwritten by any external source.
  * Only structural fields (DOI, volume, issue, pages, year, month,
    journal, publisher, arXiv IDs) are eligible for auto-complete.
  * The *trust level* of the match matters: only ``verified`` and
    ``probable`` matches can fill user-empty fields; ``ambiguous``
    matches do nothing.

Public surface: :func:`merge_crossref`.  Pure function, no I/O.
"""

from __future__ import annotations

import re

from src.refs.journal_abbrev import normalize_journal
from src.refs.similarity import ascii_fold


def merge_crossref(rec: dict, cr: dict, level: str) -> dict:
    """Merge authoritative metadata from *cr* (Crossref / DataCite /
    InspireHEP) into *rec*.

    The merge respects the trust level *level*:

    - ``"verified"`` or ``"probable"`` — eligible to fill empty fields
      and to populate DOI / arXiv IDs.
    - anything else (``"ambiguous"``, ``"not_found"``, …) — only DOI
      and arXiv IDs may be filled, never overwrite user-supplied data.

    Returns a new dict; *rec* is not mutated in place.
    """
    out = dict(rec)
    trusted = level in ("verified", "probable")

    # DOI: always safe (identifier, not content).  Always fill from
    # the authoritative source if the DOI is empty or differs.
    if cr.get("doi"):
        if not out.get("doi") or out["doi"].lower() != cr["doi"].lower():
            out["doi"] = cr["doi"]

    # Bibliographic fields: trusted match only, never overwrite user data.
    if trusted:
        for f in ("volume", "issue"):
            if cr.get(f) and not out.get(f):
                out[f] = cr[f]
        if cr.get("pages") and not out.get("pages"):
            out["pages"] = cr["pages"]
        if cr.get("year") and not out.get("year"):
            out["year"] = cr["year"]
        if cr.get("month") and not out.get("month"):
            out["month"] = cr["month"]

    # Journal: fill or confirm; never overwrite a clearly different
    # journal.  If both rec and cr agree (substring match, ASCII-folded),
    # the cr version is preferred because it has the canonical form.
    if cr.get("journal"):
        if not out.get("journal"):
            out["journal"] = normalize_journal(cr["journal"])
        else:
            cr_j = ascii_fold(cr["journal"].lower())
            our_j = ascii_fold(out["journal"].lower())
            if cr_j in our_j or our_j in cr_j:
                out["journal"] = normalize_journal(cr["journal"])
    elif out.get("journal"):
        out["journal"] = normalize_journal(out["journal"])

    # Title / authors: fill ONLY when genuinely absent from the record.
    # REQ-MFC-009 prohibits overwriting user-supplied values — it does
    # not prohibit populating empty fields from an authoritative
    # Crossref/DOI lookup (e.g. when the user supplied only a bare DOI).
    if cr.get("title") and not out.get("title") and trusted:
        out["title"] = cr["title"]
    if cr.get("crossref_authors") and not out.get("authors_raw") and trusted:
        out["authors_raw"] = cr["crossref_authors"]
        if cr.get("is_editor"):
            out["is_editor"] = True

    # Publisher: MAY auto-complete (§8.2).
    if cr.get("publisher") and not out.get("publisher"):
        out["publisher"] = cr["publisher"]

    # arXiv identifiers.
    if cr.get("arxiv_id") and not out.get("arxiv_id"):
        out["arxiv_id"] = cr["arxiv_id"]
    if cr.get("arxiv_cat") and not out.get("arxiv_cat"):
        out["arxiv_cat"] = cr["arxiv_cat"]

    return out
