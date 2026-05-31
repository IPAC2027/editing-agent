"""Safe, deterministic auto-fixes applied directly to LaTeX source text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.models import Finding, Severity

if TYPE_CHECKING:
    from src.models import Paper


def apply_safe_fixes(source: str) -> tuple[str, list[Finding]]:
    """Apply all safe fixes to *source*.

    Returns ``(modified_source, findings)`` where every finding has
    ``auto_fixed=True``.  Each fix is applied line-by-line so that
    line numbers reported in findings are accurate.
    """
    lines = source.splitlines(keepends=True)
    findings: list[Finding] = []

    new_lines: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        original_line = line
        line, lf = _fix_doi_prefix(line, lineno, findings)
        line, lf = _fix_url_doi(line, lineno, findings)
        line, lf = _fix_arxiv_to_doi(line, lineno, findings)
        line, lf = _fix_adjacent_cite_brackets(line, lineno, findings)
        line, lf = _fix_cite_spaces(line, lineno, findings)
        line, lf = _fix_cite_comma_spaces(line, lineno, findings)
        line, lf = _fix_etal(line, lineno, findings)
        new_lines.append(line)

    return ''.join(new_lines), findings


# ---------------------------------------------------------------------------
# Individual fix functions
# Each returns (new_line, was_changed).
# They append a Finding when they make a change.
# ---------------------------------------------------------------------------

def _fix_url_doi(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    r"""Replace any \url{<doi-link>} with \doi{10.xxx}.

    Handles all common forms:
    - \url{https://doi.org/10.xxx}
    - \url{http://dx.doi.org/10.xxx}
    - \url{doi:10.xxx}  /  \url{DOI:10.xxx}
    """
    pat = re.compile(
        r'\\url\{'
        r'(?:https?://(?:dx\.)?doi\.org/|[Dd][Oo][Ii]:\s*)'
        r'(10\.[^}]+)\}'
    )

    def _repl(m: re.Match) -> str:
        return f"\\doi{{{m.group(1).strip()}}}"

    new_line, n = pat.subn(_repl, line)
    if n:
        findings.append(Finding(
            check_id="DOI-FMT-02",
            severity=Severity.INFO,
            line=lineno,
            original=pat.search(line).group(0),  # type: ignore[union-attr]
            suggested=pat.sub(_repl, line).rstrip('\n'),
            message=r"Replaced \url{<doi>} with \doi{10.…}.",
            auto_fixed=True,
        ))
    return new_line, bool(n)

def _fix_doi_prefix(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    """Normalise DOI prefix to lowercase 'doi:' with no space."""
    # Match: DOI 10.xxx  /  doi 10.xxx  /  DOI:10.xxx  /  doi: 10.xxx  etc.
    pat = re.compile(r'\b(DOI|Doi|doi)\s*:?\s*(10\.\S+)', re.IGNORECASE)

    def _repl(m: re.Match) -> str:
        return f"doi:{m.group(2)}"

    new_line, n = pat.subn(_repl, line)
    if n:
        findings.append(Finding(
            check_id="DOI-FMT-01",
            severity=Severity.INFO,
            line=lineno,
            original=pat.search(line).group(0),  # type: ignore[union-attr]
            suggested=pat.sub(_repl, line).rstrip('\n'),
            message="Normalised DOI prefix to 'doi:'.",
            auto_fixed=True,
        ))
    return new_line, bool(n)


def _fix_adjacent_cite_brackets(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    """Merge [a][b] → [a, b] (handles two adjacent brackets; run iteratively)."""
    pat = re.compile(r'\[(\d[\d,\s–\-]*)\]\s*\[(\d[\d,\s–\-]*)\]')
    changed = False
    while True:
        m = pat.search(line)
        if not m:
            break
        merged = f"[{m.group(1)}, {m.group(2)}]"
        original = m.group(0)
        line = line[:m.start()] + merged + line[m.end():]
        findings.append(Finding(
            check_id="CITE-BRACKET-01",
            severity=Severity.INFO,
            line=lineno,
            original=original,
            suggested=merged,
            message="Merged adjacent citation brackets.",
            auto_fixed=True,
        ))
        changed = True
    return line, changed


def _fix_cite_spaces(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    """Remove extra spaces inside citation brackets: [ 3 ] → [3]."""
    pat = re.compile(r'\[\s+(\d[\d,\s–\-]*\d|\d)\s+\]')

    def _repl(m: re.Match) -> str:
        return f"[{m.group(1)}]"

    new_line, n = pat.subn(_repl, line)
    if n:
        original = pat.search(line).group(0)  # type: ignore[union-attr]
        findings.append(Finding(
            check_id="CITE-SPACE-01",
            severity=Severity.INFO,
            line=lineno,
            original=original,
            suggested=_repl(pat.search(line)),  # type: ignore[arg-type]
            message="Removed extra spaces inside citation bracket.",
            auto_fixed=True,
        ))
    return new_line, bool(n)


def _fix_cite_comma_spaces(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    """Normalise spacing inside multi-cite brackets: [3,4] → [3, 4]."""
    # Only inside \cite{} we already handle — here fix rendered [3,4] patterns
    pat = re.compile(r'\[(\d+),(\d)')

    def _repl(m: re.Match) -> str:
        return f"[{m.group(1)}, {m.group(2)}"

    new_line, n = pat.subn(_repl, line)
    if n:
        findings.append(Finding(
            check_id="CITE-SPACE-01",
            severity=Severity.INFO,
            line=lineno,
            message="Added space after comma in citation bracket.",
            auto_fixed=True,
        ))
    return new_line, bool(n)


def _fix_etal(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    """Normalise et al. variants: 'et. al.' / 'Et al.' / 'et al,' → 'et al.'"""
    # Various broken forms
    pat = re.compile(r'\bet\.?\s+al\.?(?!\w)', re.IGNORECASE)

    def _repl(m: re.Match) -> str:
        return "et al."

    new_line, n = pat.subn(_repl, line)
    if n and new_line != line:
        findings.append(Finding(
            check_id="AUTH-02",
            severity=Severity.INFO,
            line=lineno,
            original=pat.search(line).group(0),  # type: ignore[union-attr]
            suggested="et al.",
            message="Normalised 'et al.' punctuation.",
            auto_fixed=True,
        ))
    return new_line, bool(n) and new_line != line


def _fix_arxiv_to_doi(line: str, lineno: int, findings: list[Finding]) -> tuple[str, bool]:
    r"""Convert arXiv notation/URLs to JACoW DOI format for references."""
    from src.checks.reference_checks import _validate_doi_online

    changed = False

    raw_pat = re.compile(
        r'\barXiv:([A-Za-z\-]+/\d+|\d{4}\.\d{4,5})(?:v\d+)?\b',
        re.IGNORECASE,
    )

    def _raw_repl(m: re.Match) -> str:
        nonlocal changed
        doi_val = f"10.48550/arXiv.{m.group(1)}"
        if _validate_doi_online(doi_val):
            changed = True
            return f"doi:{doi_val}"
        return m.group(0)

    new_line = raw_pat.sub(_raw_repl, line)

    url_pat = re.compile(
        r'https?://arxiv\.org/(?:abs|pdf)/([\w./-]+?)(?:v\d+)?(?:\.pdf)?(?=[\s,.;)\]}]|$)',
        re.IGNORECASE,
    )

    def _url_repl(m: re.Match) -> str:
        nonlocal changed
        doi_val = f"10.48550/arXiv.{m.group(1).rstrip('/')}"
        if _validate_doi_online(doi_val):
            changed = True
            return f"doi:{doi_val}"
        return m.group(0)

    new_line = url_pat.sub(_url_repl, new_line)

    # If a \\url{...} now wraps a DOI value, normalise to \\doi{...}
    new_line = re.sub(
        r'\\url\{doi:\s*(10\.[^}]+)\}',
        lambda m: f"\\doi{{{m.group(1).strip()}}}",
        new_line,
    )

    if changed:
        findings.append(Finding(
            check_id="URL-AS-DOI-01",
            severity=Severity.INFO,
            line=lineno,
            original=line.rstrip('\n'),
            suggested=new_line.rstrip('\n'),
            message="Converted arXiv notation/URL to JACoW DOI format.",
            auto_fixed=True,
        ))
    return new_line, changed


# ===========================================================================
# Paper-aware fixes (require the parsed Paper model)
# ===========================================================================

def apply_paper_fixes(source: str, paper: "Paper") -> tuple[str, list[Finding]]:
    """Apply fixes that require access to the parsed *paper* model
    (e.g. reordering \\bibitem entries to match citation order).

    Returns ``(modified_source, findings)``.
    """
    findings: list[Finding] = []
    source, f = _reorder_bibitems(source, paper)
    findings.extend(f)
    source, f = _apply_arxiv_doi_suggestions(source, paper)
    findings.extend(f)
    return source, findings


def _reorder_bibitems(source: str, paper: "Paper") -> tuple[str, list[Finding]]:
    """Reorder \\bibitem entries inside \\thebibliography to match
    citation order in the text (fixes REF-NUM-02)."""
    findings: list[Finding] = []

    pt = paper.__dict__.get("_pt")
    if not pt or pt.bibliography_env != "thebibliography":
        return source, findings

    # Locate the \thebibliography block in the source
    bib_match = re.search(
        r'(\\begin\{thebibliography\}.*?\\end\{thebibliography\})',
        source, re.DOTALL,
    )
    if not bib_match:
        return source, findings

    bib_block = bib_match.group(1)

    # Find all \bibitem positions inside the block
    item_pat = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}')
    matches = list(item_pat.finditer(bib_block))
    if not matches:
        return source, findings

    # Find where \end{thebibliography} begins (= end of last item's content)
    end_tag_pos = bib_block.rfind(r'\end{thebibliography}')
    if end_tag_pos == -1:
        return source, findings

    # Text before the first \bibitem (the \begin{...} line + any blank lines)
    prefix = bib_block[: matches[0].start()]
    # Text from \end{thebibliography} onwards
    suffix = bib_block[end_tag_pos:]

    # Slice out each bibitem's raw block (from its \bibitem{} to the next one,
    # or to the \end tag for the last entry)
    bibitem_blocks: dict[str, str] = {}
    current_order: list[str] = []
    for idx, m in enumerate(matches):
        key = m.group(1).strip()
        current_order.append(key)
        block_start = m.start()
        block_end = matches[idx + 1].start() if idx + 1 < len(matches) else end_tag_pos
        bibitem_blocks[key] = bib_block[block_start:block_end]

    # Build desired order: citation_order filtered to keys in this bib list,
    # then any remaining keys (cited nowhere) appended at the end.
    known = set(current_order)
    cite_first = list(dict.fromkeys(
        k for k in paper.citation_order if k in known
    ))
    leftover = [k for k in current_order if k not in set(cite_first)]
    desired_order = cite_first + leftover

    if desired_order == current_order:
        return source, findings  # already correct

    new_bib_block = (
        prefix
        + "".join(bibitem_blocks[k] for k in desired_order if k in bibitem_blocks)
        + suffix
    )

    new_source = source[: bib_match.start(1)] + new_bib_block + source[bib_match.end(1):]

    findings.append(Finding(
        check_id="REF-NUM-02",
        severity=Severity.INFO,
        message=(
            f"Reordered {len(desired_order)} \\bibitem entries to match "
            f"citation order. (Auto-fixed in _edited.tex)"
        ),
        auto_fixed=True,
    ))
    return new_source, findings


def _apply_arxiv_doi_suggestions(source: str, paper: "Paper") -> tuple[str, list[Finding]]:
    """Append validated arXiv DOI suggestions into matching \bibitem entries.

    We only apply suggestions already produced by reference checks, so online
    verification and type classification have already happened upstream.
    """
    findings: list[Finding] = []

    suggestions: dict[str, str] = {}
    for f in paper.findings:
        if f.check_id != "URL-AS-DOI-01" or not f.suggested:
            continue
        m_key = re.search(r"Reference \{([^}]+)\}", f.message)
        m_doi = re.search(r"doi:(10\.\S+)", f.suggested, re.IGNORECASE)
        if not (m_key and m_doi):
            continue
        key = m_key.group(1)
        doi = m_doi.group(1).rstrip('.,;)]}')
        suggestions[key] = doi

    if not suggestions:
        return source, findings

    for key, doi in suggestions.items():
        pat = re.compile(
            r'(\\bibitem\s*(?:\[[^\]]*\])?\s*\{' + re.escape(key) + r'\}'
            r'.*?)(?=(?:\n\\bibitem|\\end\{thebibliography\}))',
            re.DOTALL,
        )
        m = pat.search(source)
        if not m:
            continue

        block = m.group(1)
        if re.search(r'\bdoi\s*:\s*10\.|\\doi\{10\.', block, re.IGNORECASE):
            continue

        new_block = block.rstrip() + f" doi:{doi}\n"
        source = source[:m.start(1)] + new_block + source[m.end(1):]

        findings.append(Finding(
            check_id="URL-AS-DOI-01",
            severity=Severity.INFO,
            original=block.strip()[:220],
            suggested=new_block.strip()[:240],
            message=f"Applied arXiv DOI suggestion to \\bibitem{{{key}}}.",
            auto_fixed=True,
        ))

    return source, findings
