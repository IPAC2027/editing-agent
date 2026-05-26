"""LaTeX source parser.

Responsibilities
----------------
- Read a .tex file and return a ``Paper`` model.
- Extract:
    * ``\\title{}`` text
    * ``\\author{}`` block
    * All ``\\cite{key}`` and ``\\cite{key1,key2}`` calls, in source order,
      recording first-appearance line for each key  →  ``Paper.citation_order``
    * All ``\\bibitem{key}`` entries (manual bibliography)  →  ``Paper.references``
    * All ``\\label{fig:*}`` / ``\\label{tab:*}`` and their
      ``\\ref{}`` call sites  (for FMT-FIG-* and FMT-TBL-* checks)
    * All ``\\begin{figure}`` / ``\\caption{}`` blocks
    * All ``\\begin{table}`` / ``\\caption{}`` blocks

Notes
-----
- Uses ``pylatexenc`` for tokenisation where possible; falls back to regex.
- Does **not** execute or expand macros.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.models import Paper, Reference


def parse_latex(tex_path: Path) -> Paper:
    """Parse *tex_path* and return a populated :class:`~src.models.Paper`.

    Only fields extractable without running LaTeX are populated here.
    The ``findings`` list is left empty; checks populate it later.
    """
    raise NotImplementedError("latex_parser.parse_latex() not yet implemented")
