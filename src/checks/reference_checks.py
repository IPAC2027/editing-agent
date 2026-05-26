"""Priority-1 reference and citation checks.

Each public function accepts a ``Paper`` and appends ``Finding`` objects to
``paper.findings``.  None of them modify the source text — that is the job of
``src.autofix.safe_fixes``.

Checks implemented here
-----------------------
CITE-ORDER-01   Citation numbers appear in ascending first-occurrence order.
CITE-BRACKET-01 Adjacent single-key cites should be merged: [1][2] → [1, 2].
CITE-BRACKET-02 Consecutive runs should be collapsed to ranges: [1, 2, 3] → [1–3].
CITE-SPACE-01   Spaces inside citation brackets: [ 3 ] → [3].
CITE-LINK-01    Every \\cite{key} resolves to a bibliography entry.
CITE-LINK-02    Every bibliography entry is cited at least once (WARNING).
REF-SEC-01      A section titled REFERENCES exists.
REF-NUM-01      Each entry starts with [n].
REF-NUM-02      Reference numbers are consecutive starting at 1.
AUTH-01         Penultimate comma for ≥3 authors.
AUTH-02         >6 authors → et al.
TITLE-01        Paper titles in reference list are sentence case (heuristic).
PROC-REQ-01/02/03  Proceedings entries have required fields.
JOUR-REQ-01     Journal entries have volume/pages.
DOI-REQ-01      DOI present when detectable.
DOI-FMT-01      DOI is a single token, lowercase doi: prefix.
"""

from __future__ import annotations

from src.models import Paper


def check_citation_order(paper: Paper) -> None:
    """CITE-ORDER-01: first-occurrence citation numbers must be ascending."""
    raise NotImplementedError


def check_citation_brackets(paper: Paper) -> None:
    """CITE-BRACKET-01/02, CITE-SPACE-01: bracket formatting."""
    raise NotImplementedError


def check_citation_links(paper: Paper) -> None:
    """CITE-LINK-01/02: every cite resolves and every entry is cited."""
    raise NotImplementedError


def check_reference_structure(paper: Paper) -> None:
    """REF-SEC-01, REF-NUM-01/02: section heading and numbering."""
    raise NotImplementedError


def check_reference_entry_format(paper: Paper) -> None:
    """AUTH-*, TITLE-01, PROC-REQ-*, JOUR-REQ-01, DOI-*: Annex B rules."""
    raise NotImplementedError


def run_all(paper: Paper) -> None:
    """Run every reference check against *paper*, appending findings in-place."""
    check_citation_order(paper)
    check_citation_brackets(paper)
    check_citation_links(paper)
    check_reference_structure(paper)
    check_reference_entry_format(paper)
