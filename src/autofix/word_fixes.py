"""Safe, deterministic auto-fixes for Word reference text strings.

Operates on the *raw_text* of each :class:`~src.parser.word_parser.WordReference`
and returns a corrected string together with a list of :class:`~src.models.Finding`
items (``auto_fixed=True``) describing every change made.
"""

from __future__ import annotations

import re

from src.models import Finding, Severity


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def fix_reference(ref_n: int, raw: str, *, suggested_doi: str | None = None) -> tuple[str, list[Finding]]:
    """Apply all safe fixes to *raw* (reference body text, no leading [n]).

    Returns ``(fixed_text, findings)`` where every finding has ``auto_fixed=True``.
    """
    findings: list[Finding] = []
    text = raw

    text, f = _fix_doi_prefix(ref_n, text)
    findings.extend(f)

    text, f = _fix_doi_url(ref_n, text)
    findings.extend(f)

    text, f = _fix_doi_space(ref_n, text)
    findings.extend(f)

    text, f = _fix_oxford_comma(ref_n, text)
    findings.extend(f)

    text, f = _fix_etal(ref_n, text)
    findings.extend(f)

    text, f = _append_missing_doi(ref_n, text, suggested_doi)
    findings.extend(f)

    return text, findings


# ---------------------------------------------------------------------------
# Individual fix functions
# ---------------------------------------------------------------------------

def _fix_doi_prefix(ref_n: int, text: str) -> tuple[str, list[Finding]]:
    """Normalise DOI prefix to lowercase 'doi:' with no space."""
    pat = re.compile(r'\b(DOI|Doi)\s*:\s*(10\.\S+)')

    findings: list[Finding] = []
    def _repl(m: re.Match) -> str:
        return f"doi:{m.group(2)}"

    new_text, n = pat.subn(_repl, text)
    if n:
        m = pat.search(text)
        findings.append(Finding(
            check_id="DOI-FMT-01",
            severity=Severity.INFO,
            line=ref_n,
            original=m.group(0) if m else None,
            suggested=pat.sub(_repl, text),
            message=f"Reference [{ref_n}]: normalised DOI prefix to lowercase 'doi:'.",
            auto_fixed=True,
        ))
    return new_text, findings


def _fix_doi_url(ref_n: int, text: str) -> tuple[str, list[Finding]]:
    """Replace 'https://doi.org/10.xxx' with 'doi:10.xxx'."""
    pat = re.compile(r'https?://(?:dx\.)?doi\.org/(10\.[^\s,;)]+)', re.IGNORECASE)

    findings: list[Finding] = []
    def _repl(m: re.Match) -> str:
        return f"doi:{m.group(1)}"

    new_text, n = pat.subn(_repl, text)
    if n:
        m = pat.search(text)
        findings.append(Finding(
            check_id="DOI-FMT-01",
            severity=Severity.INFO,
            line=ref_n,
            original=m.group(0) if m else None,
            suggested=f"doi:{m.group(1)}" if m else None,
            message=f"Reference [{ref_n}]: replaced doi.org URL with 'doi:10.xxx' format.",
            auto_fixed=True,
        ))
    return new_text, findings


def _fix_doi_space(ref_n: int, text: str) -> tuple[str, list[Finding]]:
    """Remove space between 'doi:' and the DOI number: 'doi: 10.x' → 'doi:10.x'."""
    pat = re.compile(r'\bdoi:\s+(10\.\S+)', re.IGNORECASE)

    findings: list[Finding] = []
    def _repl(m: re.Match) -> str:
        return f"doi:{m.group(1)}"

    new_text, n = pat.subn(_repl, text)
    if n:
        m = pat.search(text)
        findings.append(Finding(
            check_id="DOI-FMT-01",
            severity=Severity.INFO,
            line=ref_n,
            original=m.group(0) if m else None,
            suggested=f"doi:{m.group(1)}" if m else None,
            message=f"Reference [{ref_n}]: removed space inside DOI (doi: 10.x → doi:10.x).",
            auto_fixed=True,
        ))
    return new_text, findings


def _fix_oxford_comma(ref_n: int, text: str) -> tuple[str, list[Finding]]:
    """Add Oxford comma before 'and' in author list of >=3 authors.

    Only operates on the author section (before the first quoted title).

    The Oxford comma is only valid for 3+ authors.  For 1 or 2 authors
    JACoW style is ``"A"`` and ``"A and B"`` respectively -- the comma
    before ``and`` would be wrong.  We detect the author count by counting
    comma-separated name boundaries before the separator ``and`` (the
    number of authors = commas + 1).
    """
    # Find title boundary
    title_m = re.search(r'["\u201c]', text)
    if title_m is None:
        return text, []

    author_part = text[: title_m.start()]
    rest = text[title_m.start():]

    # Find the separator 'and' before the last author.  We only need to
    # fix the *last* comma (the Oxford one) -- a 4-author list with no
    # Oxford comma looks like "A, B, C and D" and should become
    # "A, B, C, and D", not "A,, B,, C, and D".
    and_matches = list(re.finditer(r'\band\b', author_part, re.IGNORECASE))
    if not and_matches:
        return text, []  # 1 author
    last_and = and_matches[-1]
    front = author_part[: last_and.start()].rstrip()
    tail  = author_part[last_and.end():].lstrip()

    # Split front on ", " -- the pieces are the names before the last
    # author.  Empty strings come from the Oxford-comma case ("A, B, "
    # -> ["A", "B", ""]); filter them.  The number of authors is
    # (front_names count) + 1, for the tail which is the last author.
    front_names = [s for s in re.split(r',\s+', front) if s]
    n_authors = len(front_names) + 1

    if n_authors < 3:
        return text, []  # 2 authors -- Oxford comma would be wrong

    # If a comma already precedes 'and', the Oxford comma is already there.
    if front.endswith(','):
        return text, []

    new_author = front + ', and ' + tail
    new_text = new_author + rest

    findings = [Finding(
        check_id="AUTH-01",
        severity=Severity.INFO,
        line=ref_n,
        original=author_part.strip(),
        suggested=new_author.strip(),
        message=(
            f"Reference [{ref_n}]: added Oxford comma before 'and' in "
            f"author list ({n_authors} authors)."
        ),
        auto_fixed=True,
    )]
    return new_text, findings

def _fix_etal(ref_n: int, text: str) -> tuple[str, list[Finding]]:
    """Normalise 'et al' variants to 'et al.'"""
    # Variants: et al, et.al., et. al., et al,
    pat = re.compile(r'\bet\.?\s*al\.?\b(?!\.)', re.IGNORECASE)

    findings: list[Finding] = []
    originals = pat.findall(text)
    new_text = pat.sub('et al.', text)
    if new_text != text:
        findings.append(Finding(
            check_id="AUTH-02",
            severity=Severity.INFO,
            line=ref_n,
            original=originals[0] if originals else None,
            suggested="et al.",
            message=f"Reference [{ref_n}]: normalised 'et al.' punctuation.",
            auto_fixed=True,
        ))
    return new_text, findings


def _append_missing_doi(ref_n: int, text: str, suggested_doi: str | None) -> tuple[str, list[Finding]]:
    """Append a DOI found by lookup when the reference text does not already contain one."""
    if not suggested_doi:
        return text, []
    if re.search(r'\bdoi\s*:\s*10\.|https?://(?:dx\.)?doi\.org/10\.', text, re.IGNORECASE):
        return text, []

    doi_value = suggested_doi.removeprefix("doi:").strip()
    fixed_text = text.rstrip()

    # JACoW arXiv DOI rule: replace arXiv URL with the DOI form, do not keep URL.
    if doi_value.lower().startswith("10.48550/arxiv."):
        arxiv_url_pat = re.compile(r'https?://arxiv\.org/(?:abs|pdf)/\S+', re.IGNORECASE)
        fixed_text = arxiv_url_pat.sub('', fixed_text)
        fixed_text = re.sub(r'\s{2,}', ' ', fixed_text).strip().rstrip(',;')

    fixed_text = fixed_text + f" doi:{doi_value}"
    return fixed_text, [Finding(
        check_id="DOI-REQ-01",
        severity=Severity.INFO,
        line=ref_n,
        original=text.rstrip(),
        suggested=fixed_text,
        message=f"Reference [{ref_n}]: appended DOI found automatically.",
        auto_fixed=True,
    )]
