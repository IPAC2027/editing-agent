"""JACoW reference checks for Word (.docx) submissions.

Applies a subset of the Annex B rules to :class:`~src.parser.word_parser.ParsedWord`
objects.  Each check appends :class:`~src.models.Finding` items to the supplied
list.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from src.checks.reference_checks import (
    _doi_matches_reference,
    _lookup_doi_crossref,
    _search_refs_jacow,
    _validate_doi_online,
)
from src.models import Finding, Reference, Severity

if TYPE_CHECKING:
    from src.parser.word_parser import ParsedWord, WordReference


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


_DOI_CANDIDATE_RE = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')
_ARXIV_RAW_RE = re.compile(r'\barXiv:([A-Za-z\-]+/\d+|\d{4}\.\d{4,5})(?:v\d+)?\b', re.IGNORECASE)
_ARXIV_URL_RE = re.compile(
    r'https?://arxiv\.org/(?:abs|pdf)/([\w./-]+?)(?:v\d+)?(?:\.pdf)?$',
    re.IGNORECASE,
)


def _to_reference(ref: "WordReference") -> Reference:
    """Convert a Word reference into the shared Reference model used by DOI lookups."""
    year_m = re.search(r'\b(19|20)\d{2}\b', ref.raw_text)
    return Reference(
        n=ref.n,
        key=f"word-ref-{ref.n}",
        ref_type=ref.ref_type,
        authors=list(ref.authors),
        title=ref.title,
        date=year_m.group(0) if year_m else None,
        doi=ref.doi or None,
        url=ref.url or None,
        raw_text=ref.raw_text,
    )


def _google_query(ref: "WordReference") -> str:
    """Build a concise Google query for DOI discovery."""
    parts: list[str] = []
    if ref.title:
        parts.append(f'"{ref.title}"')
    if ref.authors:
        parts.append(f'"{ref.authors[0]}"')
    year_m = re.search(r'\b(19|20)\d{2}\b', ref.raw_text)
    if year_m:
        parts.append(year_m.group(0))
    parts.append("doi")
    if not ref.title and not ref.authors:
        parts.append(ref.raw_text[:140])
    return " ".join(p for p in parts if p).strip()


def _extract_doi_candidates(text: str) -> list[str]:
    """Extract DOI-looking strings from arbitrary HTML/text content."""
    seen: set[str] = set()
    results: list[str] = []
    for match in _DOI_CANDIDATE_RE.finditer(text):
        doi = match.group(0).rstrip('.,;:)]}\"\'')
        if doi not in seen:
            seen.add(doi)
            results.append(doi)
    return results


def _lookup_doi_google(ref: "WordReference") -> str | None:
    """Use a lightweight Google search result page scrape to find a DOI."""
    query = _google_query(ref)
    if not query:
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = httpx.get(
            "https://www.google.com/search",
            params={"q": query, "hl": "en", "num": 5},
            headers=headers,
            timeout=10.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception:
        return None

    candidates = _extract_doi_candidates(resp.text)
    shared_ref = _to_reference(ref)
    for doi in candidates:
        if _doi_matches_reference(shared_ref, doi):
            return doi
    return None


def _lookup_missing_doi(ref: "WordReference") -> tuple[str | None, str | None]:
    """Search for a missing DOI in the requested order.

    Returns ``(doi, source_name)`` where source_name is one of
    ``google``, ``refs.jacow.org``, or ``crossref``.
    """
    shared_ref = _to_reference(ref)

    # 0) Deterministic arXiv mapping per JACoW guidance, then verify online.
    arxiv_m = _ARXIV_RAW_RE.search(ref.raw_text or "")
    if arxiv_m:
        candidate = f"10.48550/arXiv.{arxiv_m.group(1)}"
        if _validate_doi_online(candidate):
            return candidate, "arxiv-formula"

    if ref.url:
        u_m = _ARXIV_URL_RE.match(ref.url.strip().rstrip('.,;)]}'))
        if u_m:
            candidate = f"10.48550/arXiv.{u_m.group(1).rstrip('/')}"
            if _validate_doi_online(candidate):
                return candidate, "arxiv-formula"

    doi = _lookup_doi_google(ref)
    if doi:
        return doi, "google"

    doi = _search_refs_jacow(shared_ref)
    if doi:
        return doi, "refs.jacow.org"

    doi = _lookup_doi_crossref(shared_ref)
    if doi:
        return doi, "crossref"

    return None, None


# ---------------------------------------------------------------------------
# REF-SEC-01 — REFERENCES section heading
# ---------------------------------------------------------------------------

def check_references_section(pw: "ParsedWord", findings: list[Finding]) -> None:
    """REF-SEC-01: document must contain a section titled 'REFERENCES'."""
    if not pw.has_references_section:
        _add(findings, "REF-SEC-01", Severity.ERROR,
             "No 'REFERENCES' section heading found in the document.")


# ---------------------------------------------------------------------------
# REF-NUM-01/02 — reference numbering
# ---------------------------------------------------------------------------

def check_reference_numbering(pw: "ParsedWord", findings: list[Finding]) -> None:
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

def check_citation_order(pw: "ParsedWord", findings: list[Finding]) -> None:
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


# ---------------------------------------------------------------------------
# AUTH-01 — penultimate comma for ≥3 authors
# ---------------------------------------------------------------------------

# Detect author strings where the last "and" lacks a preceding comma:
# "A, B and C" should be "A, B, and C"
_MISSING_OXFORD_COMMA_RE = re.compile(
    r'([^,])\s+and\s+([A-Z\-])',   # not preceded by comma
)

def check_author_format(pw: "ParsedWord", findings: list[Finding]) -> None:
    """AUTH-01/02: penultimate comma for ≥3 authors; et al. for >6 authors."""
    for ref in pw.references:
        raw = ref.raw_text
        # Determine author section: text before first quoted title or first period
        title_m = re.search(r'["\u201c]', raw)
        author_part = raw[: title_m.start()].strip().rstrip(",") if title_m else ""

        if not author_part:
            continue

        n_authors = _count_authors(author_part)

        # AUTH-01: ≥3 authors need Oxford comma before "and"
        if n_authors >= 3 and not re.search(r',\s+and\s+', author_part):
            if _MISSING_OXFORD_COMMA_RE.search(author_part):
                # Suggest fix
                fixed = _MISSING_OXFORD_COMMA_RE.sub(r'\1, and \2', author_part)
                _add(findings, "AUTH-01", Severity.WARNING,
                     f"Reference [{ref.n}]: ≥3 authors require a comma before 'and' "
                     f"(Oxford comma). e.g. 'A, B, and C,'",
                     ref_n=ref.n,
                     original=author_part,
                     suggested=fixed)

        # AUTH-02: >6 authors should use et al.
        if n_authors > 6 and "et al" not in author_part.lower():
            _add(findings, "AUTH-02", Severity.WARNING,
                 f"Reference [{ref.n}]: more than 6 authors — "
                 "use 'et al.' instead of listing all authors.",
                 ref_n=ref.n,
                 original=author_part)


def _count_authors(author_str: str) -> int:
    """Rough count of authors in an author string."""
    if "et al" in author_str.lower():
        return 99  # et al. already — no fix needed
    # Count occurrences of 'and' (each 'and' joins authors) + 1, or count commas
    and_count = len(re.findall(r'\band\b', author_str, re.IGNORECASE))
    if and_count:
        return and_count + 1
    # Fallback: count comma-separated units where each looks like an author
    parts = [p.strip() for p in author_str.split(",") if p.strip()]
    return max(1, len(parts))


# ---------------------------------------------------------------------------
# TITLE-01 — paper title sentence case
# ---------------------------------------------------------------------------

# Common known acronyms/proper-noun patterns that should stay capitalised
_KNOWN_CAPS = re.compile(
    r'^(?:'
    r'[A-Z]{2,}'              # all-caps acronym (LHC, CERN, RF, ...)
    r'|[A-Z][a-z]+(?:[A-Z][a-z]+)+'  # CamelCase
    r')$'
)

def check_title_case(pw: "ParsedWord", findings: list[Finding]) -> None:
    """TITLE-01: paper titles in references should be sentence case."""
    for ref in pw.references:
        if not ref.title:
            continue
        words = ref.title.split()
        if len(words) < 3:
            continue  # too short to judge
        # Count capitalised words beyond the first
        cap_later = [
            w for w in words[1:]
            if w and w[0].isupper()
            and not _KNOWN_CAPS.match(w.rstrip(",.;:"))
            and not w.rstrip(",.;:").endswith(".")
        ]
        # If more than half the non-first words are capitalised, flag it
        if len(cap_later) >= max(2, len(words) // 2):
            sentence = words[0] + " " + " ".join(w.lower() if (
                w[0].isupper() and not _KNOWN_CAPS.match(w.rstrip(",.;:"))
            ) else w for w in words[1:])
            _add(findings, "TITLE-01", Severity.WARNING,
                 f"Reference [{ref.n}]: title appears to be in Title Case; "
                 "JACoW requires sentence case (only first word and proper nouns capitalised).",
                 ref_n=ref.n,
                 original=ref.title,
                 suggested=sentence)


# ---------------------------------------------------------------------------
# DOI-FMT-01 — DOI format in raw text
# ---------------------------------------------------------------------------

_DOI_BAD_PREFIX_RE = re.compile(
    r'(?:'
    r'(?:https?://(?:dx\.)?doi\.org/)'  # URL form
    r'|(?:\b(?:DOI|Doi)\s*:?\s*)'       # wrong case
    r'|(?:doi\s+)'                       # doi with space instead of colon
    r')'
    r'(10\.\S+)',
    re.IGNORECASE,
)
_DOI_SPACE_RE = re.compile(r'\bdoi\s*:\s+(10\.\S+)', re.IGNORECASE)
_DOI_CORRECT_RE = re.compile(r'\bdoi:(10\.\S+)', re.IGNORECASE)


def check_doi_format(pw: "ParsedWord", findings: list[Finding]) -> None:
    """DOI-FMT-01: DOI must use 'doi:10.xxx' format with no space after colon."""
    for ref in pw.references:
        raw = ref.raw_text

        # Check for doi with space
        m = _DOI_SPACE_RE.search(raw)
        if m:
            correct = f"doi:{m.group(1)}"
            _add(findings, "DOI-FMT-01", Severity.WARNING,
                 f"Reference [{ref.n}]: DOI has space after colon — should be 'doi:{m.group(1)}'.",
                 ref_n=ref.n,
                 original=m.group(0),
                 suggested=correct)
            continue

        # Check for URL-form DOI (https://doi.org/...)
        m2 = re.search(r'https?://(?:dx\.)?doi\.org/(10\.\S+)', raw, re.IGNORECASE)
        if m2:
            correct = f"doi:{m2.group(1).rstrip('.,)')}"
            _add(findings, "DOI-FMT-01", Severity.WARNING,
                 f"Reference [{ref.n}]: DOI expressed as URL — "
                 f"replace '{m2.group(0).rstrip('.,)')}' with '{correct}'.",
                 ref_n=ref.n,
                 original=m2.group(0),
                 suggested=correct)
            continue

        # Check for wrong-case DOI prefix (DOI: or Doi:)
        m3 = re.search(r'\b(DOI|Doi)\s*:\s*(10\.\S+)', raw)
        if m3:
            correct = f"doi:{m3.group(2)}"
            _add(findings, "DOI-FMT-01", Severity.WARNING,
                 f"Reference [{ref.n}]: DOI prefix should be lowercase 'doi:'.",
                 ref_n=ref.n,
                 original=m3.group(0),
                 suggested=correct)


# ---------------------------------------------------------------------------
# PROC-REQ-01/02/03 — proceedings references
# ---------------------------------------------------------------------------

def check_proceedings_fields(pw: "ParsedWord", findings: list[Finding]) -> None:
    """PROC-REQ-01/02/03: proceedings refs must have 'in Proc.', location, and pages."""
    for ref in pw.references:
        if ref.ref_type != "proceedings":
            continue
        raw = ref.raw_text

        # PROC-REQ-01: must contain 'in Proc.' or 'Proc.'
        if not re.search(r'\bProc\.', raw):
            _add(findings, "PROC-REQ-01", Severity.WARNING,
                 f"Reference [{ref.n}]: proceedings reference should contain 'in Proc. CONF\\'YY'.",
                 ref_n=ref.n,
                 original=raw[:80])

        # PROC-REQ-02: should include location (city, country) and month/year
        has_year = bool(re.search(r'\b(19|20)\d{2}\b', raw))
        if not has_year:
            _add(findings, "PROC-REQ-02", Severity.WARNING,
                 f"Reference [{ref.n}]: proceedings reference should include year.",
                 ref_n=ref.n,
                 original=raw[:80])

        # PROC-REQ-03: should include page numbers (pp. N-M or p. N)
        has_pages = bool(re.search(r'\bpp?\.\s*\d', raw))
        if not has_pages and not ref.doi:
            _add(findings, "PROC-REQ-03", Severity.WARNING,
                 f"Reference [{ref.n}]: proceedings reference should include page numbers (pp. N-M) "
                 "or a DOI.",
                 ref_n=ref.n,
                 original=raw[:80])


# ---------------------------------------------------------------------------
# DOI-REQ-01 — DOI missing for paper-type references
# ---------------------------------------------------------------------------

_PAPER_TYPES = {"proceedings", "journal", "arxiv"}

def check_missing_doi(pw: "ParsedWord", findings: list[Finding]) -> None:
    """DOI-REQ-01: paper-type references (proceedings, journal, arXiv) should have a DOI."""
    cache: dict[str, tuple[str | None, str | None]] = {}

    for ref in pw.references:
        if ref.ref_type not in _PAPER_TYPES:
            continue
        if ref.doi:
            continue
        cache_key = _google_query(ref) or ref.raw_text[:160]
        if cache_key in cache:
            found, source = cache[cache_key]
        else:
            found, source = _lookup_missing_doi(ref)
            cache[cache_key] = (found, source)

        if found and source:
            source_msg = (
                "JACoW arXiv DOI rule suggests"
                if source == "arxiv-formula"
                else f"{source} suggests"
            )
            _add(findings, "DOI-REQ-01", Severity.WARNING,
                 f"Reference [{ref.n}]: {ref.ref_type} reference has no DOI in the document. "
                 f"{source_msg} doi:{found}.",
                 ref_n=ref.n,
                 original=ref.raw_text[:160],
                 suggested=f"doi:{found}")
            continue

        _add(findings, "DOI-REQ-01", Severity.WARNING,
             f"Reference [{ref.n}]: {ref.ref_type} reference has no DOI. "
             "Google, refs.jacow.org, and Crossref could not determine it automatically.",
             ref_n=ref.n,
             original=ref.raw_text[:160])


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_all(pw: "ParsedWord") -> list[Finding]:
    """Run all Word reference checks and return a list of :class:`Finding` items."""
    findings: list[Finding] = []
    check_references_section(pw, findings)
    check_reference_numbering(pw, findings)
    check_citation_order(pw, findings)
    check_author_format(pw, findings)
    check_title_case(pw, findings)
    check_doi_format(pw, findings)
    check_proceedings_fields(pw, findings)
    check_missing_doi(pw, findings)
    return findings
