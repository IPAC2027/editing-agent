"""Conflict detection between two authoritative metadata sources.

Migrated from the v1.0.0 standalone formatter (line 4281).  Pure
function — takes two already-fetched metadata dicts and returns a list
of human-readable conflict descriptions.

Per §9 of the standalone spec, a non-empty conflict list should
cause a ``ValidationError`` to be raised by the caller.  The package
uses this to surface disagreements between refs.jacow.org and
Crossref / InspireHEP so the user isn't silently given whichever
ran second.

Public surface: :func:`detect_conflicts`.  Pure function, no I/O.
"""

from __future__ import annotations

import re
from typing import Optional


def _norm(s: str) -> str:
    """Normalise a string for conflict comparison (case + whitespace + punct)."""
    return re.sub(r"[^\w]", "", (s or "").lower()).strip()


def detect_conflicts(
    cr_data: dict,
    other_data: Optional[dict],
) -> list[str]:
    """Compare *cr_data* against *other_data* and return conflict messages.

    An empty list means no conflicts.  *other_data* may be ``None`` (e.g.
    when InspireHEP returned nothing) — in that case we trivially return
    no conflicts.

    Conflicts are flagged when both sources provide a value for the
    same field and those values disagree by more than a trivial
    normalisation difference.  Per the standalone, the fields
    checked are DOI, year, and volume.  Volumes are only flagged when
    both look like conventional volume labels (≤4 chars) so long
    InspireHEP record IDs don't produce spurious errors.
    """
    if not other_data:
        return []

    conflicts: list[str] = []

    # DOI
    cr_doi = _norm(cr_data.get("doi", ""))
    other_doi = _norm(other_data.get("doi", ""))
    if cr_doi and other_doi and cr_doi != other_doi:
        conflicts.append(
            f"DOI mismatch: Crossref={cr_data.get('doi')!r} "
            f"vs other={other_data.get('doi')!r}"
        )

    # Year
    cr_year = str(cr_data.get("year") or "").strip()
    other_year = str(other_data.get("year") or "").strip()
    if cr_year and other_year and cr_year != other_year:
        conflicts.append(
            f"Year mismatch: Crossref={cr_year!r} vs other={other_year!r}"
        )

    # Volume
    cr_vol = str(cr_data.get("volume") or "").strip()
    other_vol = str(other_data.get("volume") or "").strip()
    if (
        cr_vol
        and other_vol
        and cr_vol != other_vol
        and len(cr_vol) <= 4
        and len(other_vol) <= 4
    ):
        conflicts.append(
            f"Volume mismatch: Crossref={cr_vol!r} vs other={other_vol!r}"
        )

    return conflicts
