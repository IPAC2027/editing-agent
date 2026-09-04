"""Safe, deterministic auto-fixes applied directly to LaTeX source text."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from src.models import Finding, Severity

if TYPE_CHECKING:
    from src.models import Paper

logger = logging.getLogger(__name__)


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
    (e.g. reordering \\bibitem entries to match citation order, and
    reformatting each \\bibitem body via the JACoW-style formatter).

    Each pass mutates the source text so its result is visible in
    ``changes.html`` / ``changes.patch`` as a real line-level diff.

    Returns ``(modified_source, findings)``.
    """
    findings: list[Finding] = []
    source, f = _reorder_bibitems(source, paper)
    findings.extend(f)
    source, f = _apply_arxiv_doi_suggestions(source, paper)
    findings.extend(f)
    source, f = reformat_bibitem_bodies(source, paper)
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


# ===========================================================================
# Bibitem body reformat (Tier-1 integration point)
# ===========================================================================

def _drops_bibitem_information(original: str, formatted: str) -> bool:
    """Conservative guard used by :func:`reformat_bibitem_bodies`.

    Returns ``True`` when *formatted* is missing one of the key JACoW
    information markers carried by *original*.  In that case the
    reformat would silently regress the reference and we keep the
    original block instead.

    Markers tracked: ``in Proc.``, ``presented at``, ``pp.``/``p.``,
    ``vol.``/``no.``, 3-letter month abbreviations, and any 10.xxxx/...
    DOI token.  A single missing marker is enough to bail out.
    """
    markers = [
        r"\bin\s+Proc\.\b",
        r"\bpresented\s+at\b",
        r"\bpp?\.\s*\d",
        r"\bvol\.\s*\w",
        r"\bno\.\s*\w",
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s",
    ]
    for pat in markers:
        if re.search(pat, original, re.IGNORECASE) and not re.search(
            pat, formatted, re.IGNORECASE,
        ):
            return True
    doi_re = re.compile(r"\b10\.\d{4,9}/\S+", re.IGNORECASE)
    if doi_re.search(original) and not doi_re.search(formatted):
        return True
    return False


# ===========================================================================

def _reference_to_formatter_rec(ref) -> dict | None:
    """Map a :class:`~src.models.Reference` to a ``rec`` dict the formatter can consume.

    Returns ``None`` if the reference lacks the minimum required fields
    (authors + title + year) — the formatter has nothing to work with in
    that case and the caller should leave the bibitem body unchanged.
    """
    # authors_raw is the one field formatters want most; build it from the
    # parsed author list when present.
    authors_raw = ""
    if getattr(ref, "authors", None):
        authors_raw = " and ".join(ref.authors)
    if not authors_raw:
        return None

    title = (getattr(ref, "title", "") or "").strip()
    if not title:
        return None

    # date may be "May 2023" or just "2023"
    date = getattr(ref, "date", "") or ""
    year = ""
    month = ""
    dm = re.match(r"^(\S+)\s+(\d{4})$", date)
    if dm:
        month, year = dm.group(1), dm.group(2)
    else:
        ym = re.search(r"\d{4}", date)
        if ym:
            year = ym.group(0)
    if not year:
        return None

    rec: dict = {
        "authors_raw": authors_raw,
        "title": title,
        "year": year,
    }
    if month:
        rec["month"] = month

    if getattr(ref, "ref_type", None):
        rec["ref_type"] = ref.ref_type

    # container_title carries the journal/proceedings/book title depending on
    # the entry type — route it to the right formatter key.
    container = getattr(ref, "container_title", None)
    rt = (ref.ref_type or "").lower()
    if container:
        if rt in ("journal", "journal_accepted", "journal_submitted"):
            rec["journal"] = container
        elif rt in ("book", "book_chapter"):
            rec["booktitle"] = container
        elif rt in (
            "proceedings",
            "proceedings_published",
            "proceedings_unpublished",
            "conference_published",
            "conference_unpublished",
            "conference_current",
        ):
            rec["conference"] = container

    # venue_location is a single "City, Country" string
    venue = getattr(ref, "venue_location", None)
    if venue:
        parts = [p.strip() for p in venue.split(",", 1)]
        if parts:
            rec["city"] = parts[0]
        if len(parts) > 1:
            rec["country"] = parts[1]

    for k in ("doi", "url", "volume", "issue", "pages"):
        v = getattr(ref, k, None)
        if v:
            rec[k] = v

    # arXiv special-case: convert id → canonical DOI
    if rt == "arxiv" and not rec.get("doi"):
        arxiv_id = (ref.raw_text or "")
        m = re.search(r"arXiv:\s*([\w.\-]+/?\d+|\d{4}\.\d{4,5})", arxiv_id, re.IGNORECASE)
        if m:
            rec["arxiv_id"] = m.group(1)

    return rec


def reformat_bibitem_bodies(source: str, paper: "Paper") -> tuple[str, list[Finding]]:
    """Replace each ``\\bibitem{key}`` body with a JACoW-formatted rewrite.

    This is the integration point where the migrated Tier-1 modules
    (:func:`src.refs.format_ref`, :class:`src.refs.JacoWConnector`,
    :func:`src.refs.normalize_journal`) actually mutate the LaTeX source so
    their work appears in ``changes.html`` / ``changes.patch`` as a real
    line-level diff.

    Constraints:

    - Only runs in ``thebibliography`` mode.  In biblatex mode the bodies
      live in a separate ``.bib`` file which the existing pipeline does not
      rewrite on disk; the formatter is still useful for the in-memory
      record but would not be visible in the .tex diff.
    - Skips any ``\\bibitem`` whose key has no matching Reference in
      ``paper.references`` (so uncited entries from shared .bib files are
      left alone).
    - Skips References lacking authors / title / year — the formatter has
      nothing to produce.  The line-level fixes in :func:`apply_safe_fixes`
      still run on the body regardless, so the diff still shows DOI / arXiv
      normalisation, bracket cleanup, etc.
    """
    from src.refs import JacoWConnector, format_ref, normalize_journal

    findings: list[Finding] = []
    pt = paper.__dict__.get("_pt")
    if not pt or pt.bibliography_env != "thebibliography":
        return source, findings

    ref_by_key = {r.key: r for r in paper.references if getattr(r, "key", None)}
    if not ref_by_key:
        return source, findings

    bib_match = re.search(
        r"(\\begin\{thebibliography\}.*?\\end\{thebibliography\})",
        source,
        re.DOTALL,
    )
    if not bib_match:
        return source, findings

    bib_block = bib_match.group(1)
    bibitem_pat = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
    positions = list(bibitem_pat.finditer(bib_block))
    if not positions:
        return source, findings

    end_tag_pos = bib_block.rfind(r"\end{thebibliography}")
    if end_tag_pos == -1:
        return source, findings

    prefix = bib_block[: positions[0].start()]
    suffix = bib_block[end_tag_pos:]

    # Single connector instance; offline by default — the hardcoded table
    # covers the most common JACoW events, and turning network on here
    # would add a network call to every prescreen run.
    connector = JacoWConnector(allow_network=False)

    new_items: list[str] = []
    n_reformatted = 0

    for idx, m in enumerate(positions):
        key = m.group(1).strip()
        block_start = m.start()
        block_end = (
            positions[idx + 1].start()
            if idx + 1 < len(positions)
            else end_tag_pos
        )
        original_block = bib_block[block_start:block_end]

        ref = ref_by_key.get(key)
        if ref is None:
            new_items.append(original_block)
            continue

        rec = _reference_to_formatter_rec(ref)
        if not rec:
            new_items.append(original_block)
            continue

        # Tier-1: fill missing conference metadata from the JACoW DB.
        if rec.get("conference") and rec.get("year"):
            log: list = []
            rec = connector.complete_record(rec, log)

        # Tier-1: apply the JACoW journal-abbreviation cascade.
        if rec.get("journal"):
            normalised = normalize_journal(rec["journal"])
            if normalised and normalised != rec["journal"]:
                rec["journal"] = normalised

        # Tier-1: produce the canonical JACoW citation.
        try:
            new_text = format_ref(rec, rec.get("ref_type", "journal"))
        except Exception as exc:
            logger.warning("format_ref failed for bibitem %s: %s", key, exc)
            new_items.append(original_block)
            continue

        new_text_clean = (new_text or "").strip()
        original_clean = original_block.strip()
        if not new_text_clean or new_text_clean == original_clean:
            new_items.append(original_block)
            continue

        # Conservative guard: skip the reformat if it would silently drop
        # information present in the original body — e.g. "in Proc. ..."
        # line, "pp. N-M" pages, "Oct." month.  This is the same
        # information-preservation check used by the Word pipeline.
        if _drops_bibitem_information(original_clean, new_text_clean):
            new_items.append(original_block)
            continue

        # Splice the formatted text into the bibitem slot.  Preserve the
        # \bibitem{key} line verbatim, then indent the body to match the
        # convention used by the existing _reorder_bibitems rewrite.
        new_block = f"\\bibitem{{{key}}}\n  {new_text_clean}\n"

        findings.append(Finding(
            check_id="FMT-REF-01",
            severity=Severity.INFO,
            line=None,
            original=original_clean[:240],
            suggested=new_text_clean[:240],
            message=(
                f"Reformatted \\bibitem{{{key}}} per JACoW style "
                f"(via src.refs: format_ref + JacoWConnector + normalize_journal)."
            ),
            auto_fixed=True,
        ))
        n_reformatted += 1
        new_items.append(new_block)

    if n_reformatted == 0:
        return source, findings

    new_bib_block = prefix + "".join(new_items) + suffix
    new_source = (
        source[: bib_match.start(1)]
        + new_bib_block
        + source[bib_match.end(1) :]
    )
    return new_source, findings
