"""End-to-end reference extraction and checking workflow for Word submissions."""

from __future__ import annotations

import re
from pathlib import Path

from src.autofix.word_fixes import fix_reference
from src.checks.word_reference_checks import run_all
from src.output.word_report import write_word_reference_report
from src.parser.word_parser import parse_word


class WordPrescreenResult:
    """Lightweight result object for Word reference checking."""

    def __init__(self, paper_id: str, out_dir: Path, report_path: Path,
                 total_refs: int, findings: list) -> None:
        self.paper_id = paper_id
        self.out_dir = out_dir
        self.report_path = report_path
        self.total_refs = total_refs
        self.findings = findings


def prescreen_word(folder: Path) -> WordPrescreenResult:
    """Extract references from a Word submission, check them, and emit HTML output.

    Writes ``word_references.html`` into ``<folder>/aiagent_prescreen/``.
    """
    doc_path = _find_word_doc(folder)
    parsed = parse_word(doc_path)

    findings = run_all(parsed)

    # Apply safe fixes reference-by-reference and collect per-ref findings
    refs_before: list[tuple[int, str]] = []
    refs_after: list[tuple[int, str]] = []
    findings_by_ref: dict[int, list] = {}

    for ref in parsed.references:
        refs_before.append((ref.n, ref.raw_text))
        ref_findings = [f for f in findings if f.line == ref.n]
        suggested_doi = next(
            (
                f.suggested for f in ref_findings
                if f.check_id == "DOI-REQ-01" and f.suggested
            ),
            None,
        )
        corrected, fix_findings = fix_reference(
            ref.n,
            ref.raw_text,
            suggested_doi=suggested_doi,
        )
        # Final pass: reformat the line-level-corrected text via the
        # Tier-1 JACoW formatter so the per-ref before/after card in
        # word_references.html shows the canonical JACoW rewrite.
        formatted, fmt_finding = _format_word_reference(ref, corrected, ref_n=ref.n)
        if formatted and formatted.strip() != corrected.strip():
            corrected = formatted
            fix_findings.append(fmt_finding)
        refs_after.append((ref.n, corrected))
        findings_by_ref.setdefault(ref.n, [])
        findings_by_ref[ref.n].extend(ref_findings)
        findings_by_ref[ref.n].extend(fix_findings)

    global_findings = [f for f in findings if f.line is None or f.line <= 0]
    all_findings = global_findings + [f for fl in findings_by_ref.values() for f in fl]

    out_dir = folder / "aiagent_prescreen"
    out_dir.mkdir(exist_ok=True)

    report_path = write_word_reference_report(
        parsed.paper_id,
        refs_before,
        refs_after,
        findings_by_ref,
        global_findings,
        out_dir,
    )

    return WordPrescreenResult(
        paper_id=parsed.paper_id,
        out_dir=out_dir,
        report_path=report_path,
        total_refs=len(parsed.references),
        findings=all_findings,
    )


def _find_word_doc(folder: Path) -> Path:
    """Find the primary Word document in a submission folder."""
    candidates: list[Path] = []
    for d in (folder / "Source_Files", folder):
        if not d.is_dir():
            continue
        for path in d.iterdir():
            if path.is_file() and path.suffix.lower() in {".docx", ".doc"}:
                candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No Word document found under {folder}")

    # Prefer .docx in Source_Files, then any .docx, then .doc
    candidates.sort(key=lambda p: (
        p.suffix.lower() != ".docx",
        p.parent.name != "Source_Files",
        p.name.lower(),
    ))
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# Tier-1 integration: final-pass JACoW reformat for the Word pipeline.
# ─────────────────────────────────────────────────────────────────────────────

def _format_word_reference(
    ref,
    line_corrected: str,
    *,
    ref_n: int,
) -> tuple[str, "Finding | None"]:
    """Run :func:`src.refs.format_ref` over the line-level-corrected text.

    The :class:`WordReference` parser already extracts authors, title, year,
    DOI and ref_type heuristically; we use those structured fields to build
    a ``rec`` dict and call the JACoW formatter.  When the formatter emits a
    text that differs from *line_corrected*, the per-ref before/after card in
    ``word_references.html`` shows the JACoW rewrite as the diff.

    Returns ``(formatted_text, finding)``.  When the formatter cannot produce
    a different text (e.g. required fields missing), returns
    ``(line_corrected, None)`` and the caller's line-level fixes are kept
    untouched.
    """
    from src.models import Finding, Severity
    from src.refs import JacoWConnector, format_ref, normalize_journal
    from src.refs.extract import _extract_conference

    # Need at least a title to format anything.  Authors and year are
    # required by the formatters too, so skip when missing.
    if not (ref.title and ref.authors):
        return line_corrected, None

    rec: dict = {
        "authors_raw": " and ".join(ref.authors),
        "title": ref.title,
    }

    year_m = None
    if ref.raw_text:
        year_m = re.search(r"\b(19|20)\d{2}\b", ref.raw_text)
    if year_m:
        rec["year"] = year_m.group(0)
    else:
        return line_corrected, None

    if ref.ref_type:
        rec["ref_type"] = ref.ref_type
    if ref.doi:
        rec["doi"] = ref.doi
    if ref.url:
        rec["url"] = ref.url

    # Conference hints from the raw text (best-effort, no DB lookup).
    raw = ref.raw_text or ""
    if not rec.get("conference"):
        m = re.search(r"\bin\s+Proc\.\s*([A-Za-z][A-Za-z0-9'’\-]+)", raw)
        if m:
            rec["conference"] = m.group(1)
    # arXiv id for arXiv refs
    if (ref.ref_type or "").lower() == "arxiv":
        m = re.search(r"arXiv:\s*([\w.\-]+/?\d+|\d{4}\.\d{4,5})", raw, re.IGNORECASE)
        if m:
            rec["arxiv_id"] = m.group(1)

    # Tier-1.5: best-effort lift of conference / location / month / pages
    # / DOI from the raw text.  The Word parser doesn't put these in
    # the structured WordReference model, so without this the formatter
    # would emit a paper with no "in Proc.", no city, no month, no
    # pages — silently regressing the reference.  We only fill in
    # fields that aren't already set, so we never overwrite a value
    # that came from somewhere more authoritative.
    from src.refs.extract import extract_from_raw
    extracted = extract_from_raw(raw)
    for k in ("city", "country", "month", "pages", "paper_id",
              "doi", "journal", "volume", "issue"):
        if extracted.get(k) and not rec.get(k):
            rec[k] = extracted[k]
    if not rec.get("conference") and extracted.get("conference"):
        rec["conference"] = extracted["conference"]
    if not rec.get("year") and extracted.get("year"):
        rec["year"] = extracted["year"]

    # Tier-1: fill conference metadata when both acronym and year are known
    # AND the acronym resolves in the JACoW hardcoded table.  Strip any
    # trailing 'YY or 'YYYY suffix from the acronym so IPAC'23 → IPAC and
    # the connector's _norm_acr can match.
    if rec.get("conference"):
        rec["conference"] = re.sub(r"['’]\d{2,4}$", "", rec["conference"])
    if rec.get("conference") and rec.get("year"):
        connector = JacoWConnector(allow_network=False)
        log: list = []
        rec = connector.complete_record(rec, log)

    # Best-effort extraction of journal name and volume from raw_text.  The
    # Word parser doesn't put these in structured fields, so without this
    # the formatter would emit a paper with no journal and no vol/no/pp.
    if (rec.get("ref_type", "").lower() in (
        "journal", "journal_accepted", "journal_submitted",
    )) and not rec.get("journal"):
        rec["journal"], rec["volume"], rec["issue"], rec["pages"] = (
            _extract_journal_meta_from_raw(raw)
        )

    # Tier-1: journal abbreviation cascade (L1 hand-curated table).  Now
    # that the journal name is known, normalise it to the JACoW ANNEX C
    # abbreviation (e.g. "Physical Review Letters" → "Phys. Rev. Lett.").
    if (
        rec.get("ref_type", "").lower() in (
            "journal", "journal_accepted", "journal_submitted",
        )
        and rec.get("journal")
    ):
        normalised = normalize_journal(rec["journal"])
        if normalised and normalised != rec["journal"]:
            rec["journal"] = normalised

    try:
        formatted = format_ref(rec, rec.get("ref_type", "journal"))
    except Exception as exc:  # noqa: BLE001 — formatting is best-effort
        # Log-and-continue: the line-level fixes already produced a usable
        # text. The formatter is the icing; failure shouldn't abort the run.
        import logging

        logging.getLogger(__name__).debug(
            "format_ref failed for ref [%d]: %s", ref_n, exc,
        )
        return line_corrected, None

    formatted_clean = (formatted or "").strip()
    corrected_clean = (line_corrected or "").strip()
    if not formatted_clean or formatted_clean == corrected_clean:
        return line_corrected, None

    # Conservative guard: only emit FMT-REF-01 if the formatter output
    # preserves the key information markers carried by the line-level
    # corrected text.  This prevents the failure mode where the formatter
    # drops information the original had — e.g. "in Proc. ..." line,
    # "pp. N-M" pages, "Oct." month — and would silently regress the
    # reference instead of improving it.
    if _drops_information(corrected_clean, formatted_clean):
        import logging
        logging.getLogger(__name__).debug(
            "FMT-REF-01 skipped for ref [%d]: formatted text drops "
            "information present in the line-corrected text", ref_n,
        )
        return line_corrected, None

    finding = Finding(
        check_id="FMT-REF-01",
        severity=Severity.INFO,
        line=ref_n,
        original=corrected_clean[:240],
        suggested=formatted_clean[:240],
        message=(
            f"Reformatted reference [{ref_n}] per JACoW style "
            f"(via src.refs: format_ref + JacoWConnector + normalize_journal)."
        ),
        auto_fixed=True,
    )
    return formatted, finding


def _drops_information(original: str, formatted: str) -> bool:
    """Return True if *formatted* is missing key information markers from
    *original*.

    Used by :func:`_format_word_reference` to skip the FMT-REF-01 emission
    when the formatter would silently regress the reference.  The marker
    set is intentionally narrow — just the fields whose loss would be a
    clear regression for a JACoW-style reference:

    - ``in Proc.`` / ``presented at`` lines for conference refs
    - ``pp.`` / ``p.`` page ranges
    - ``vol.`` / ``no.`` volume / issue markers
    - 3-letter month abbreviations (Jan./Feb./...)
    - 4-digit conference years in the venue/location segment
    - DOI (when the original has one, the formatted must too)
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
    # DOI: if the original has a 10.xxxx/... DOI, the formatted must too.
    doi_re = re.compile(r"\b10\.\d{4,9}/\S+", re.IGNORECASE)
    if doi_re.search(original) and not doi_re.search(formatted):
        return True
    return False


def _extract_journal_meta_from_raw(
    raw: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Best-effort journal-name / volume / issue / pages extraction from raw text.

    Used by :func:`_format_word_reference` to fill fields the Word parser
    does not currently put in the ``WordReference`` structured model.
    Returns ``(journal, volume, issue, pages)``; any field that cannot be
    determined is ``None``.
    """
    if not raw:
        return None, None, None, None

    # Locate the first 4-digit year in the raw text — it almost always
    # marks the boundary between the citation body and the year field.
    ym = re.search(r"\b(19|20)\d{2}\b", raw)
    if not ym:
        return None, None, None, None
    body, year_end = raw[: ym.start()].rstrip(", "), ym.end()

    # Strip the authors+title prefix: the first quoted text or first comma
    # cluster after a leading initial pattern is the title boundary.
    title_m = re.search(r'["“](.*?)["”]', raw)
    if title_m:
        after_title = raw[title_m.end():]
    else:
        # No quoted title — assume the journal starts after the first comma
        # that is followed by a capitalised word (rough heuristic).
        after_title = raw

    # From the post-title text, peel off the journal name (up to the next
    # "vol.", "no.", "p.", or 4-digit-year).
    journal_m = re.match(
        r"^\s*[,\s]*\s*([A-Z][^,\n]+?)\s*,\s*"
        r"(?:vol\.|no\.|pp?\.|p\.\s*\d|(?:19|20)\d{2})",
        after_title,
        re.IGNORECASE,
    )
    if not journal_m:
        return None, None, None, None

    journal = journal_m.group(1).strip().rstrip(",").strip()
    if journal.lower() in {"proc", "in proc", "proceedings", "thesis", "phd thesis"}:
        return None, None, None, None

    # Now from the segment between the journal name and the year, pull
    # vol/no/pp.
    tail = after_title[journal_m.end(1):]
    vol = (re.search(r"vol\.\s*([\w\-\./]+)", tail, re.IGNORECASE) or [None, None])[1]
    iss = (re.search(r"no\.\s*([\w\-\./]+)", tail, re.IGNORECASE) or [None, None])[1]
    pp_m = re.search(r"pp?\.\s*([\w\-\.,–]+)", tail, re.IGNORECASE)
    pp = pp_m.group(1).strip() if pp_m else None

    return journal, vol, iss, pp
