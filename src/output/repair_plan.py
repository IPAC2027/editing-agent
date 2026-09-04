"""Superseded — ``repair_plan.json`` is now written by :mod:`src.output.report`.

The plan is generated from the :class:`~src.edits.EditSet` rather than from a
per-finding ``auto_fixed`` flag, so it can no longer disagree with the diff, the
patches or the file on disk.  Kept for its tests; not used by the pipeline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import Finding, Paper


def write_repair_plan(
    paper: Paper,
    out_dir: Path,
    findings: list[Finding],
    *,
    original_source: str,
    edited_source: str,
) -> Path:
    """Write a machine-readable plan linking every repair to its evidence."""
    repairs = []
    for index, finding in enumerate(
        (finding for finding in findings if finding.auto_fixed), start=1,
    ):
        repairs.append({
            "id": f"repair-{index:03d}",
            "check_id": finding.check_id,
            "line": finding.line,
            "reason": finding.message,
            "original": finding.original,
            "suggested": finding.suggested,
            "status": "pending_editor_review",
        })

    plan = {
        "schema_version": 1,
        "paper_id": paper.paper_id,
        "source": str(paper.source_path),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sha256": hashlib.sha256(original_source.encode("utf-8")).hexdigest(),
        "edited_source_sha256": hashlib.sha256(edited_source.encode("utf-8")).hexdigest(),
        "validation": _validation_summary(paper),
        "repairs": repairs,
    }
    path = out_dir / "repair_plan.json"
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return path


def _validation_summary(paper: Paper) -> dict[str, str]:
    for finding in reversed(paper.findings):
        if finding.check_id == "BUILD-OK":
            return {"status": "passed", "detail": finding.message}
        if finding.check_id == "BUILD-FAIL":
            return {"status": "failed", "detail": finding.message}
    return {
        "status": "not_run",
        "detail": "LaTeX compilation was not requested for this prescreen run.",
    }
