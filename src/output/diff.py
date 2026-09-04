"""Diff writers: unified patch and annotated side-by-side HTML."""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from itertools import zip_longest
from pathlib import Path

from src.models import Finding

_CONTEXT_LINES = 3


@dataclass(frozen=True)
class _Repair:
    id: str
    finding: Finding

    @property
    def reason(self) -> str:
        return f"{self.finding.check_id}: {self.finding.message}"

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
  table.diff { font-family: 'SFMono-Regular', Consolas, monospace;
               font-size: 0.82rem; width: 100%; border-collapse: collapse; }
  table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                  word-break: break-all; }
  table.diff th { background: #2c3e50; color: #fff; padding: 6px;
                  text-align: center; }
  .lineno { color: #888; text-align: right; min-width: 3em; user-select: none; }
  .diff-add { background: #d4edda; }
  .diff-del { background: #f8d7da; }
  .diff-chg { background: #fff3cd; }
  .diff-skip { background: #e9ecef; color: #6c757d; font-style: italic;
               text-align: center; }
  .diff-highlight { cursor: help; position: relative; }
  .diff-highlight:hover::after {
    content: attr(data-reason); position: absolute; z-index: 1; left: 0; top: 1.5em;
    width: min(34rem, 80vw); padding: 7px 9px; border-radius: 4px;
    background: #2c3e50; color: #fff; font-family: -apple-system, BlinkMacSystemFont,
    'Segoe UI', sans-serif; font-size: 0.78rem; line-height: 1.35; white-space: normal;
    box-shadow: 0 2px 8px rgba(0, 0, 0, .25);
  }
  .review { margin: 16px 20px; padding: 16px; background: #fff; border-radius: 6px;
            box-shadow: 0 1px 4px rgba(0, 0, 0, .12); }
  .review h2 { margin: 0 0 8px; color: #2c3e50; font-size: 1rem; }
  .review p { margin: 0 0 12px; font-size: .88rem; color: #566573; }
  .review-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
  .review button { border: 0; border-radius: 4px; padding: 6px 10px; cursor: pointer;
                   color: #fff; background: #2980b9; font-size: .82rem; }
  .review button.reject { background: #c0392b; }
  .review button.download { background: #566573; }
  .repair { border-top: 1px solid #e5e7e9; padding: 10px 0; }
  .repair:first-of-type { border-top: 0; }
  .repair-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .repair code { background: #ecf0f1; padding: 1px 4px; border-radius: 3px; }
  .repair-detail { margin: 5px 0; font-size: .84rem; }
  .repair-status { font-size: .78rem; color: #566573; }
  .repair.accepted { border-left: 3px solid #27ae60; padding-left: 8px; }
  .repair.rejected { border-left: 3px solid #c0392b; padding-left: 8px; opacity: .68; }
  .diff-highlight.review-accepted { outline: 2px solid #27ae60; }
  .diff-highlight.review-rejected { opacity: .45; text-decoration: line-through; }
</style>
"""


def write_diff(
    original: str,
    modified: str,
    filename: str,
    out_dir: Path,
    findings: Iterable[Finding] = (),
) -> None:
    """Write a unified patch and hover-annotated side-by-side HTML diff."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    repairs = _repairs(findings)

    diff_lines = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
    (out_dir / "changes.patch").write_text("".join(diff_lines), encoding="utf-8")

    if original == modified:
        html = _no_changes_html(filename)
    else:
        original_reasons, modified_reasons, fallback_reasons = _reason_maps(
            original, modified, repairs,
        )
        table = _make_table(
            orig_lines,
            mod_lines,
            original_reasons,
            modified_reasons,
            fallback_reasons,
            filename,
        )
        html = _wrap_html(table, filename, _review_panel(repairs))

    (out_dir / "changes.html").write_text(html, encoding="utf-8")


def _repairs(findings: Iterable[Finding]) -> list[_Repair]:
    return [
        _Repair(id=f"repair-{index:03d}", finding=finding)
        for index, finding in enumerate(
            (finding for finding in findings if finding.auto_fixed), start=1,
        )
    ]


def _reason_maps(
    original: str,
    modified: str,
    repairs: Iterable[_Repair],
) -> tuple[dict[int, list[_Repair]], dict[int, list[_Repair]], list[_Repair]]:
    """Associate source lines with the auto-fix findings that changed them."""
    original_lines = original.splitlines()
    modified_lines = modified.splitlines()
    original_reasons: dict[int, list[_Repair]] = {}
    modified_reasons: dict[int, list[_Repair]] = {}
    fallback_reasons: list[_Repair] = []

    for repair in repairs:
        finding = repair.finding
        original_hits: set[int] = set()
        modified_hits: set[int] = set()

        if finding.line and 1 <= finding.line <= len(original_lines):
            original_hits.add(finding.line - 1)
        original_hits.update(_find_fragment_lines(original, finding.original))
        modified_hits.update(_find_fragment_lines(modified, finding.suggested))

        if not original_hits and not modified_hits:
            fallback_reasons.append(repair)
            continue
        _add_repairs(original_reasons, original_hits, repair)
        _add_repairs(modified_reasons, modified_hits, repair)

    matcher = difflib.SequenceMatcher(a=original_lines, b=modified_lines)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            for old_index, new_index in zip(range(old_start, old_end), range(new_start, new_end)):
                _add_repairs(modified_reasons, {new_index}, *_repairs_at(original_reasons, old_index))
            continue
        for old_index in range(old_start, old_end):
            _add_repairs(modified_reasons, range(new_start, new_end), *_repairs_at(original_reasons, old_index))
        for new_index in range(new_start, new_end):
            _add_repairs(original_reasons, range(old_start, old_end), *_repairs_at(modified_reasons, new_index))

    return original_reasons, modified_reasons, _unique_repairs(fallback_reasons)


def _find_fragment_lines(source: str, fragment: str | None) -> set[int]:
    if not fragment:
        return set()
    start = 0
    lines: set[int] = set()
    while True:
        offset = source.find(fragment, start)
        if offset < 0:
            return lines
        first_line = source.count("\n", 0, offset)
        lines.update(range(first_line, first_line + fragment.count("\n") + 1))
        start = offset + max(1, len(fragment))


def _add_repairs(
    mapping: dict[int, list[_Repair]],
    indexes: Iterable[int],
    *repairs: _Repair,
) -> None:
    for index in indexes:
        if not repairs:
            continue
        existing = mapping.setdefault(index, [])
        for repair in repairs:
            if repair not in existing:
                existing.append(repair)


def _repairs_at(mapping: dict[int, list[_Repair]], index: int) -> list[_Repair]:
    return mapping.get(index, [])


def _make_table(
    original_lines: list[str],
    modified_lines: list[str],
    original_reasons: dict[int, list[_Repair]],
    modified_reasons: dict[int, list[_Repair]],
    fallback_reasons: list[_Repair],
    filename: str,
) -> str:
    matcher = difflib.SequenceMatcher(a=original_lines, b=modified_lines)
    rows = [
        "<table class=\"diff\">",
        "<thead><tr><th colspan=\"2\">"
        f"Original — {escape(filename)}</th><th colspan=\"2\">"
        f"Edited (auto-fixes applied) — {escape(filename)}</th></tr></thead><tbody>",
    ]
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            rows.extend(_equal_rows(original_lines, old_start, old_end, new_start, new_end))
            continue
        rows.extend(_changed_rows(
            tag,
            original_lines,
            modified_lines,
            old_start,
            old_end,
            new_start,
            new_end,
            original_reasons,
            modified_reasons,
            fallback_reasons,
        ))
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _equal_rows(
    original_lines: list[str],
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
) -> list[str]:
    length = old_end - old_start
    if length <= _CONTEXT_LINES * 2:
        indexes = list(range(length))
        return [_row(old_start + index, original_lines[old_start + index], new_start + index, original_lines[old_start + index]) for index in indexes]

    head = range(_CONTEXT_LINES)
    tail = range(length - _CONTEXT_LINES, length)
    rows = [_row(old_start + index, original_lines[old_start + index], new_start + index, original_lines[old_start + index]) for index in head]
    rows.append(
        f'<tr><td colspan="4" class="diff-skip">… {length - _CONTEXT_LINES * 2} unchanged lines …</td></tr>'
    )
    rows.extend(_row(old_start + index, original_lines[old_start + index], new_start + index, original_lines[old_start + index]) for index in tail)
    return rows


def _changed_rows(
    tag: str,
    original_lines: list[str],
    modified_lines: list[str],
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
    original_reasons: dict[int, list[_Repair]],
    modified_reasons: dict[int, list[_Repair]],
    fallback_reasons: list[_Repair],
) -> list[str]:
    rows: list[str] = []
    old_indexes = range(old_start, old_end)
    new_indexes = range(new_start, new_end)
    for old_index, new_index in zip_longest(old_indexes, new_indexes):
        old_line = original_lines[old_index] if old_index is not None else None
        new_line = modified_lines[new_index] if new_index is not None else None
        repairs = _combine_repairs(
            original_reasons.get(old_index, []) if old_index is not None else [],
            modified_reasons.get(new_index, []) if new_index is not None else [],
            fallback_reasons,
        )
        if old_line is not None and new_line is not None:
            old_text, new_text = _inline_change(old_line, new_line, repairs)
            rows.append(_row(old_index, old_text, new_index, new_text, raw_html=True))
        elif old_line is not None:
            rows.append(_row(old_index, _highlight(old_line, "diff-del", repairs), None, "", raw_html=True))
        elif new_line is not None:
            rows.append(_row(None, "", new_index, _highlight(new_line, "diff-add", repairs), raw_html=True))
    return rows


def _inline_change(old_line: str, new_line: str, repairs: list[_Repair]) -> tuple[str, str]:
    old_parts: list[str] = []
    new_parts: list[str] = []
    matcher = difflib.SequenceMatcher(a=old_line, b=new_line)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        old_part = old_line[old_start:old_end]
        new_part = new_line[new_start:new_end]
        if tag == "equal":
            old_parts.append(escape(old_part))
            new_parts.append(escape(new_part))
        elif tag == "replace":
            old_parts.append(_highlight(old_part, "diff-chg", repairs))
            new_parts.append(_highlight(new_part, "diff-chg", repairs))
        elif tag == "delete":
            old_parts.append(_highlight(old_part, "diff-del", repairs))
        elif tag == "insert":
            new_parts.append(_highlight(new_part, "diff-add", repairs))
    return "".join(old_parts), "".join(new_parts)


def _highlight(text: str, css_class: str, repairs: list[_Repair]) -> str:
    tooltip = " | ".join(repair.reason for repair in repairs) if repairs else "Automated source change; see report.md for details."
    escaped_tooltip = escape(tooltip, quote=True)
    escaped_text = escape(text.rstrip("\n"))
    repair_ids = " ".join(repair.id for repair in repairs)
    return (
        f'<span class="{css_class} diff-highlight" title="{escaped_tooltip}" '
        f'data-reason="{escaped_tooltip}" data-repairs="{repair_ids}">{escaped_text}</span>'
    )


def _combine_repairs(*repair_lists: list[_Repair]) -> list[_Repair]:
    return _unique_repairs(repair for repairs in repair_lists for repair in repairs)


def _unique_repairs(repairs: Iterable[_Repair]) -> list[_Repair]:
    result: list[_Repair] = []
    for repair in repairs:
        if repair not in result:
            result.append(repair)
    return result


def _row(
    old_index: int | None,
    old_text: str,
    new_index: int | None,
    new_text: str,
    *,
    raw_html: bool = False,
) -> str:
    old_content = old_text if raw_html else escape(old_text.rstrip("\n"))
    new_content = new_text if raw_html else escape(new_text.rstrip("\n"))
    old_number = str(old_index + 1) if old_index is not None else ""
    new_number = str(new_index + 1) if new_index is not None else ""
    return (
        "<tr>"
        f'<td class="lineno">{old_number}</td><td>{old_content}</td>'
        f'<td class="lineno">{new_number}</td><td>{new_content}</td>'
        "</tr>"
    )


def _review_panel(repairs: list[_Repair]) -> str:
    if not repairs:
        return ""
    items = []
    for repair in repairs:
        finding = repair.finding
        original = escape(finding.original or "(not recorded)")
        suggested = escape(finding.suggested or "(not recorded)")
        items.append(
            f'<div class="repair" data-repair-id="{repair.id}">'
            '<div class="repair-head">'
            f'<strong><code>{repair.id}</code> <code>{escape(finding.check_id)}</code></strong>'
            '<span class="repair-status">Pending review</span></div>'
            f'<p class="repair-detail">{escape(finding.message)}</p>'
            f'<p class="repair-detail"><b>Original:</b> <code>{original}</code><br>'
            f'<b>Proposed:</b> <code>{suggested}</code></p>'
            '<div class="review-actions">'
            f'<button type="button" data-decision="accepted" data-repair="{repair.id}">Accept</button>'
            f'<button type="button" class="reject" data-decision="rejected" data-repair="{repair.id}">Reject</button>'
            '</div></div>'
        )
    return (
        '<section class="review" id="repair-review" data-review-key="aiagent-repair-review">'
        '<h2>Editor review</h2>'
        '<p>Record decisions here, then download them as <code>review_decisions.json</code>. '
        'This page never changes the LaTeX source by itself.</p>'
        '<div class="review-actions">'
        '<button type="button" data-action="accept-all">Accept all</button>'
        '<button type="button" class="reject" data-action="reject-all">Reject all</button>'
        '<button type="button" class="download" data-action="download">Download decisions</button>'
        '</div>'
        + "".join(items)
        + '</section>'
    )


_REVIEW_SCRIPT = """
<script>
(() => {
  const panel = document.getElementById('repair-review');
  if (!panel) return;
  const storageKey = `${panel.dataset.reviewKey}:${location.pathname}`;
  let decisions = {};
  try { decisions = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch (_) {}

  const save = () => {
    try { localStorage.setItem(storageKey, JSON.stringify(decisions)); } catch (_) {}
  };
  const refresh = () => {
    document.querySelectorAll('[data-repair-id]').forEach((item) => {
      const state = decisions[item.dataset.repairId] || 'pending';
      item.classList.toggle('accepted', state === 'accepted');
      item.classList.toggle('rejected', state === 'rejected');
      item.querySelector('.repair-status').textContent = state === 'pending' ? 'Pending review' : state;
    });
    document.querySelectorAll('[data-repairs]').forEach((highlight) => {
      const states = highlight.dataset.repairs.split(' ').map((id) => decisions[id]);
      highlight.classList.toggle('review-accepted', states.includes('accepted'));
      highlight.classList.toggle('review-rejected', states.includes('rejected'));
    });
  };
  document.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    if (button.dataset.repair) {
      decisions[button.dataset.repair] = button.dataset.decision;
    } else if (button.dataset.action === 'accept-all' || button.dataset.action === 'reject-all') {
      const decision = button.dataset.action === 'accept-all' ? 'accepted' : 'rejected';
      document.querySelectorAll('[data-repair-id]').forEach((item) => { decisions[item.dataset.repairId] = decision; });
    } else if (button.dataset.action === 'download') {
      const payload = JSON.stringify({ generated_at: new Date().toISOString(), decisions }, null, 2);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
      link.download = 'review_decisions.json';
      link.click();
      URL.revokeObjectURL(link.href);
      return;
    } else {
      return;
    }
    save();
    refresh();
  });
  refresh();
})();
</script>
"""


def _wrap_html(table: str, filename: str, review_panel: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Agent Edits — {escape(filename)}</title>
  {_HTML_STYLE}
</head>
<body>
  <h1>AI Agent Edits — {escape(filename)}</h1>
  <div class="meta">
    Hover any highlighted edit to see its check ID and reason. Yellow = changed,
    green = added, red = removed. Use <b>changes.patch</b> to apply with
    <code>patch</code> or review in any diff tool.
  </div>
  <div class="legend">
    <span class="add">Added / fixed</span>
    <span class="del">Removed</span>
    <span class="chg">Changed</span>
  </div>
  {review_panel}
  {table}
  {_REVIEW_SCRIPT}
</body>
</html>
"""


def _no_changes_html(filename: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>No Changes — {escape(filename)}</title>{_HTML_STYLE}</head>
<body>
  <h1>No Changes — {escape(filename)}</h1>
  <p style="padding:20px;font-size:1rem;">
    No safe auto-fixes were applicable. See <code>report.md</code> for findings
    that require human attention.
  </p>
</body>
</html>
"""
