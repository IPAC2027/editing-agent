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
* every whole-reference reformat must pass :func:`jacow_formatter.check_rewrite` (via :mod:`src.references`),
  which compares the rewrite to the original and rejects it if a number, DOI,
  word or capital went missing.  That check is what stops the two defects seen
  on the sample corpus — ``Poincaré`` lowercased to ``poincaré`` and a doubled
  comma at ``pp. 611-632,,`` — from ever reaching an editor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.desk.files import relative_to_paper, write_text
from src.checks.reference_list_checks import run_all
from src.edits import Tier
from src.lookup_status import STATUS
from src.models import Finding, Severity
from src.output.word_report import write_word_reference_report
from src.parser.word_parser import parse_word
from src.references import screen_reference


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
        corrections: list | None = None,
    ) -> None:
        self.paper_id = paper_id
        self.out_dir = out_dir
        self.report_path = report_path
        self.total_refs = total_refs
        self.findings = findings
        self.tracked_docx = tracked_docx
        self.revisions = revisions
        self.skipped = skipped
        self.corrections = corrections or []


def prescreen_word(folder: Path) -> WordPrescreenResult:
    """Screen a Word submission and write tracked changes plus a report."""
    STATUS.reset()

    doc_path = _find_word_doc(folder)
    parsed = parse_word(doc_path)
    findings = run_all(parsed)

    # Body text and reference forms, shared with the LaTeX path.
    from src.checks import body_checks
    try:
        body, abstract = body_checks.word_paragraphs(doc_path)
    except Exception:  # noqa: BLE001 — an unreadable body must not stop the reference checks
        body, abstract = [], None
    findings.extend(body_checks.check_body_text(body, abstract))

    # Title, author and unit checks — LaTeX papers had these, Word papers did not.
    from src.checks import word_front_checks
    try:
        findings.extend(word_front_checks.run_all(doc_path))
    except Exception:  # noqa: BLE001 — never let these block the reference checks
        pass
    # Unpublished/submitted reference forms are corrected by the formatter
    # itself below, so body_checks.check_reference_forms is not run here.

    # The same PDF checks a LaTeX submission gets: the Word path previously
    # checked the reference list only.
    from src.checks.pdf_checks import find_author_pdf, run_pdf_checks
    author_pdf = find_author_pdf(folder)
    if author_pdf is not None:
        findings.extend(run_pdf_checks(author_pdf))

    out_dir = folder / "aiagent_prescreen"
    out_dir.mkdir(parents=True, exist_ok=True)

    refs_before: list[tuple[int, str]] = []
    refs_after: list[tuple[int, str]] = []
    findings_by_ref: dict[int, list] = {}
    rewrites: list = []
    corrections: list[dict] = []
    rejected_rewrites = 0

    from src.output.docx_tracked import ParagraphRewrite

    for ref in parsed.references:
        ref_findings = [f for f in findings if f.line == ref.n]

        # One engine for Word and LaTeX: the formatter formats, looks up and
        # verifies; the adapter decides the tier (src/references.py).
        result = screen_reference(ref.raw_text, label=f"Reference [{ref.n}]", line=ref.n)
        fix_findings = list(result.findings)
        corrected = ref.raw_text
        if result.after is not None and result.tier is not None:
            corrected = result.after
            fix_findings.append(Finding(
                check_id="FMT-REF-01" if result.tier is Tier.SUGGEST else "FMT-REF-02",
                severity=Severity.INFO, line=ref.n, message=result.message,
                original=ref.raw_text[:200], suggested=corrected[:200],
                auto_fixed=result.tier is Tier.AUTO,
            ))
        elif any(f.check_id == "FMT-REF-03" for f in result.findings):
            rejected_rewrites += 1

        refs_before.append((ref.n, ref.raw_text))
        refs_after.append((ref.n, corrected))
        findings_by_ref.setdefault(ref.n, [])
        findings_by_ref[ref.n].extend(ref_findings)
        findings_by_ref[ref.n].extend(fix_findings)

        if corrected.strip() == ref.raw_text.strip():
            continue

        more: list[dict] = []
        split = None
        if ref.paragraph_count == 2 and ref.paragraph_text:
            split = _split_link_paragraph(ref, corrected)
            if split is not None:
                paragraph_after, more = split
        if ref.paragraph_index < 0 or not ref.paragraph_text or (
                ref.paragraph_count != 1 and split is None):
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
        if split is None:
            paragraph_after = _rebuild_paragraph(ref.paragraph_text, ref.raw_text, corrected)
        if paragraph_after is None or (paragraph_after == ref.paragraph_text and not more):
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

        checks = ["FMT-REF-02"] if result.tier is Tier.AUTO else ["FMT-REF-01"]
        # Same tiering as the LaTeX side: presentation is applied, a
        # whole-reference rewrite is offered.  This is what lets an editor make
        # every decision at the desk and receive a Word file containing only
        # what they accepted.
        tier = "auto" if result.tier is Tier.AUTO else "suggest"
        corrections.append({
            "id": f"W{len(corrections) + 1:03d}",
            "tier": tier,
            # Name the correction after its biggest component: a whole-reference
            # reformat is what the editor is really being asked about, even when
            # a DOI fix rides along with it.
            "check_id": ("FMT-REF-01" if "FMT-REF-01" in checks
                         else (checks[0] if checks else "FMT-REF-01")),
            "checks": checks,
            "reference": ref.n,
            "paragraph_index": ref.paragraph_index,
            "before": ref.paragraph_text,
            "after": paragraph_after,
            "shown_before": ref.raw_text,
            "shown_after": corrected,
            "message": result.message or f"Reference [{ref.n}] reformatted to JACoW style.",
            "added_from": result.added_from,
            "integrity": result.integrity,
            # Further paragraphs the same correction rewrites (a link line).
            "more": more,
        })
        if paragraph_after != ref.paragraph_text:
            rewrites.append(ParagraphRewrite(
                paragraph_index=ref.paragraph_index,
                before=ref.paragraph_text,
                after=paragraph_after,
                author=f"JACoW prescreen ({', '.join(checks)})",
                note="; ".join(f.message for f in fix_findings),
            ))
        for extra in more:
            rewrites.append(ParagraphRewrite(
                paragraph_index=extra["paragraph_index"], before=extra["before"],
                after=extra["after"], author=f"JACoW prescreen ({', '.join(checks)})",
            ))

    # --- Main text: corrections as tracked changes -------------------
    # Each fix is its own correction (decided on the desk); the fixes in one
    # paragraph are combined into one rewrite of that paragraph.
    from src.autofix.word_body_fixes import apply_fixes, body_fixes
    try:
        text_fixes, text_findings, para_text = body_fixes(doc_path)
    except Exception:  # noqa: BLE001 — never let the main text block the references
        text_fixes, text_findings, para_text = [], [], {}
    findings.extend(text_findings)
    by_paragraph: dict[int, list] = {}
    for fix in text_fixes:
        by_paragraph.setdefault(fix.paragraph_index, []).append(fix)
        before = para_text[fix.paragraph_index]
        context_start = max(0, fix.start - 30)
        corrections.append({
            "id": f"W{len(corrections) + 1:03d}",
            "tier": fix.tier,
            "check_id": fix.check_id,
            "checks": [fix.check_id],
            "reference": None,
            "paragraph_index": fix.paragraph_index,
            "before": before,
            "after": apply_fixes(before, [fix]),
            "spans": [{"start": fix.start, "end": fix.end, "after": fix.after}],
            "shown_before": ("…" if context_start else "") + before[context_start:fix.end + 30],
            "shown_after": ("…" if context_start else "")
            + before[context_start:fix.start] + fix.after + before[fix.end:fix.end + 30],
            "message": fix.message,
            "more": [],
        })
    for index, group in by_paragraph.items():
        before = para_text[index]
        rewrites.append(ParagraphRewrite(
            paragraph_index=index, before=before, after=apply_fixes(before, group),
            author=f"JACoW prescreen ({', '.join(sorted({f.check_id for f in group}))})",
        ))

    # --- Layout: paragraph and heading formatting (tracked) ------------
    from src.autofix.word_format_fixes import format_fixes
    from src.checks.docx_audit import audit_findings
    try:
        layout_fixes, layout_findings = format_fixes(doc_path)
    except Exception:  # noqa: BLE001
        layout_fixes, layout_findings = [], []
    try:
        layout_findings += audit_findings(doc_path)
    except Exception:  # noqa: BLE001
        pass
    run_in = [f for f in layout_findings if f.check_id == "WORD-HEAD-04"]
    if run_in:
        # One note for all third-level headings on their own line.
        layout_findings = [f for f in layout_findings if f.check_id != "WORD-HEAD-04"]
        names = ", ".join(f"'{f.original}'" for f in run_in[:6])
        layout_findings.append(type(run_in[0])(
            check_id="WORD-HEAD-04", severity=run_in[0].severity,
            message=(f"{len(run_in)} third-level heading(s) are on a line of their own ({names}). "
                     "JACoW third-level headings are 10 pt bold and run into the paragraph "
                     "text, followed by an em space."), original=names))
    findings.extend(layout_findings)
    formats: list[tuple[int, dict, str]] = []
    for fix in layout_fixes:
        corrections.append({
            "id": f"W{len(corrections) + 1:03d}",
            "tier": fix.tier,
            "check_id": fix.check_id,
            "checks": [fix.check_id],
            "reference": None,
            "paragraph_index": fix.paragraph_index,
            "before": para_text.get(fix.paragraph_index, ""),
            "after": para_text.get(fix.paragraph_index, ""),
            "format": fix.as_dict(),
            "shown_before": para_text.get(fix.paragraph_index, "")[:120],
            "shown_after": "(formatting) " + fix.message,
            "message": fix.message,
            "more": [],
        })
        formats.append((fix.paragraph_index, fix.as_dict(), f"JACoW prescreen ({fix.check_id})"))

    # --- Word tracked changes ------------------------------------------
    tracked_name: str | None = None
    revisions = 0
    skipped: list = []
    if rewrites or formats:
        from src.output.docx_tracked import write_tracked_docx

        tracked_path = out_dir / f"{doc_path.stem}_tracked.docx"
        try:
            _path, revision_blocks, skipped = write_tracked_docx(
                doc_path, tracked_path, rewrites, formats,
            )
            # Report *corrections*, not revision blocks: one correction can be
            # several w:ins/w:del pairs, and an editor counts references.
            # A reference whose link line was also rewritten is still one
            # correction, so count references, not paragraphs.
            skipped_index = {r.paragraph_index for r in skipped}
            revisions = sum(
                1 for c in corrections
                if c.get("paragraph_index", -1) >= 0
                and c["paragraph_index"] not in skipped_index
                and not any(m["paragraph_index"] in skipped_index for m in c.get("more") or [])
            )
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
                f"{revisions} correction(s) written as tracked changes in "
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
            check_id="FMT-REF-03",
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

    _write_word_report_json(
        out_dir / "report.json",
        parsed,
        doc_path,
        all_findings,
        corrections,
        tracked_name,
        revisions,
    )
    (out_dir / "word_edits.json").write_text(
        json.dumps({"schema_version": 1, "document": doc_path.name,
                    "corrections": corrections}, indent=2),
        encoding="utf-8",
    )

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
        corrections=corrections,
    )


_CONTAINER_STOP_RE = re.compile(
    r"^(?:vol\.?|volume|no\.?|nos\.?|iss\.?|issue|pp?\.?|pages?|art(?:icle)?\.?|"
    r"e?id|doi|https?:|arxiv|in\s+press|\(?(?:19|20)\d{2}\)?$)",
    re.IGNORECASE,
)


_TRAILING_LINK_RE = re.compile(r"\s*((?:doi:|https?://)\S+)\s*$", re.IGNORECASE)


def _split_link_paragraph(ref, corrected: str) -> tuple[str, list[dict]] | None:
    """Write a reference whose link sits on its own line as two revisions.

    One test paper put every reference's DOI or URL in the paragraph below it.  The
    corrected text is split at its trailing link: the entry paragraph gets
    the text, the link paragraph gets the link (e.g. https://doi.org/… ->
    doi:…).  Returns the first paragraph's new text and the extra rewrite,
    or None when the split is not clean.
    """
    if len(ref.continuations) != 1:
        return None
    link_index, link_text = ref.continuations[0]
    link_clean = link_text.strip()
    if not re.match(r"(?:doi:|https?://|www\.)", link_clean, re.IGNORECASE):
        return None
    match = _TRAILING_LINK_RE.search(corrected)
    if not match:
        return None
    head, tail = corrected[:match.start()].rstrip(), match.group(1)
    if tail.endswith(".") and not link_clean.endswith("."):
        tail = tail[:-1]          # a full stop after a URL is not part of it
    raw_first = ref.raw_text[: len(ref.raw_text) - len(link_clean)].rstrip()
    if not ref.raw_text.endswith(link_clean):
        return None
    first_after = _rebuild_paragraph(ref.paragraph_text, raw_first, head)
    if first_after is None:
        return None
    lead = link_text[: len(link_text) - len(link_text.lstrip())]
    trail = link_text[len(link_text.rstrip()):]
    more = []
    if tail != link_clean:
        more.append({"paragraph_index": link_index, "before": link_text,
                     "after": f"{lead}{tail}{trail}"})
    if first_after == ref.paragraph_text and not more:
        return None
    return first_after, more


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


def _write_word_report_json(
    path: Path,
    parsed,
    doc_path: Path,
    findings: list,
    corrections: list[dict],
    tracked_name: str | None,
    revisions: int,
) -> None:
    """Write the same ``report.json`` shape the LaTeX path writes.

    Without this a Word submission was invisible to the review desk and to the
    worklist: both read ``report.json`` to decide whether a paper has been
    prepared, and the Word path only ever wrote Markdown and HTML.
    """
    from datetime import datetime, timezone

    auto = [c for c in corrections if c["tier"] == "auto"]
    suggested = [c for c in corrections if c["tier"] != "auto"]
    from src.checks.title_authors import front_matter_of

    try:
        front_matter = front_matter_of(doc_path).model_dump()
    except Exception:  # noqa: BLE001 — the comparison is optional; the report is not
        front_matter = None
    payload = {
        "schema_version": 2,
        "paper_id": parsed.paper_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": relative_to_paper(doc_path, path.parent.parent),
        "title": parsed.title,
        "authors": front_matter["authors"] if front_matter else [],
        "front_matter": front_matter,
        "build": (
            f"{revisions} correction(s) written as tracked changes"
            if tracked_name else "no corrections needed"
        ),
        "findings": [f.model_dump() for f in findings],
        "edits": corrections,
        "summary": {
            "errors": sum(1 for f in findings if f.severity is Severity.ERROR),
            "warnings": sum(1 for f in findings if f.severity is Severity.WARNING),
            "notes": sum(1 for f in findings if f.severity is Severity.INFO),
            "edits": {
                "applied_automatically": len(auto),
                "awaiting_decision": len(suggested),
                "total": len(corrections),
            },
        },
        "lookups": STATUS.report(),
        "references_checked": len(parsed.references),
        "tracked_document": tracked_name,
    }
    write_text(path, json.dumps(payload, indent=2, default=str))
