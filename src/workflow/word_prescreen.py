"""Reference checking for Word submissions, delivered as Word tracked changes.

Word is the format most JACoW submissions arrive in, and it used to be the
format this tool did least for: it produced an HTML page of before/after cards
and no corrected document, so an editor's only option was to read a suggestion
in a browser and retype it into Word.

The output now leads with ``<name>_tracked.docx`` — the author's own document
with each correction as a Word revision.  The editor opens it, and Review →
Accept / Reject works per change, in the tool they already use.  The HTML page
is still written, because it is the only place the *reasons* fit.

Two guards decide what gets into that document:

* every line-level fix is a narrow, deterministic substitution;
* every whole-reference reformat must pass :func:`src.refs.verify.check_rewrite`,
  which compares the rewrite to the original and rejects it if a number, DOI,
  word or capital went missing.  That check is what stops the two defects seen
  on the sample corpus — ``Poincaré`` lowercased to ``poincaré`` and a doubled
  comma at ``pp. 611-632,,`` — from ever reaching an editor.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.autofix.word_fixes import fix_reference
from src.checks.word_reference_checks import run_all
from src.lookup_status import STATUS
from src.models import Finding, Severity
from src.output.word_report import write_word_reference_report
from src.parser.word_parser import parse_word
from src.refs.verify import check_rewrite, proper_noun_risk


class WordPrescreenResult:
    """Result of screening a Word submission."""

    def __init__(
        self,
        paper_id: str,
        out_dir: Path,
        report_path: Path,
        total_refs: int,
        findings: list,
        tracked_docx: str | None = None,
        revisions: int = 0,
        skipped: int = 0,
    ) -> None:
        self.paper_id = paper_id
        self.out_dir = out_dir
        self.report_path = report_path
        self.total_refs = total_refs
        self.findings = findings
        self.tracked_docx = tracked_docx
        self.revisions = revisions
        self.skipped = skipped


def prescreen_word(folder: Path) -> WordPrescreenResult:
    """Screen a Word submission and write tracked changes plus a report."""
    STATUS.reset()

    doc_path = _find_word_doc(folder)
    parsed = parse_word(doc_path)
    findings = run_all(parsed)

    out_dir = folder / "aiagent_prescreen"
    out_dir.mkdir(parents=True, exist_ok=True)

    refs_before: list[tuple[int, str]] = []
    refs_after: list[tuple[int, str]] = []
    findings_by_ref: dict[int, list] = {}
    rewrites: list = []
    rejected_rewrites = 0

    from src.output.docx_tracked import ParagraphRewrite

    for ref in parsed.references:
        ref_findings = [f for f in findings if f.line == ref.n]
        suggested_doi = next(
            (f.suggested for f in ref_findings
             if f.check_id == "DOI-REQ-01" and f.suggested),
            None,
        )

        corrected, fix_findings = fix_reference(
            ref.n, ref.raw_text, suggested_doi=suggested_doi,
        )

        formatted, format_finding, rejection = _verified_reformat(ref, corrected)
        if formatted is not None:
            corrected = formatted
            if format_finding:
                fix_findings.append(format_finding)
        elif rejection is not None:
            fix_findings.append(rejection)
            rejected_rewrites += 1

        refs_before.append((ref.n, ref.raw_text))
        refs_after.append((ref.n, corrected))
        findings_by_ref.setdefault(ref.n, [])
        findings_by_ref[ref.n].extend(ref_findings)
        findings_by_ref[ref.n].extend(fix_findings)

        if corrected.strip() == ref.raw_text.strip():
            continue

        if ref.paragraph_index < 0 or ref.paragraph_count != 1 or not ref.paragraph_text:
            findings_by_ref[ref.n].append(Finding(
                check_id="WORD-TRACK-01",
                severity=Severity.WARNING,
                line=ref.n,
                message=(
                    f"Reference [{ref.n}] spans {ref.paragraph_count} paragraphs, so it "
                    "could not be written as a single Word revision. The correction is "
                    "in word_references.html; apply it by hand."
                ),
                original=ref.raw_text[:200],
                suggested=corrected[:200],
            ))
            continue

        # Express the change against the paragraph's *real* characters, not
        # against the cleaned raw_text: the entry usually begins "[1]\t", and a
        # revision computed against collapsed whitespace would not match the
        # document and would be silently skipped.
        paragraph_after = _rebuild_paragraph(ref.paragraph_text, ref.raw_text, corrected)
        if paragraph_after is None or paragraph_after == ref.paragraph_text:
            findings_by_ref[ref.n].append(Finding(
                check_id="WORD-TRACK-01",
                severity=Severity.WARNING,
                line=ref.n,
                message=(
                    f"Reference [{ref.n}] could not be matched back to its paragraph, so "
                    "no tracked change was written. The correction is in "
                    "word_references.html."
                ),
                original=ref.raw_text[:200],
                suggested=corrected[:200],
            ))
            continue

        checks = sorted({f.check_id for f in fix_findings}) or ["FMT-REF-01"]
        rewrites.append(ParagraphRewrite(
            paragraph_index=ref.paragraph_index,
            before=ref.paragraph_text,
            after=paragraph_after,
            author=f"JACoW prescreen ({', '.join(checks)})",
            note="; ".join(f.message for f in fix_findings),
        ))

    # --- Word tracked changes ------------------------------------------
    tracked_name: str | None = None
    revisions = 0
    skipped: list = []
    if rewrites:
        from src.output.docx_tracked import write_tracked_docx

        tracked_path = out_dir / f"{doc_path.stem}_tracked.docx"
        try:
            _path, revision_blocks, skipped = write_tracked_docx(
                doc_path, tracked_path, rewrites,
            )
            # Report *corrections*, not revision blocks: one correction can be
            # several w:ins/w:del pairs, and an editor counts references.
            revisions = len(rewrites) - len(skipped)
            tracked_name = tracked_path.name
        except Exception as exc:  # noqa: BLE001 — never lose the report over this
            findings.append(Finding(
                check_id="WORD-TRACK-02",
                severity=Severity.WARNING,
                message=(
                    f"Could not write tracked changes ({type(exc).__name__}: {exc}). "
                    "The corrections are still listed in word_references.html."
                ),
            ))

    global_findings = [f for f in findings if f.line is None or f.line <= 0]
    if tracked_name:
        global_findings.insert(0, Finding(
            check_id="WORD-TRACK-00",
            severity=Severity.INFO,
            message=(
                f"{revisions} reference(s) corrected as tracked changes in "
                f"{tracked_name}. Open it in "
                "Word and use Review → Accept or Reject on each one; rejecting restores "
                "the author's text exactly."
            ),
        ))
    if skipped:
        global_findings.append(Finding(
            check_id="WORD-TRACK-01",
            severity=Severity.WARNING,
            message=(
                f"{len(skipped)} correction(s) could not be written as revisions because "
                "the paragraph text had changed; see word_references.html."
            ),
        ))
    if rejected_rewrites:
        global_findings.append(Finding(
            check_id="FMT-REF-01",
            severity=Severity.INFO,
            message=(
                f"{rejected_rewrites} reference(s) were left exactly as submitted because "
                "the JACoW-style rewrite would have lost or altered information. Each one "
                "says what it would have damaged."
            ),
        ))

    # A check and the correction that resolves it are two views of one problem;
    # reporting both is how the LaTeX side came to list DOI-FMT-02 twice per
    # occurrence.  Keep the finding only when nothing was corrected for it.
    corrected_refs = {rewrite.paragraph_index for rewrite in rewrites}
    index_by_ref = {ref.n: ref.paragraph_index for ref in parsed.references}
    for ref_n, group in findings_by_ref.items():
        if index_by_ref.get(ref_n) not in corrected_refs:
            continue
        fixed_checks = {f.check_id for f in group if f.auto_fixed}
        findings_by_ref[ref_n] = [
            f for f in group
            if f.auto_fixed or f.check_id not in fixed_checks
        ]

    all_findings = global_findings + [
        f for group in findings_by_ref.values() for f in group
    ]

    report_path = write_word_reference_report(
        parsed.paper_id,
        refs_before,
        refs_after,
        findings_by_ref,
        global_findings,
        out_dir,
    )
    _write_word_report_md(
        out_dir / "report.md",
        parsed.paper_id,
        doc_path.name,
        tracked_name,
        revisions,
        refs_before,
        all_findings,
    )

    return WordPrescreenResult(
        paper_id=parsed.paper_id,
        out_dir=out_dir,
        report_path=report_path,
        total_refs=len(parsed.references),
        findings=all_findings,
        tracked_docx=tracked_name,
        revisions=revisions,
        skipped=len(skipped),
    )


def _rebuild_paragraph(paragraph_text: str, raw_body: str, corrected_body: str) -> str | None:
    r"""Put *corrected_body* back into *paragraph_text*, keeping its prefix.

    A reference paragraph looks like ``[1]\tAuthors, "Title", ...``.  The parser
    hands the checks a cleaned body without the ``[1]`` label; this puts the
    corrected body back after whatever prefix the document actually uses, so the
    tracked change matches the document byte for byte.
    """
    match = re.match(r"^(\s*\[\d+\][\s\t\u00a0]*)(.*)$", paragraph_text, re.DOTALL)
    if match:
        return match.group(1) + corrected_body
    # No bracket label: fall back to a whitespace-insensitive comparison.
    if _squash(paragraph_text) == _squash(raw_body):
        return corrected_body
    return None


def _squash(text: str) -> str:
    return " ".join(text.replace("\t", " ").replace("\u00a0", " ").split())


def _find_word_doc(folder: Path) -> Path:
    """Find the primary Word document in a submission folder."""
    candidates: list[Path] = []
    for directory in (folder / "Source_Files", folder):
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() in {".docx", ".doc"}:
                if "_tracked" in path.stem:
                    continue  # our own previous output
                candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No Word document found under {folder}")
    candidates.sort(key=lambda p: (
        p.suffix.lower() != ".docx",
        p.parent.name != "Source_Files",
        p.name.lower(),
    ))
    return candidates[0]


# ---------------------------------------------------------------------------
# Verified whole-reference reformat
# ---------------------------------------------------------------------------

def _verified_reformat(ref, line_corrected: str):
    """Reformat one reference to JACoW style, but only if it verifies.

    Returns ``(formatted_or_None, accept_finding, rejection_finding)``.
    """
    formatted, finding = _format_word_reference(ref, line_corrected, ref_n=ref.n)
    if not formatted or formatted.strip() == line_corrected.strip():
        return None, None, None

    verdict = check_rewrite(line_corrected, formatted, allow_case_change=False)
    if verdict.ok:
        return formatted, finding, None

    risky = proper_noun_risk(line_corrected, formatted)
    detail = verdict.reason
    if risky:
        detail += f" (words at risk: {', '.join(risky[:4])})"
    return None, None, Finding(
        check_id="FMT-REF-01",
        severity=Severity.INFO,
        line=ref.n,
        message=(
            f"Reference [{ref.n}]: a JACoW-style rewrite was computed but rejected "
            f"because it would have {detail}. The reference is unchanged."
        ),
        original=line_corrected[:220],
    )


def _format_word_reference(ref, line_corrected: str, *, ref_n: int):
    """Run the JACoW formatter over the line-corrected reference text.

    Unchanged in intent from the previous version — it is the *verification*
    around it that changed. The formatter still fills conference metadata from
    the offline JACoW table and normalises the journal title, and still never
    invents a value it was not given.
    """
    from src.refs import JacoWConnector, format_ref, normalize_journal

    if not (ref.title and ref.authors):
        return line_corrected, None

    record: dict = {
        "authors_raw": " and ".join(ref.authors),
        "title": ref.title,
    }

    year = re.search(r"\b(19|20)\d{2}\b", ref.raw_text or "")
    if not year:
        return line_corrected, None
    record["year"] = year.group(0)

    if ref.ref_type:
        record["ref_type"] = ref.ref_type
    if ref.doi:
        record["doi"] = ref.doi
    if ref.url:
        record["url"] = ref.url

    raw = ref.raw_text or ""
    conference = re.search(r"\bin\s+Proc\.\s*([A-Za-z][A-Za-z0-9'’\-]+)", raw)
    if conference:
        record["conference"] = conference.group(1)
    if (ref.ref_type or "").lower() == "arxiv":
        arxiv = re.search(r"arXiv:\s*([\w.\-]+/?\d+|\d{4}\.\d{4,5})", raw, re.IGNORECASE)
        if arxiv:
            record["arxiv_id"] = arxiv.group(1)

    from src.refs.extract import extract_from_raw

    extracted = extract_from_raw(raw)
    for key in ("city", "country", "month", "pages", "paper_id",
                "doi", "journal", "volume", "issue", "conference", "year"):
        if extracted.get(key) and not record.get(key):
            record[key] = extracted[key]

    if record.get("conference"):
        record["conference"] = re.sub(r"['’]\d{2,4}$", "", record["conference"])
        if record.get("year"):
            record = JacoWConnector(allow_network=False).complete_record(record, [])
    if record.get("journal"):
        normalised = normalize_journal(record["journal"])
        if normalised:
            record["journal"] = normalised

    try:
        formatted = format_ref(record, record.get("ref_type", "journal"))
    except Exception:  # noqa: BLE001
        return line_corrected, None

    formatted = (formatted or "").strip()
    if not formatted or formatted == line_corrected.strip():
        # No-op: the caller keeps its own text and no finding is emitted.  An
        # "improvement" that changes nothing must never be reported.
        return line_corrected, None

    return formatted, Finding(
        check_id="FMT-REF-01",
        severity=Severity.INFO,
        line=ref_n,
        original=line_corrected[:240],
        suggested=formatted[:240],
        message=(
            f"Reference [{ref_n}] reformatted to JACoW Annex B style; verified to "
            "preserve every number, DOI, word and capital in the original."
        ),
        auto_fixed=True,
    )


# ---------------------------------------------------------------------------
# report.md for Word submissions
# ---------------------------------------------------------------------------

def _write_word_report_md(
    path: Path,
    paper_id: str,
    doc_name: str,
    tracked_name: str | None,
    revisions: int,
    refs_before: list[tuple[int, str]],
    findings: list,
) -> None:
    from datetime import datetime, timezone

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    errors = [f for f in findings if f.severity is Severity.ERROR]
    warnings = [f for f in findings if f.severity is Severity.WARNING]
    notes = [f for f in findings if f.severity is Severity.INFO]

    lines = [
        f"# Pre-screen — {paper_id} (Word)",
        "",
        f"**{'NEEDS WORK' if errors else ('REVIEW' if revisions or warnings else 'CLEAN')}** "
        f"· {generated} · source `{doc_name}`",
        "",
        f"- **{revisions}** tracked change(s) written",
        f"- **{len(refs_before)}** reference(s) checked",
        f"- **{len(errors)}** problem(s) needing a human, "
        f"**{len(warnings)}** warning(s), **{len(notes)}** note(s)",
        "",
        "## What to do",
        "",
    ]
    if tracked_name:
        lines += [
            f"1. Open **`{tracked_name}`** in Word.",
            "2. Review → Accept or Reject each change. Rejecting restores the author's "
            "text exactly; the revision author names the rule behind each change, so "
            "you can accept a whole rule at once.",
            "3. **`word_references.html`** has the reason for every change side by side.",
            "",
        ]
    else:
        lines += [
            "No corrections were needed, so no tracked-changes document was written.",
            "See **`word_references.html`** for the checks that ran.",
            "",
        ]

    for group, heading in (
        (errors, "Problems that need a human"),
        (warnings, "Warnings"),
        (notes, "Notes"),
    ):
        if not group:
            continue
        lines += [f"## {heading} ({len(group)})", ""]
        for finding in group:
            where = f" (reference [{finding.line}])" if finding.line else ""
            lines.append(f"- **`{finding.check_id}`**{where} — {finding.message}")
        lines.append("")

    lines += ["## External authorities", "", STATUS.summary_line(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
