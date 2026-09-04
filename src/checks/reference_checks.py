"""Priority-1 reference and citation checks — Phase 1 implementation."""

from __future__ import annotations

import difflib
import os
from enum import Enum
import re
from pathlib import Path

import httpx

from src.lookup_status import STATUS, label
from src.models import Finding, Paper, Reference, Severity
from src.parser.latex_parser import ParsedTex


def _pt(paper: Paper) -> ParsedTex:
    """Retrieve the ParsedTex metadata attached by the parser."""
    return paper.__dict__.get('_pt')  # type: ignore[return-value]


def _add(paper: Paper, check_id: str, sev: Severity, msg: str,
         line: int | None = None, original: str | None = None,
         suggested: str | None = None) -> None:
    paper.findings.append(Finding(
        check_id=check_id,
        severity=sev,
        line=line,
        original=original,
        suggested=suggested,
        message=msg,
    ))


# ---------------------------------------------------------------------------
# CITE-ORDER-01 — citations must appear in ascending first-occurrence order
# ---------------------------------------------------------------------------

def check_citation_order(paper: Paper) -> None:
    """CITE-ORDER-01: first-occurrence citation numbers are non-decreasing."""
    pt = _pt(paper)
    if not pt:
        return
    if pt.uses_biblatex:
        return  # biblatex sorts citations by first-appearance automatically
    if not pt.cite_occurrences:
        return

    # Build key→citation_number from citation_order (order of first appearance)
    key_to_num: dict[str, int] = {k: i + 1 for i, k in enumerate(paper.citation_order)}

    max_seen = 0
    seen_keys: set[str] = set()

    for occ in pt.cite_occurrences:
        k = occ.key
        num = key_to_num.get(k)
        if num is None:
            continue   # missing key — handled by CITE-LINK-01
        if k in seen_keys:
            continue   # back-reference is fine

        seen_keys.add(k)
        if num < max_seen:
            _add(paper, "CITE-ORDER-01", Severity.ERROR,
                 f"Citation [{num}] ({k!r}) appears after [{max_seen}]: "
                 f"in-text citation numbers must be in ascending order on first use.",
                 line=occ.line,
                 original=occ.raw)
        else:
            max_seen = num


# ---------------------------------------------------------------------------
# CITE-LINK-01/02 — every cite resolves; every entry is cited
# ---------------------------------------------------------------------------

def check_citation_links(paper: Paper) -> None:
    r"""CITE-LINK-01: every ``\cite{key}`` must resolve to a reference entry.

    When the cause is a *missing bibliography file*, this reports the cause
    once instead of the symptom many times.  On the sample corpus MOZN01
    declares ``\addbibresource{MOZN01.bib}`` while the submission actually
    contains ``MOZN01_bib.bib``; the previous version emitted 19 separate
    ERRORs, one per citation, which tells the editor 19 times about one typo.
    """
    pt = _pt(paper)
    if not pt:
        return

    ref_keys: set[str] = {r.key for r in paper.references}

    cited_keys: set[str] = set()
    cite_key_to_line: dict[str, int] = {}
    for occ in pt.cite_occurrences:
        if occ.key not in cite_key_to_line:
            cite_key_to_line[occ.key] = occ.line
        cited_keys.add(occ.key)

    if not ref_keys and pt.uses_biblatex:
        return  # ref_keys come from .bib, populated before this check is called

    unresolved = sorted(cited_keys - ref_keys)
    if not unresolved:
        return

    # If a declared .bib file is missing, that single fact explains all of it.
    missing_bib = [
        f.original for f in paper.findings if f.check_id == "BIB-MISSING-01" and f.original
    ]
    if missing_bib and len(unresolved) > 2:
        _add(paper, "CITE-LINK-01", Severity.ERROR,
             f"{len(unresolved)} citations cannot be resolved because a declared "
             f"bibliography file is missing ({', '.join(missing_bib)}). Fix the "
             f"file name and these resolve themselves. Unresolved keys: "
             f"{', '.join(unresolved[:8])}"
             + (f", and {len(unresolved) - 8} more" if len(unresolved) > 8 else ""))
        return

    for key in unresolved:
        _add(paper, "CITE-LINK-01", Severity.ERROR,
             f"\\cite{{{key}}} has no corresponding reference entry.",
             line=cite_key_to_line.get(key),
             original=f"\\cite{{{key}}}")

    # CITE-LINK-02: skipped — .bib files often contain more entries than used
    # in a single paper (shared libraries), so uncited entries are not flagged.


# ---------------------------------------------------------------------------
# REF-SEC-01 — REFERENCES section exists
# ---------------------------------------------------------------------------

def check_reference_section(paper: Paper) -> None:
    """REF-SEC-01: a REFERENCES section (or \\printbibliography) must be present."""
    pt = _pt(paper)
    if not pt:
        return
    if not pt.has_bibliography_section:
        _add(paper, "REF-SEC-01", Severity.ERROR,
             "No bibliography section found. Expected either "
             "\\begin{thebibliography} or \\printbibliography.")


# ---------------------------------------------------------------------------
# REF-NUM-01/02 — numbering of manual \bibitem entries
# ---------------------------------------------------------------------------

def check_reference_numbering(paper: Paper) -> None:
    """REF-NUM-01/02: manual \\bibitem entries must be consecutive from 1."""
    pt = _pt(paper)
    if not pt or pt.bibliography_env != "thebibliography":
        return  # biblatex handles numbering automatically

    keys = [r.key for r in paper.references]
    # Check that the order in the reference list matches citation_order
    # (REF-NUM-01 is structural; for manual bibs we check that items appear
    #  in the same order as they are first cited — CITE-ORDER-01 covers the
    #  in-text side; here we just verify the list is not obviously misordered.)
    if not keys:
        _add(paper, "REF-NUM-01", Severity.WARNING,
             "No \\bibitem entries found inside \\thebibliography.")
        return

    # Build expected order from citation_order (keys in cite order)
    # Only keys that appear in both the cite list and the ref list
    cite_order = [k for k in paper.citation_order if k in {r.key for r in paper.references}]
    ref_order  = [r.key for r in paper.references]

    mismatches = []
    for expected_n, key in enumerate(cite_order, start=1):
        actual_n = ref_order.index(key) + 1 if key in ref_order else None
        if actual_n != expected_n:
            mismatches.append((key, expected_n, actual_n))

    for key, exp, act in mismatches:
        _add(paper, "REF-NUM-02", Severity.ERROR,
             f"Reference {{{key}}} is entry #{act} in the list but "
             f"should be #{exp} based on citation order in the text. "
             f"Renumber the reference list to match citation order.",
             original=f"[{act}] {key}",
             suggested=f"[{exp}] {key}")


# ---------------------------------------------------------------------------
# URL-AS-DOI-01 — URL provided where a DOI should be used
# ---------------------------------------------------------------------------

def check_url_instead_of_doi(paper: Paper) -> None:
    """URL-AS-DOI-01: reference uses a URL/arXiv notation where a DOI should appear.

    Priority order for DOI resolution:
    1. arXiv:XXXX.YYYY raw notation → formula-based, no network
    2. arXiv/doi.org/jacow.org/accelconf URL → formula-based, no network
    3. refs.jacow.org HTML search (for JACoW proceedings with text-only refs)
    4. Crossref bibliographic search (fallback for journal articles)
    """
    jacow_cache: dict[str, str | None] = {}
    crossref_cache: dict[str, str | None] = {}

    for ref in paper.references:
        if ref.doi:
            continue  # already has DOI — DOI-FMT checks handle any formatting issues

        # ── 1. arXiv:XXXX.YYYY notation in raw text ──────────────────────────
        arxiv_m = _ARXIV_RAW_RE.search(ref.raw_text or "")
        if arxiv_m:
            arxiv_id = arxiv_m.group(1)
            suggested = f"10.48550/arXiv.{arxiv_id}"
            arxiv_verdict = verify_doi(suggested)
            if arxiv_verdict is DoiVerdict.UNVERIFIED:
                _add(
                    paper,
                    "URL-AS-DOI-01",
                    Severity.INFO,
                    f"Reference {{{ref.key}}}: NOT CHECKED — arXiv notation found, but "
                    f"doi:{suggested} could not be verified because no DOI authority "
                    "was reachable on this run.",
                    original=arxiv_m.group(0),
                )
                continue
            if arxiv_verdict is DoiVerdict.VERIFIED:
                _add(
                    paper,
                    "URL-AS-DOI-01",
                    Severity.WARNING,
                    f"Reference {{{ref.key}}}: arXiv preprint should use "
                    f"doi:10.48550/arXiv.{arxiv_id} instead of arXiv notation. "
                    "See https://ipac-docs.jacow.org/Paper/Writing/general/#dois-for-arxiv",
                    original=arxiv_m.group(0),
                    suggested=f"doi:{suggested}",
                )
            else:
                _add(
                    paper,
                    "URL-AS-DOI-01",
                    Severity.WARNING,
                    f"Reference {{{ref.key}}}: arXiv notation detected, and the derived "
                    f"DOI doi:{suggested} does not resolve. Check the arXiv identifier.",
                    original=arxiv_m.group(0),
                )
            continue  # one finding per ref is enough

        urls = _extract_urls_from_ref(ref)
        if not urls:
            continue  # no URL at all — handled by check_missing_doi

        if not _is_paper_ref(ref):
            continue  # not a paper; URL may be intentional (e.g. software repo)

        # ── 2. Direct URL → DOI derivation ───────────────────────────────────
        # A DOI carried *inside* the URL is authoritative and needs no check.
        # A DOI *constructed* from a URL pattern is a guess and must resolve
        # before it is ever put in front of an editor.
        suggested_doi: str | None = None
        source_url: str | None = None
        unverifiable: list[str] = []
        for url in urls:
            candidate, authoritative = _url_to_doi_direct(url)
            if not candidate:
                continue
            if authoritative:
                suggested_doi, source_url = candidate, url
                break
            verdict = verify_doi(candidate)
            if verdict is DoiVerdict.VERIFIED:
                suggested_doi, source_url = candidate, url
                break
            if verdict is DoiVerdict.UNVERIFIED:
                unverifiable.append(candidate)

        # ── 3. refs.jacow.org search (for proceedings without recognisable URL) ─
        if not suggested_doi:
            q_key = (ref.title or "") + "|" + "|".join(ref.authors[:1])
            if q_key in jacow_cache:
                suggested_doi = jacow_cache[q_key]
            else:
                suggested_doi = _search_refs_jacow(ref)
                jacow_cache[q_key] = suggested_doi
            if suggested_doi:
                source_url = source_url or (urls[0] if urls else None)

        # ── 4. Crossref fallback (journal articles only) ───────────────────────
        if not suggested_doi and _likely_requires_doi(ref):
            cq = _crossref_query(ref)
            if cq:
                if cq in crossref_cache:
                    suggested_doi = crossref_cache[cq]
                else:
                    suggested_doi = _lookup_doi_crossref(ref)
                    crossref_cache[cq] = suggested_doi
                if suggested_doi:
                    source_url = source_url or (urls[0] if urls else None)

        if suggested_doi:
            # If the URL itself was a doi: or doi.org reference, it just needs
            # to be moved to the doi field — produce a clear message.
            url_is_doi = any(
                re.match(r'doi:\s*10\.', u, re.IGNORECASE) or
                _DOI_ORG_URL_RE.match(u)
                for u in urls
            )
            if url_is_doi:
                _add(
                    paper,
                    "URL-AS-DOI-01",
                    Severity.WARNING,
                    f"Reference {{{ref.key}}}: DOI stored in url field "
                    f"instead of doi field. Move to doi = {{{suggested_doi}}}",
                    original=source_url or urls[0],
                    suggested=f"doi:{suggested_doi}",
                )
            else:
                _add(
                    paper,
                    "URL-AS-DOI-01",
                    Severity.WARNING,
                    f"Reference {{{ref.key}}}: URL used instead of DOI. "
                    f"Replace {(source_url or urls[0])!r} with doi:{suggested_doi}",
                    original=source_url or urls[0],
                    suggested=f"doi:{suggested_doi}",
                )
        elif unverifiable or not (
            STATUS.reachable("crossref") or STATUS.reachable("doi.org")
            or STATUS.reachable("jacow-refdb")
        ):
            # We could not reach any authority. Say exactly that, and do not
            # imply anything about the reference itself.
            offline = ", ".join(label(name) for name in STATUS.offline_services()) or "the DOI authorities"
            _add(
                paper,
                "URL-AS-DOI-01",
                Severity.INFO,
                f"Reference {{{ref.key}}}: NOT CHECKED — could not reach {offline}, "
                f"so no DOI lookup was performed for {urls[0]!r}.",
                original=urls[0],
            )
        else:
            _add(
                paper,
                "URL-AS-DOI-01",
                Severity.WARNING,
                f"Reference {{{ref.key}}}: a URL is given where JACoW expects a DOI, and "
                f"no DOI was found for it in Crossref or refs.jacow.org. "
                f"URL: {urls[0]!r}. Add the correct doi: field, or keep the URL if the "
                f"item genuinely has no DOI.",
                original=urls[0],
            )


# ---------------------------------------------------------------------------
# DOI-FMT-01 — doi: prefix normalisation (for manual \bibitem entries)
# ---------------------------------------------------------------------------

def check_doi_format(paper: Paper) -> None:
    """DOI-FMT-01/02: DOI prefix normalisation and \\url→\\doi replacement."""
    pt = _pt(paper)
    for ref in paper.references:
        if not ref.raw_text:
            continue
        # Look for DOI patterns that are wrong
        bad_doi = re.search(
            r'\b(DOI|Doi|doi\s+|doi:\s+)(10\.\S+)',
            ref.raw_text,
        )
        if bad_doi:
            original = bad_doi.group(0)
            suggested = f"doi:{bad_doi.group(2)}"
            if original != suggested:
                _add(paper, "DOI-FMT-01", Severity.WARNING,
                     f"Reference [{ref.n}]: DOI prefix should be 'doi:' "
                     f"(no spaces, lowercase). Found: {original!r}",
                     original=original,
                     suggested=suggested)

    # DOI-FMT-02: any \url{<doi>} form should be \doi{10.xxx}
    url_doi_pat = re.compile(
        r'\\url\{'
        r'(?:https?://(?:dx\.)?doi\.org/|[Dd][Oo][Ii]:\s*)'
        r'(10\.[^}]+)\}'
    )
    if pt and pt.source_lines:
        for lineno, line in enumerate(pt.source_lines, start=1):
            m = url_doi_pat.search(line)
            if m:
                doi_val = m.group(1).strip()
                _add(paper, "DOI-FMT-02", Severity.WARNING,
                     rf"Use \doi{{{doi_val}}} instead of \url{{<doi>}} "
                     "in reference entries. (Auto-fixed in _edited.tex)",
                     line=lineno,
                     original=m.group(0),
                     suggested=f"\\doi{{{doi_val}}}")


# ---------------------------------------------------------------------------
# DOI-MISSING-01 — likely journal/article references should include DOI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# URL-AS-DOI-01 — compiled patterns
# ---------------------------------------------------------------------------

_ARXIV_URL_RE = re.compile(
    r'https?://arxiv\.org/(?:abs|pdf)/([\w./-]+?)(?:v\d+)?(?:\.pdf)?$',
    re.IGNORECASE,
)
_ARXIV_RAW_RE = re.compile(
    r'\barXiv:([A-Za-z\-]+/\d+|\d{4}\.\d{4,5})(?:v\d+)?\b',
    re.IGNORECASE,
)
_DOI_ORG_URL_RE = re.compile(
    r'https?://(?:dx\.)?doi\.org/(10\.[^/\s\]{}]+)',
    re.IGNORECASE,
)
_JACOW_URL_RE = re.compile(
    r'https?://(?:www\.)?jacow\.org/([^/]+)/papers/([^/.?#]+)(?:\.pdf)?',
    re.IGNORECASE,
)
_ACCELCONF_URL_RE = re.compile(
    r'https?://accelconf\.web\.cern\.ch/([^/]+)/papers/([^/.?#]+)(?:\.pdf)?',
    re.IGNORECASE,
)
# Matches a doi.org link inside refs.jacow.org HTML response
_JACOW_HTML_DOI_RE = re.compile(r'href="https?://doi\.org/(10\.[^"]+)"')
_TITLE_STOPWORDS = {
    'a', 'an', 'and', 'at', 'by', 'for', 'from', 'in', 'of', 'on', 'or',
    'the', 'to', 'with', 'using', 'via', 'into', 'over', 'under', 'paper',
}


def _fetch_crossref_work(doi: str) -> dict | None:
    """Fetch Crossref metadata for *doi* and return the message payload."""
    doi = doi.strip().removeprefix("doi:").strip().rstrip('.,;)]}')
    if not doi:
        return None

    headers = {"User-Agent": "aiagent-prescreen/0.1"}
    email = os.getenv("CROSSREF_EMAIL", "").strip()
    if email:
        headers["User-Agent"] = f"aiagent-prescreen/0.1 (mailto:{email})"

    with STATUS.attempt("crossref") as outcome:
        try:
            resp = httpx.get(
                f"https://api.crossref.org/works/{doi}",
                headers=headers,
                timeout=8.0,
            )
        except Exception as exc:  # noqa: BLE001 — network failure, not a data answer
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return None
        if resp.status_code == 404:
            # A real answer: Crossref does not know this DOI.
            outcome.succeeded()
            return None
        if resp.status_code != 200:
            outcome.failed(f"HTTP {resp.status_code}")
            return None
        outcome.succeeded()
        return resp.json().get("message", {})


def _title_tokens(text: str) -> set[str]:
    cleaned = re.sub(r'[^a-z0-9]+', ' ', text.lower())
    return {
        tok for tok in cleaned.split()
        if len(tok) >= 4 and tok not in _TITLE_STOPWORDS
    }


def _extract_ref_year(ref: Reference) -> int | None:
    if ref.date:
        m = re.search(r'\b(19|20)\d{2}\b', str(ref.date))
        if m:
            return int(m.group(0))
    m = re.search(r'\b(19|20)\d{2}\b', ref.raw_text or '')
    return int(m.group(0)) if m else None


def _extract_crossref_year(message: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = message.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except Exception:
                continue
    return None


def _ref_author_surname(ref: Reference) -> str | None:
    if not ref.authors:
        return None
    author = ref.authors[0].strip()
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+", author)
    return tokens[-1].lower() if tokens else None


def _crossref_author_surnames(message: dict) -> set[str]:
    surnames: set[str] = set()
    for author in message.get("author", []) or []:
        family = str(author.get("family", "")).strip().lower()
        if family:
            surnames.add(family)
    return surnames


def _doi_matches_reference(ref: Reference, doi: str, message: dict | None = None) -> bool:
    """Return True when DOI metadata is a plausible match for *ref*."""
    message = message or _fetch_crossref_work(doi)
    if not message:
        return _validate_doi_online(doi)

    if ref.title:
        ref_title = ref.title.strip()
        candidate_title = " ".join(message.get("title", []) or []).strip()
        if not candidate_title:
            return False

        ratio = difflib.SequenceMatcher(
            None,
            re.sub(r'\s+', ' ', ref_title.lower()),
            re.sub(r'\s+', ' ', candidate_title.lower()),
        ).ratio()
        overlap = 0.0
        ref_tokens = _title_tokens(ref_title)
        cand_tokens = _title_tokens(candidate_title)
        if ref_tokens and cand_tokens:
            overlap = len(ref_tokens & cand_tokens) / max(1, len(ref_tokens))

        if ratio < 0.55 and overlap < 0.45:
            return False

    ref_year = _extract_ref_year(ref)
    cand_year = _extract_crossref_year(message)
    if ref_year and cand_year and ref_year != cand_year:
        return False

    ref_surname = _ref_author_surname(ref)
    cand_surnames = _crossref_author_surnames(message)
    if ref_surname and cand_surnames and ref_surname not in cand_surnames:
        return False

    return True


class DoiVerdict(str, Enum):
    """Outcome of trying to verify a DOI against an authority."""

    VERIFIED = "verified"        # an authority confirmed it resolves
    NOT_FOUND = "not_found"      # an authority answered and does not know it
    UNVERIFIED = "unverified"    # no authority could be reached — says nothing

    def __bool__(self) -> bool:  # keeps `if _validate_doi_online(x):` honest
        return self is DoiVerdict.VERIFIED


def verify_doi(doi: str) -> DoiVerdict:
    """Verify *doi* against Crossref, then the doi.org resolver.

    Returns three states, not two.  This is the fix for the single most
    misleading behaviour of the previous version: every lookup swallowed its
    exception and returned ``False``, so "this DOI does not exist" and "we had
    no network" produced the same output.  On a run with blocked egress the
    agent emitted 25 confident "a DOI could not be found automatically"
    warnings, several of them for references with well-known DOIs.

    Callers must treat :attr:`UNVERIFIED` as *no information* — never as a
    problem with the reference, and never as licence to suggest the DOI.
    """
    doi = doi.strip().removeprefix("doi:").strip().rstrip('.,;)]}')
    if not doi:
        return DoiVerdict.NOT_FOUND

    if _fetch_crossref_work(doi):
        return DoiVerdict.VERIFIED

    headers = {"User-Agent": "aiagent-prescreen/0.1"}
    email = os.getenv("CROSSREF_EMAIL", "").strip()
    if email:
        headers["User-Agent"] = f"aiagent-prescreen/0.1 (mailto:{email})"

    with STATUS.attempt("doi.org") as outcome:
        try:
            resp = httpx.head(
                f"https://doi.org/{doi}",
                headers={
                    "User-Agent": headers["User-Agent"],
                    "Accept": "text/html,application/xhtml+xml",
                },
                timeout=8.0,
                follow_redirects=True,
            )
        except Exception as exc:  # noqa: BLE001
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return _no_authority_reached()
        outcome.succeeded()
        if resp.status_code < 400:
            return DoiVerdict.VERIFIED
        if resp.status_code in (404, 410):
            return DoiVerdict.NOT_FOUND
        return DoiVerdict.UNVERIFIED


def _no_authority_reached() -> DoiVerdict:
    if STATUS.reachable("crossref") or STATUS.reachable("doi.org"):
        return DoiVerdict.NOT_FOUND
    return DoiVerdict.UNVERIFIED


def _validate_doi_online(doi: str) -> bool:
    """Backwards-compatible boolean wrapper — True only when verified."""
    return verify_doi(doi) is DoiVerdict.VERIFIED


# JACoW DOIs are minted as 10.18429/JACoW-<CONF><YEAR>-<PAPERID>, e.g.
# 10.18429/JACoW-IPAC2023-TUPL139.  A proceedings URL directory sometimes
# carries exactly that ("ipac2023") and sometimes carries a legacy code that is
# NOT part of any DOI ("p05" for PAC 2005, "e04", "l02").  Only the first form
# may be turned into a DOI candidate, and even then it must be verified before
# it is shown: an earlier version derived "10.18429/JACoW-p05-FPAT077" from
# https://jacow.org/p05/papers/FPAT077.pdf and offered it unchecked, which is a
# dead DOI in the published proceedings if an editor accepts it.
_CONF_DIR_RE = re.compile(r"^([A-Za-z]{2,10})(\d{4})$")


def _jacow_conference_tag(directory: str) -> str | None:
    """Return the DOI conference tag for a proceedings URL directory, or None."""
    match = _CONF_DIR_RE.match(directory.strip())
    if not match:
        return None  # legacy code such as "p05" — no DOI can be derived
    return f"{match.group(1).upper()}{match.group(2)}"


def _url_to_doi_direct(url: str) -> tuple[str | None, bool]:
    """Derive a DOI from a URL without network requests, where possible.

    Returns ``(doi, is_authoritative)``.  ``is_authoritative`` is True only when
    the URL *contains* the DOI (a doi.org link or a ``doi:`` token), so no
    verification is needed.  A DOI merely *constructed* from a URL pattern is
    returned with False and must be verified by the caller before being shown.
    """
    url = url.strip().rstrip('.,;)]}')

    # doi: prefix notation stored directly in the url field
    m = re.match(r'doi:\s*(10\.\S+)', url, re.IGNORECASE)
    if m:
        return m.group(1).rstrip('.,;'), True

    m = _DOI_ORG_URL_RE.match(url)
    if m:
        return m.group(1).rstrip('.,;'), True

    m = _ARXIV_URL_RE.match(url)
    if m:
        return f"10.48550/arXiv.{m.group(1).rstrip('/')}", False

    for pattern in (_JACOW_URL_RE, _ACCELCONF_URL_RE):
        m = pattern.match(url)
        if m:
            tag = _jacow_conference_tag(m.group(1))
            if not tag:
                return None, False
            return f"10.18429/JACoW-{tag}-{m.group(2).upper()}", False

    return None, False


def _extract_urls_from_ref(ref: Reference) -> list[str]:
    """Collect all URLs from a reference (url field + \\url{} + bare URLs)."""
    seen: set[str] = set()
    result: list[str] = []

    def _keep(u: str) -> None:
        u = u.strip().rstrip('.,;)]}')
        if u and u not in seen:
            seen.add(u)
            result.append(u)

    if ref.url:
        _keep(ref.url)
    raw = ref.raw_text or ""
    for m in re.finditer(r'\\url\{([^}]+)\}', raw):
        _keep(m.group(1))
    # bare https:// URLs not already captured
    no_url_cmd = re.sub(r'\\url\{[^}]+\}', '', raw)
    for m in re.finditer(r'https?://\S+', no_url_cmd):
        _keep(m.group(0))
    return result


def _is_paper_ref(ref: Reference) -> bool:
    """Return True if ref looks like a scholarly paper that should have a DOI."""
    rt = (ref.ref_type or "").lower()
    if rt in {"journal", "proceedings", "arxiv"}:
        return True
    raw = (ref.raw_text or "").lower()
    return bool(re.search(
        r'\b(phys\.|journal|j\. phys|proc\.|in proc\.|conference|'
        r'arxiv|preprint|ieee trans|nucl\.)\b',
        raw,
    ))


def _search_refs_jacow(ref: Reference) -> str | None:
    """Search refs.jacow.org for a DOI matching *ref*; returns first hit or None."""
    # Build a concise query: prefer title + first author
    parts: list[str] = []
    if ref.title:
        parts.append(ref.title)
    if ref.authors:
        parts.append(ref.authors[0])
    if ref.container_title:
        parts.append(ref.container_title)
    if ref.date:
        parts.append(str(ref.date))
    if not parts and ref.raw_text:
        # For manual \bibitem refs, use the raw text
        parts.append(ref.raw_text[:200])
    q = " ".join(p for p in parts if p).strip()
    if not q:
        return None
    headers = {
        "User-Agent": "aiagent-prescreen/0.1",
        "Accept": "text/html",
    }
    with STATUS.attempt("jacow-refdb") as outcome:
        try:
            resp = httpx.get(
                "https://refs.jacow.org/",
                params={"query": q, "formatType": "text"},
                headers=headers,
                timeout=10.0,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return None
        outcome.succeeded()
        for doi in _JACOW_HTML_DOI_RE.findall(resp.text):
            candidate = doi.strip()
            if _doi_matches_reference(ref, candidate):
                return candidate
        return None


def _likely_requires_doi(ref: Reference) -> bool:
    """Return True if *ref* looks like a scholarly article that should have DOI."""
    rt = (ref.ref_type or "").lower()
    if rt in {"journal"}:
        return True
    if rt in {
        "proceedings", "proceedings_unpublished", "online", "arxiv",
        "book", "chapter", "thesis", "report", "patent", "unpublished",
    }:
        return False

    raw = (ref.raw_text or "").lower()
    # Journal-like cues
    if re.search(r'\b(phys\.?\s+rev|journal|j\.|nucl\.?\s+instr|rev\.?\s+sci\.?\s+instr|scientific reports|nature|science|plasma)\b', raw):
        return True
    # Conference / web cues (usually DOI optional in JACoW references)
    if re.search(r'\b(proc\.|in\s+proc\.|conference|ipac|linac|napac|url|http)\b', raw):
        return False
    return False


def _crossref_query(ref: Reference) -> str:
    """Build a concise Crossref bibliographic query string from *ref*."""
    parts: list[str] = []
    if ref.title:
        parts.append(ref.title)
    if ref.container_title:
        parts.append(ref.container_title)
    if ref.authors:
        parts.append(ref.authors[0])
    if ref.date:
        parts.append(str(ref.date))
    if not parts and ref.raw_text:
        parts.append(ref.raw_text)
    return " ".join(p for p in parts if p).strip()


def _lookup_doi_crossref(ref: Reference) -> str | None:
    """Try to find a DOI for *ref* using Crossref. Returns DOI or None."""
    q = _crossref_query(ref)
    if not q:
        return None

    params = {
        "query.bibliographic": q,
        "rows": 5,
    }
    headers = {"User-Agent": "aiagent-prescreen/0.1"}
    email = os.getenv("CROSSREF_EMAIL", "").strip()
    if email:
        headers["User-Agent"] = f"aiagent-prescreen/0.1 (mailto:{email})"

    try:
        resp = httpx.get(
            "https://api.crossref.org/works",
            params=params,
            headers=headers,
            timeout=8.0,
        )
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except Exception:
        return None

    if not items:
        return None

    # Prefer highest-score match with a DOI.
    for item in items:
        doi = item.get("DOI")
        if doi:
            candidate = str(doi).strip()
            if _doi_matches_reference(ref, candidate, message=item):
                return candidate
    return None


def check_missing_doi(paper: Paper) -> None:
    """DOI-MISSING-01: likely article references should include a DOI.

    This check is *only* meaningful when Crossref answers.  Without it the
    finding degenerates into "we did not look", which on the sample corpus
    produced 25 warnings carrying no information and no suggestion.  So the
    first lookup decides whether the check runs at all: if Crossref cannot be
    reached, the paper gets one INFO line saying the check did not run, and no
    per-reference warnings.
    """
    cache: dict[str, str | None] = {}
    candidates = [
        ref for ref in paper.references
        if not ref.doi and not _extract_urls_from_ref(ref) and _likely_requires_doi(ref)
    ]
    if not candidates:
        return

    # Probe once with the first candidate, then decide.
    _lookup_doi_crossref(candidates[0])
    if not STATUS.reachable("crossref"):
        _add(
            paper,
            "DOI-MISSING-01",
            Severity.INFO,
            f"NOT CHECKED — {len(candidates)} reference(s) have no DOI, but "
            f"{label('crossref')} could not be reached on this run, so no DOI lookup "
            "was performed. Re-run with network access to check them.",
        )
        return

    for ref in paper.references:
        if ref.doi:
            continue
        # Refs with URLs are handled by check_url_instead_of_doi
        if _extract_urls_from_ref(ref):
            continue
        if not _likely_requires_doi(ref):
            continue

        q = _crossref_query(ref)
        if q in cache:
            found = cache[q]
        else:
            found = _lookup_doi_crossref(ref)
            cache[q] = found

        if found:
            _add(
                paper,
                "DOI-MISSING-01",
                Severity.WARNING,
                f"Reference {{{ref.key}}} appears to be a journal/article entry "
                f"without DOI. Crossref suggests: {found}.",
                original=ref.raw_text or ref.key,
                suggested=f"doi:{found}",
            )
        else:
            _add(
                paper,
                "DOI-MISSING-01",
                Severity.WARNING,
                f"Reference {{{ref.key}}} looks like a journal article with no DOI. "
                f"{label('crossref')} was searched and returned no confident match, so "
                "the DOI needs to be added by hand (or the entry is not an article).",
                original=ref.raw_text or ref.key,
            )


# ---------------------------------------------------------------------------
# BRACKET-FMT — detect [1][2] or [ 3 ] patterns in body text
# ---------------------------------------------------------------------------

def check_citation_bracket_format(paper: Paper) -> None:
    """CITE-BRACKET-01/02, CITE-SPACE-01: flag bracket format issues in source."""
    pt = _pt(paper)
    if not pt:
        return

    # Pattern: two consecutive cite brackets [n][m]
    adjacent_pat = re.compile(r'\[(\d[\d,\s\-–]*)\]\s*\[(\d[\d,\s\-–]*)\]')
    # Pattern: spaces inside bracket [ 3 ]
    space_pat = re.compile(r'\[\s+(\d[\d,\s\-–]*\d|\d)\s+\]')

    for lineno, line in enumerate(pt.source_lines, start=1):
        clean = re.sub(r'(?<!\\)%.*', '', line)  # strip comment
        for m in adjacent_pat.finditer(clean):
            _add(paper, "CITE-BRACKET-01", Severity.WARNING,
                 f"Adjacent citation brackets should be merged into one: "
                 f"{m.group(0)!r} → [{m.group(1)}, {m.group(2)}]",
                 line=lineno,
                 original=m.group(0),
                 suggested=f"[{m.group(1)}, {m.group(2)}]")
        for m in space_pat.finditer(clean):
            inner = m.group(1)
            _add(paper, "CITE-SPACE-01", Severity.WARNING,
                 f"Extra spaces inside citation bracket: {m.group(0)!r} → [{inner}]",
                 line=lineno,
                 original=m.group(0),
                 suggested=f"[{inner}]")


# ---------------------------------------------------------------------------
# BIB-MISSING-01 — \addbibresource names a file not present in the submission
# ---------------------------------------------------------------------------

def check_bib_resources(paper: Paper) -> None:
    """BIB-MISSING-01: every \\addbibresource{f} must resolve to an actual file."""
    pt = _pt(paper)
    if not pt or not pt.uses_biblatex:
        return
    if not paper.source_path:
        return

    folder = paper.source_path.parent.parent  # Source_Files/ -> submission root
    # Collect all .bib files anywhere in the submission
    available_bibs = {f.name for f in folder.rglob("*.bib")}

    # Ignore commented-out addbibresource lines; some templates keep an example
    # bibliography resource commented next to the real one.
    cleaned_source = "\n".join(
        re.sub(r'(?<!\\)%.*', '', line) for line in pt.source_lines
    )
    declared = re.findall(r'\\addbibresource\{([^}]+\.bib)\}', cleaned_source)
    for bib_name in declared:
        if bib_name not in available_bibs:
            hint = ""
            if available_bibs:
                close = difflib.get_close_matches(bib_name, available_bibs, n=1, cutoff=0.4)
                hint = f" (available: {', '.join(sorted(available_bibs))}" + \
                       (f"; closest match: {close[0]}" if close else "") + ")"
            else:
                hint = " — no .bib file found anywhere in the submission"
            _add(paper, "BIB-MISSING-01", Severity.ERROR,
                 f"\\addbibresource{{{bib_name}}} references a file not found "
                 f"in the submission{hint}.",
                 original=f"\\addbibresource{{{bib_name}}}")


# ---------------------------------------------------------------------------
# FIG-MISSING-01 — \includegraphics references an image not in the submission
# ---------------------------------------------------------------------------

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg", ".gif"}


def _images_in_archives(folder: Path) -> dict[str, Path]:
    """Image names found inside .zip / .tar archives in the submission.

    JACoW authors routinely upload their figures as a single archive
    (``MOP030_fig.zip``).  Walking the filesystem alone therefore reported six
    hard ERRORs against a complete submission.  Looking inside costs
    milliseconds and removes a whole class of false positive.
    """
    found: dict[str, Path] = {}
    for archive in folder.rglob("*"):
        if not archive.is_file():
            continue
        suffix = archive.suffix.lower()
        try:
            if suffix == ".zip":
                import zipfile

                with zipfile.ZipFile(archive) as zf:
                    names = zf.namelist()
            elif suffix in (".tar", ".tgz", ".gz", ".bz2", ".xz"):
                import tarfile

                if not tarfile.is_tarfile(archive):
                    continue
                with tarfile.open(archive) as tf:
                    names = tf.getnames()
            else:
                continue
        except Exception:  # noqa: BLE001 — a corrupt archive is not our problem here
            continue
        for name in names:
            entry = Path(name)
            if entry.suffix.lower() in _IMG_EXTS:
                found[entry.name] = archive
                found[entry.stem] = archive
    return found


def check_figure_files(paper: Paper) -> None:
    r"""FIG-MISSING-01: every ``\includegraphics{f}`` should resolve to a file.

    Severity is deliberately graded.  A figure that is nowhere in the
    submission is an ERROR the editor must chase.  A figure that exists but only
    inside an archive is a WARNING addressed to the *submission*, not the
    source: the paper will build once the archive is unpacked.
    """
    pt = _pt(paper)
    if not pt or not paper.source_path:
        return

    folder = paper.source_path.parent.parent  # submission root
    available_images: dict[str, Path] = {}
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in _IMG_EXTS:
            available_images[f.name] = f
            available_images[f.stem] = f

    archived_images = _images_in_archives(folder)

    inc_pat = re.compile(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}')
    reported_in_archive: set[str] = set()

    for lineno, line in enumerate(pt.source_lines, start=1):
        clean = re.sub(r'(?<!\\)%.*', '', line)
        for m in inc_pat.finditer(clean):
            ref = m.group(1).strip()
            ref_stem = Path(ref).stem
            ref_name = Path(ref).name

            def _present(pool: dict[str, Path]) -> bool:
                return (
                    ref_name in pool
                    or ref_stem in pool
                    or any((ref_name + ext) in pool for ext in _IMG_EXTS)
                )

            if _present(available_images):
                continue

            if _present(archived_images):
                archive = (
                    archived_images.get(ref_name)
                    or archived_images.get(ref_stem)
                    or next(
                        (archived_images[ref_name + ext] for ext in _IMG_EXTS
                         if (ref_name + ext) in archived_images),
                        None,
                    )
                )
                archive_name = archive.name if archive else "an archive"
                if archive_name in reported_in_archive:
                    continue
                reported_in_archive.add(archive_name)
                _add(paper, "FIG-ARCHIVE-01", Severity.WARNING,
                     f"Figures are packed inside {archive_name} rather than supplied as "
                     f"individual files. Unpack it before building; the source itself is fine.",
                     line=lineno)
                continue

            close = difflib.get_close_matches(
                ref_stem, list(available_images.keys()), n=1, cutoff=0.6
            )
            suggestion = f" Did you mean '{close[0]}'?" if close else ""
            _add(paper, "FIG-MISSING-01", Severity.ERROR,
                 f"\\includegraphics{{{ref}}}: image file not found in "
                 f"the submission.{suggestion}",
                 line=lineno,
                 original=m.group(0),
                 suggested=f"\\includegraphics{{{close[0]}}}" if close else None)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all(paper: Paper) -> None:
    """Run every Phase-1 reference check against *paper*."""
    check_reference_section(paper)
    check_bib_resources(paper)   # must precede check_citation_links: a missing
    check_figure_files(paper)     # .bib explains every unresolved \cite at once
    check_citation_order(paper)
    check_citation_links(paper)
    check_reference_numbering(paper)
    check_url_instead_of_doi(paper)
    check_missing_doi(paper)
    check_doi_format(paper)
    check_citation_bracket_format(paper)
