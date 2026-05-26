"""Report writers: report.json and report.md."""

from __future__ import annotations

import json
from pathlib import Path

from src.models import Paper, Severity


def write_report(paper: Paper, out_dir: Path) -> None:
    """Write ``report.json`` and ``report.md`` into *out_dir*."""
    _write_json(paper, out_dir / "report.json")
    _write_markdown(paper, out_dir / "report.md")


def _write_json(paper: Paper, path: Path) -> None:
    data = {
        "paper_id": paper.paper_id,
        "source": str(paper.source_path),
        "title": paper.title,
        "findings": [f.model_dump() for f in paper.findings],
        "summary": {
            "errors": sum(1 for f in paper.findings if f.severity == Severity.ERROR),
            "warnings": sum(1 for f in paper.findings if f.severity == Severity.WARNING),
            "info": sum(1 for f in paper.findings if f.severity == Severity.INFO),
            "auto_fixed": sum(1 for f in paper.findings if f.auto_fixed),
        },
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_markdown(paper: Paper, path: Path) -> None:
    errors = [f for f in paper.findings if f.severity == Severity.ERROR]
    warnings = [f for f in paper.findings if f.severity == Severity.WARNING]
    infos = [f for f in paper.findings if f.severity == Severity.INFO]
    auto_fixed = [f for f in paper.findings if f.auto_fixed]

    icon = "🔴" if errors else ("🟡" if warnings else "🟢")

    lines = [
        f"# Pre-screen Report — {paper.paper_id}  {icon}",
        "",
        f"**Title:** {paper.title or '(unknown)'}",
        "",
        f"| Errors | Warnings | Info | Auto-fixed |",
        f"|--------|----------|------|------------|",
        f"| {len(errors)} | {len(warnings)} | {len(infos)} | {len(auto_fixed)} |",
        "",
    ]

    for group, heading in [(errors, "Errors"), (warnings, "Warnings"), (infos, "Info")]:
        if not group:
            continue
        lines += [f"## {heading}", ""]
        for f in group:
            loc = f" _(line {f.line})_" if f.line else ""
            lines.append(f"### `{f.check_id}`{loc}")
            lines.append(f"{f.message}")
            if f.original:
                lines.append(f"\n**Original:** `{f.original}`")
            if f.suggested:
                lines.append(f"\n**Suggested:** `{f.suggested}`")
            if f.auto_fixed:
                lines.append("\n> ✅ Auto-fixed in `_edited.tex`")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
