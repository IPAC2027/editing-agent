"""Diff writers: unified patch + side-by-side HTML for editor review."""

from __future__ import annotations

import difflib
from pathlib import Path

_HTML_STYLE = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; background: #f5f5f5; }
  h1   { background: #2c3e50; color: #fff; margin: 0; padding: 12px 20px;
         font-size: 1.1rem; }
  .meta { background: #34495e; color: #ecf0f1; padding: 6px 20px;
          font-size: 0.85rem; }
  .legend { padding: 8px 20px; font-size: 0.85rem; background: #ecf0f1; }
  .legend span { display: inline-block; padding: 2px 8px; border-radius: 3px;
                 margin-right: 12px; }
  .add  { background: #d4edda; }
  .del  { background: #f8d7da; }
  .chg  { background: #fff3cd; }
  /* Override difflib default table styles */
  table.diff { font-family: 'SFMono-Regular', Consolas, monospace;
               font-size: 0.82rem; width: 100%; border-collapse: collapse; }
  table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                  word-break: break-all; }
  table.diff th { background: #2c3e50; color: #fff; padding: 6px;
                  text-align: center; }
  .diff_header { background: #bdc3c7 !important; }
  .diff_next   { background: #bdc3c7; }
  td.diff_add  { background: #d4edda; }
  td.diff_chg  { background: #fff3cd; }
  td.diff_sub  { background: #f8d7da; }
  .lineno { color: #888; text-align: right; min-width: 3em; user-select: none; }
</style>
"""


def write_diff(original: str, modified: str, filename: str, out_dir: Path) -> None:
    """Write ``changes.patch`` (unified) and ``changes.html`` (side-by-side)."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    # --- unified patch ---
    diff_lines = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
    (out_dir / "changes.patch").write_text("".join(diff_lines), encoding="utf-8")

    # --- side-by-side HTML ---
    if original == modified:
        html = _no_changes_html(filename)
    else:
        differ = difflib.HtmlDiff(tabsize=4, wrapcolumn=90)
        table = differ.make_table(
            orig_lines, mod_lines,
            fromdesc=f"Original  —  {filename}",
            todesc=f"Edited (auto-fixes applied)  —  {filename}",
            context=True,
            numlines=3,
        )
        html = _wrap_html(table, filename)

    (out_dir / "changes.html").write_text(html, encoding="utf-8")


def _wrap_html(table: str, filename: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Agent Edits — {filename}</title>
  {_HTML_STYLE}
</head>
<body>
  <h1>AI Agent Edits — {filename}</h1>
  <div class="meta">
    Open this file in any browser. Yellow = changed, green = added, red = removed.
    Use <b>changes.patch</b> to apply with <code>patch</code> or review in any diff tool.
  </div>
  <div class="legend">
    <span class="add">Added / fixed</span>
    <span class="del">Removed</span>
    <span class="chg">Changed</span>
  </div>
  {table}
</body>
</html>
"""


def _no_changes_html(filename: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>No Changes — {filename}</title>{_HTML_STYLE}</head>
<body>
  <h1>No Changes — {filename}</h1>
  <p style="padding:20px;font-size:1rem;">
    No safe auto-fixes were applicable. See <code>report.md</code> for findings
    that require human attention.
  </p>
</body>
</html>
"""
