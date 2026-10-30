"""Checks on a reference list as a whole (REF-SEC-01, REF-NUM-01/02, CITE-TEXT-02).

Formatting, lookups and integrity of each *individual* reference are done by
the reference formatter through :mod:`src.references`, for Word and LaTeX
alike.  What stays here is about the list: that there is one, that it is
numbered from [1] without gaps, and that citations first appear in order.

*document* is anything with ``has_references_section``, ``references``
(items with ``n``) and ``citations`` (items with ``number`` and
``paragraph_index``) — today a :class:`~src.parser.word_parser.ParsedWord`.
"""

from __future__ import annotations

from src.models import Finding, Severity


def _add(findings: list[Finding], check_id: str, sev: Severity, msg: str,
         ref_n: int | None = None,
         original: str | None = None,
         suggested: str | None = None,
         auto_fixed: bool = False) -> None:
    findings.append(Finding(
        check_id=check_id,
        severity=sev,
        line=ref_n,           # re-purpose line field for reference number
        original=original,
        suggested=suggested,
        message=msg,
        auto_fixed=auto_fixed,
    ))



def check_references_section(pw: object, findings: list[Finding]) -> None:
    """REF-SEC-01: document must contain a section titled 'REFERENCES'."""
    if not pw.has_references_section:
        _add(findings, "REF-SEC-01", Severity.ERROR,
             "No 'REFERENCES' section heading found in the document.")


# ---------------------------------------------------------------------------
# REF-NUM-01/02 — reference numbering
# ---------------------------------------------------------------------------

def check_reference_numbering(pw: object, findings: list[Finding]) -> None:
    """REF-NUM-01/02: entries must start with [n]; must be consecutive from [1]."""
    if not pw.references:
        if pw.has_references_section:
            _add(findings, "REF-NUM-01", Severity.WARNING,
                 "REFERENCES section found but no numbered entries detected.")
        return

    # REF-NUM-02: consecutive from 1
    nums = [r.n for r in pw.references]
    expected = list(range(1, len(nums) + 1))
    if nums != expected:
        bad = [(got, exp) for got, exp in zip(nums, expected) if got != exp]
        for got, exp in bad[:5]:  # report up to 5
            _add(findings, "REF-NUM-02", Severity.ERROR,
                 f"Reference [{got}] found where [{exp}] expected. "
                 "Reference numbers must be consecutive starting at [1].",
                 ref_n=got)


# ---------------------------------------------------------------------------
# CITE-TEXT-01/02 — in-text citation format and ordering
# ---------------------------------------------------------------------------

def check_citation_order(pw: object, findings: list[Finding]) -> None:
    """CITE-TEXT-02: in-text citation numbers must be non-decreasing on first use."""
    seen: dict[int, int] = {}  # number → paragraph_index of first use
    max_first_para: int = -1
    max_num: int = 0

    for cit in pw.citations:
        n = cit.number
        if n in seen:
            continue  # back-reference, allowed
        seen[n] = cit.paragraph_index
        # First occurrence should be after the previous first-occurrence paragraph
        # (or at least the number itself should be ascending)
        if n < max_num:
            _add(findings, "CITE-TEXT-02", Severity.ERROR,
                 f"Citation [{n}] appears after [{max_num}]: "
                 "in-text citation numbers must be in ascending order on first use.",
                 ref_n=n,
                 original=f"[{n}]")
        else:
            max_num = n



def run_all(document: object) -> list[Finding]:
    findings: list[Finding] = []
    check_references_section(document, findings)
    check_reference_numbering(document, findings)
    check_citation_order(document, findings)
    return findings
