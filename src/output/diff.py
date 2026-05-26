"""Unified diff writer."""

from __future__ import annotations

import difflib
from pathlib import Path


def write_diff(original: str, modified: str, filename: str, out_dir: Path) -> None:
    """Write a unified diff of *original* vs *modified* to ``changes.patch``."""
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    (out_dir / "changes.patch").write_text("".join(diff_lines), encoding="utf-8")
