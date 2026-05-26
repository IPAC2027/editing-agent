"""Safe, deterministic auto-fixes applied directly to LaTeX source text.

Rules
-----
- Only the fixes listed in IMPLEMENTATION_PLAN §3.4 may be applied here.
- Never invent bibliography metadata.
- Return the modified source string and a list of ``Finding`` objects with
  ``auto_fixed=True`` so the diff can record what changed.

Fixes implemented
-----------------
- Normalise spaces inside citation brackets:  [ 3 ]  →  [3]
- Merge adjacent single-key cites:            [1][2] →  [1, 2]
- Normalise doi prefix casing/format:         DOI 10.x  →  doi:10.x
- Strip extra spaces around commas in multi-cites: [3,4] → [3, 4]
- Normalise et al. punctuation:               et. al. / Et al  →  et al.
"""

from __future__ import annotations

from src.models import Finding


def apply_safe_fixes(source: str) -> tuple[str, list[Finding]]:
    """Apply all safe fixes to *source* and return the modified text plus findings.

    Parameters
    ----------
    source:
        Full content of the .tex file.

    Returns
    -------
    tuple[str, list[Finding]]
        ``(modified_source, findings)`` where every finding has ``auto_fixed=True``.
    """
    raise NotImplementedError("safe_fixes.apply_safe_fixes() not yet implemented")
