"""BibTeX file parser.

Responsibilities
----------------
- Read a .bib file and return a list of ``Reference`` objects.
- Map each BibTeX entry type to the ``ref_type`` field:
    * ``@inproceedings`` / ``@proceedings``  →  ``"proceedings"``
    * ``@article``                           →  ``"journal"``
    * ``@misc`` with ``eprint``              →  ``"arxiv"``
    * ``@book``                              →  ``"book"``
    * ``@incollection``                      →  ``"chapter"``
    * ``@techreport``                        →  ``"report"``
    * ``@phdthesis`` / ``@mastersthesis``    →  ``"thesis"``
    * ``@misc`` with ``url``                 →  ``"online"``
    * ``@patent``                            →  ``"patent"``
    * everything else                        →  ``"unknown"``
- Extract: authors, title, booktitle/journal, year, volume, number (issue),
  pages, doi, url, address (venue_location), month, note.

Notes
-----
- Uses ``bibtexparser`` (v1.x API).
"""

from __future__ import annotations

from pathlib import Path

from src.models import Reference


def parse_bib(bib_path: Path) -> list[Reference]:
    """Parse *bib_path* and return one :class:`~src.models.Reference` per entry."""
    raise NotImplementedError("bib_parser.parse_bib() not yet implemented")
