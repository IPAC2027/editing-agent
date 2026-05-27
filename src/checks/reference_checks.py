"""Priority-1 reference and citation checks — Phase 1 implementation."""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

import httpx

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
    """CITE-LINK-01/02: cross-check in-text cites against reference list."""
    pt = _pt(paper)
    if not pt:
        return

    # Reference keys from the reference list
    ref_keys: set[str] = {r.key for r in paper.references}

    # Keys cited in text
    cited_keys: set[str] = set()
    cite_key_to_line: dict[str, int] = {}
    for occ in pt.cite_occurrences:
        if occ.key not in cite_key_to_line:
            cite_key_to_line[occ.key] = occ.line
        cited_keys.add(occ.key)

    # For biblatex papers we might not have ref_keys from bibitems — skip CITE-LINK
    if not ref_keys and pt.uses_biblatex:
        return  # ref_keys come from .bib, populated before this check is called

    # CITE-LINK-01: every \cite{key} must have a matching reference entry
    for key in sorted(cited_keys - ref_keys):
        line = cite_key_to_line.get(key)
        _add(paper, "CITE-LINK-01", Severity.ERROR,
             f"\\cite{{{key}}} has no corresponding reference entry.",
             line=line,
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
            return str(doi).strip()
    return None


def check_missing_doi(paper: Paper) -> None:
    """DOI-MISSING-01: likely article references should include DOI."""
    cache: dict[str, str | None] = {}

    for ref in paper.references:
        if ref.doi:
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
                f"Reference {{{ref.key}}} appears to be a journal/article entry "
                "without DOI, and a DOI could not be found automatically.",
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


def check_figure_files(paper: Paper) -> None:
    """FIG-MISSING-01: every \\includegraphics{f} must resolve to a file."""
    pt = _pt(paper)
    if not pt or not paper.source_path:
        return

    folder = paper.source_path.parent.parent  # submission root
    # All image files anywhere in the submission (name only, for fast lookup)
    available_images: dict[str, Path] = {}
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in _IMG_EXTS:
            available_images[f.name] = f
            available_images[f.stem] = f   # also index without extension

    inc_pat = re.compile(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}')
    for lineno, line in enumerate(pt.source_lines, start=1):
        clean = re.sub(r'(?<!\\)%.*', '', line)
        for m in inc_pat.finditer(clean):
            ref = m.group(1).strip()
            # Strip leading path component (e.g. "figures/fig1" -> "fig1")
            ref_stem = Path(ref).stem
            ref_name = Path(ref).name

            # Found if: exact name match, stem match, or name with any image ext
            found = (
                ref_name in available_images
                or ref_stem in available_images
                or any((ref_name + ext) in available_images for ext in _IMG_EXTS)
            )
            if not found:
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
    check_bib_resources(paper)
    check_figure_files(paper)
    check_citation_order(paper)
    check_citation_links(paper)
    check_reference_numbering(paper)
    check_missing_doi(paper)
    check_doi_format(paper)
    check_citation_bracket_format(paper)
