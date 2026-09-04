"""Report writers — one source of truth for every number they print.

The previous version derived its counts from a boolean on each ``Finding``
(``auto_fixed``) that the fix functions set about themselves.  Nothing tied that
flag to the file on disk, so ``report.md`` could announce seven auto-fixes while
``changes.html`` said "No safe auto-fixes were applicable", ``changes.patch``
was empty, and the two SHA-256 hashes in ``repair_plan.json`` matched.

Every count here now comes from the :class:`~src.edits.EditSet` — the same
object that produced the patches, the git history and the edited file — so the
outputs cannot disagree.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.edits import EditSet
from src.lookup_status import STATUS
from src.models import Paper, Severity


def write_report(
    paper: Paper,
    out_dir: Path,
    *,
    editset: EditSet | None = None,
    build_status: str = "not compiled",
    bib_editset: EditSet | None = None,
) -> None:
    """Write ``report.json``, ``report.md`` and ``repair_plan.json``."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _write_json(paper, out_dir / "report.json", generated_at, editset, build_status)
    _write_markdown(paper, out_dir / "report.md", generated_at, editset, build_status,
                    bib_editset)
    _write_repair_plan(paper, out_dir / "repair_plan.json", generated_at, editset,
                       build_status)


def _tally(paper: Paper) -> dict[str, int]:
    return {
        "errors": sum(1 for f in paper.findings if f.severity is Severity.ERROR),
        "warnings": sum(1 for f in paper.findings if f.severity is Severity.WARNING),
        "notes": sum(1 for f in paper.findings if f.severity is Severity.INFO),
    }


def _edit_tally(editset: EditSet | None) -> dict[str, int]:
    if editset is None:
        return {"applied_automatically": 0, "awaiting_decision": 0, "total": 0}
    return {
        "applied_automatically": len(editset.auto),
        "awaiting_decision": len(editset.suggested),
        "total": len(editset.edits),
    }


def _write_json(
    paper: Paper,
    path: Path,
    generated_at: str,
    editset: EditSet | None,
    build_status: str,
) -> None:
    data = {
        "schema_version": 2,
        "paper_id": paper.paper_id,
        "generated_at": generated_at,
        "source": str(paper.source_path),
        "title": paper.title,
        "authors": paper.authors,
        "build": build_status,
        "findings": [f.model_dump() for f in paper.findings],
        "edits": [e.model_dump() for e in (editset.edits if editset else [])],
        "summary": {**_tally(paper), "edits": _edit_tally(editset)},
        "lookups": STATUS.report(),
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _write_markdown(
    paper: Paper,
    path: Path,
    generated_at: str,
    editset: EditSet | None,
    build_status: str,
    bib_editset: EditSet | None,
) -> None:
    tally = _tally(paper)
    edits = _edit_tally(editset)
    errors = [f for f in paper.findings if f.severity is Severity.ERROR]
    warnings = [f for f in paper.findings if f.severity is Severity.WARNING]
    notes = [f for f in paper.findings if f.severity is Severity.INFO]

    status = "NEEDS WORK" if errors else ("REVIEW" if warnings or edits["awaiting_decision"] else "CLEAN")

    lines = [
        f"# Pre-screen — {paper.paper_id}",
        "",
        f"**{status}** · {generated_at} · {build_status}",
        "",
        f"- **{edits['applied_automatically']}** change(s) applied automatically "
        f"(safe, reversible, already in `{paper.paper_id}_edited.tex`)",
        f"- **{edits['awaiting_decision']}** change(s) awaiting your decision "
        f"(open `review.html`)",
        f"- **{tally['errors']}** problem(s) the agent will not touch",
        f"- **{tally['warnings']}** style point(s), **{tally['notes']}** note(s)",
        "",
        f"Title: {paper.title or '(not parsed)'}",
        "",
        "## What to do",
        "",
        "1. Open **`review.html`** — one accept/reject decision per proposed change.",
        "2. Save your decisions, then apply them:",
        "",
        "   ```",
        "   uv run python main.py apply <this folder> --decisions review_decisions.json",
        "   ```",
        "",
        f"   or take just the automatic changes from `{paper.paper_id}_edited.tex`, "
        "which needs no review.",
        "3. Every edit is also a single commit in **`history/`** "
        "(`git log --oneline`, `git revert <sha>`) and a single patch in "
        "**`edits/`**.",
        "",
    ]

    if editset and editset.auto:
        lines += [
            f"## Applied automatically ({len(editset.auto)})",
            "",
            "| Edit | Check | Line | Change |",
            "|------|-------|------|--------|",
        ]
        for edit in editset.auto:
            lines.append(
                f"| `{edit.id}` | `{edit.check_id}` | {edit.line} | "
                f"`{_cell(edit.before)}` → `{_cell(edit.after)}` |"
            )
        lines.append("")

    if editset and editset.suggested:
        lines += [
            f"## Awaiting your decision ({len(editset.suggested)})",
            "",
        ]
        for edit in editset.suggested:
            lines += [
                f"### `{edit.id}` `{edit.check_id}` — line {edit.line}",
                "",
                edit.message,
                "",
                f"- was: `{_cell(edit.before, 300)}`",
                f"- now: `{_cell(edit.after, 300)}`",
                f"- rule: {edit.rule or '(none recorded)'}",
                f"- accept with: `--accept {edit.id}`",
                "",
            ]

    if bib_editset and bib_editset.edits:
        lines += [
            f"## BibTeX file ({len(bib_editset.edits)} edit(s))",
            "",
            "| Edit | Check | Change |",
            "|------|-------|--------|",
        ]
        for edit in bib_editset.edits:
            lines.append(
                f"| `{edit.id}` | `{edit.check_id}` | "
                f"`{_cell(edit.before)}` → `{_cell(edit.after)}` |"
            )
        lines.append("")

    for group, heading in (
        (errors, "Problems that need a human"),
        (warnings, "Style points"),
        (notes, "Notes, and checks that did not run"),
    ):
        if not group:
            continue
        lines += [f"## {heading} ({len(group)})", ""]
        for finding in group:
            where = f" (line {finding.line})" if finding.line else ""
            lines.append(f"- **`{finding.check_id}`**{where} — {finding.message}")
            if finding.original:
                lines.append(f"  - in: `{_cell(finding.original, 200)}`")
            if finding.suggested:
                lines.append(f"  - suggested: `{_cell(finding.suggested, 200)}`")
        lines.append("")

    lines += [
        "## External authorities",
        "",
        STATUS.summary_line(),
        "",
    ]
    for service in STATUS.report():
        state = (
            "reachable" if service["reachable"]
            else ("UNREACHABLE" if service["attempted"] else "not needed")
        )
        detail = f" — {service['last_error']}" if service["last_error"] and not service["reachable"] else ""
        lines.append(f"- `{service['service']}`: {state}{detail}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_repair_plan(
    paper: Paper,
    path: Path,
    generated_at: str,
    editset: EditSet | None,
    build_status: str,
) -> None:
    """Machine-readable plan, now generated from the EditSet itself."""
    plan = {
        "schema_version": 2,
        "paper_id": paper.paper_id,
        "source": str(paper.source_path),
        "generated_at": generated_at,
        "source_sha256": editset.source_sha256 if editset else None,
        "validation": {"status": build_status},
        "lookups": STATUS.report(),
        "repairs": [
            {
                "id": edit.id,
                "check_id": edit.check_id,
                "tier": edit.tier.value,
                "confidence": edit.confidence.value,
                "line": edit.line,
                "span": [edit.start, edit.end],
                "before": edit.before,
                "after": edit.after,
                "reason": edit.message,
                "rule": edit.rule,
                "evidence": edit.evidence.model_dump(),
                "reversible": edit.reversible,
                "patch": f"edits/{edit.id}.patch",
                "status": (
                    "applied" if edit.tier.value == "auto" else "pending_editor_review"
                ),
            }
            for edit in (editset.edits if editset else [])
        ],
    }
    path.write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")


def _cell(text: str | None, width: int = 90) -> str:
    if not text:
        return ""
    flat = text.replace("\n", "↵ ").replace("|", "\\|").replace("`", "'")
    flat = " ".join(flat.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"
