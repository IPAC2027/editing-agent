"""Generate an HTML reference-check report for Word (.docx) submissions.

Produces ``word_references.html`` in the ``aiagent_prescreen/`` folder.
The file shows:
  - A summary table (errors / warnings / auto-fixed counts)
  - For each reference: original text, issues found, and corrected text (if any)
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from src.models import Finding, Severity


def _esc(text: str | None) -> str:
    return html.escape(str(text or ""), quote=True)


_STYLE = """
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    margin: 0; background: #f4f5f7; color: #1a1a2e;
  }
  header {
    background: #1a1a2e; color: #fff;
    padding: 18px 28px;
  }
  header h1 { margin: 0; font-size: 1.4rem; }
  header p  { margin: 5px 0 0; font-size: .9rem; opacity: .75; }
  .badge {
    display: inline-block; padding: 4px 14px; border-radius: 20px;
    font-weight: 700; font-size: .95rem; margin-left: 12px; vertical-align: middle;
  }
  .green  { background: #27ae60; color: #fff; }
  .yellow { background: #e67e22; color: #fff; }
  .red    { background: #c0392b; color: #fff; }
  main { padding: 24px 28px; max-width: 1100px; }
  /* summary card */
  .summary-card {
    background: #fff; border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.12);
    padding: 20px 24px; margin-bottom: 24px;
    display: flex; gap: 32px; flex-wrap: wrap; align-items: center;
  }
  .stat { text-align: center; min-width: 80px; }
  .stat .n { font-size: 2rem; font-weight: 800; }
  .stat .lbl { font-size: .72rem; text-transform: uppercase; color: #888; letter-spacing: .05em; }
  .err-n  { color: #c0392b; }
  .warn-n { color: #e67e22; }
  .fix-n  { color: #27ae60; }
  .info-n { color: #2980b9; }
  /* reference cards */
  .ref-card {
    background: #fff; border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    margin-bottom: 18px; overflow: hidden;
  }
  .ref-header {
    padding: 10px 16px; font-weight: 700; font-size: .95rem;
    border-bottom: 1px solid #eee; display: flex; justify-content: space-between;
    align-items: center;
  }
  .ref-header.ok     { background: #edfaf1; }
  .ref-header.warn   { background: #fef9ef; }
  .ref-header.err    { background: #fdf0ef; }
  .ref-header.fixed  { background: #eaf4fb; }
  .ref-body { padding: 14px 16px; }
  /* before/after diff table */
  .diff-table {
    width: 100%; border-collapse: collapse;
    font-size: .88rem; margin-top: 10px;
  }
  .diff-table th {
    background: #ecf0f1; padding: 6px 10px;
    text-align: left; font-size: .78rem; text-transform: uppercase;
    letter-spacing: .05em; color: #555;
  }
  .diff-table td {
    padding: 8px 10px; vertical-align: top;
    border-top: 1px solid #f0f0f0;
  }
  .diff-table .orig { background: #fff8f8; color: #922; }
  .diff-table .corr { background: #f6fff8; color: #1a7a3a; }
  code {
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: .84em; background: #ecf0f1;
    padding: 1px 5px; border-radius: 3px;
  }
  /* findings list */
  .finding {
    border-left: 3px solid #ccc; padding: 7px 12px;
    margin: 6px 0; font-size: .87rem; border-radius: 0 4px 4px 0;
  }
  .finding.err-f  { border-color: #c0392b; background: #fdf0ef; }
  .finding.warn-f { border-color: #e67e22; background: #fef9ef; }
  .finding.fix-f  { border-color: #27ae60; background: #edfaf1; }
  .chip {
    display: inline-block; font-size: .72rem; font-weight: 700;
    padding: 2px 8px; border-radius: 10px; margin-left: 6px;
    vertical-align: middle;
  }
  .chip-err  { background: #c0392b; color: #fff; }
  .chip-warn { background: #e67e22; color: #fff; }
  .chip-fix  { background: #27ae60; color: #fff; }
  .chip-ok   { background: #27ae60; color: #fff; }
  /* raw text block */
  .raw-text {
    font-family: 'Menlo', 'Consolas', monospace;
    font-size: .82rem; white-space: pre-wrap; word-break: break-word;
    background: #f8f9fa; border: 1px solid #e0e0e0;
    border-radius: 4px; padding: 10px 12px; margin: 8px 0;
    color: #333;
  }
  .section-heading { font-size: 1.05rem; font-weight: 700; margin: 24px 0 10px; color: #1a1a2e; }
  .no-issues { color: #27ae60; font-style: italic; font-size: .9rem; }
</style>
"""


def write_word_reference_report(
    paper_id: str,
    refs_before: list[tuple[int, str]],       # list of (n, original_text)
    refs_after: list[tuple[int, str]],         # list of (n, corrected_text)
    findings_by_ref: dict[int, list[Finding]], # ref_n → list of Finding
    global_findings: list[Finding],            # findings not tied to a specific ref
    out_dir: Path,
) -> Path:
    """Write ``word_references.html`` into *out_dir* and return the path."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    all_findings = global_findings + [f for fl in findings_by_ref.values() for f in fl]
    errors   = [f for f in all_findings if f.severity == Severity.ERROR   and not f.auto_fixed]
    warnings = [f for f in all_findings if f.severity == Severity.WARNING and not f.auto_fixed]
    fixed    = [f for f in all_findings if f.auto_fixed]

    badge_cls = "red"    if errors   else ("yellow" if warnings or fixed else "green")
    badge_txt = ("🔴 Needs fixes" if errors else
                 "🟡 Review corrections" if (warnings or fixed) else
                 "🟢 References OK")

    # --- summary card ---
    summary_html = f"""
<div class="summary-card">
  <div class="stat"><div class="n err-n">{len(errors)}</div><div class="lbl">Errors</div></div>
  <div class="stat"><div class="n warn-n">{len(warnings)}</div><div class="lbl">Warnings</div></div>
  <div class="stat"><div class="n fix-n">{len(fixed)}</div><div class="lbl">Auto-corrected</div></div>
  <div class="stat"><div class="n info-n">{len(refs_before)}</div><div class="lbl">References</div></div>
</div>"""

    # --- global findings (REF-SEC-01, CITE-TEXT-02, etc.) ---
    global_html = ""
    if global_findings:
        global_html = '<div class="section-heading">Document-level findings</div>\n'
        for f in global_findings:
            css = "err-f" if f.severity == Severity.ERROR else (
                  "warn-f" if f.severity == Severity.WARNING else "fix-f")
            orig = f"<br><b>Original:</b> <code>{_esc(f.original)}</code>" if f.original else ""
            sugg = f"<br><b>Suggested:</b> <code>{_esc(f.suggested)}</code>" if f.suggested else ""
            global_html += (
                f'<div class="finding {css}">'
                f'<code>{_esc(f.check_id)}</code> — {_esc(f.message)}{orig}{sugg}'
                f'</div>\n'
            )

    # --- per-reference cards ---
    before_map  = {n: txt for n, txt in refs_before}
    after_map   = {n: txt for n, txt in refs_after}
    all_ref_ns  = sorted(before_map.keys())

    cards_html = '<div class="section-heading">Reference entries</div>\n'
    for n in all_ref_ns:
        orig_txt = before_map[n]
        corr_txt = after_map.get(n, orig_txt)
        ref_findings = findings_by_ref.get(n, [])
        changed = corr_txt != orig_txt

        ref_errors   = [f for f in ref_findings if f.severity == Severity.ERROR   and not f.auto_fixed]
        ref_warnings = [f for f in ref_findings if f.severity == Severity.WARNING and not f.auto_fixed]
        ref_fixed    = [f for f in ref_findings if f.auto_fixed]

        if ref_errors:
            hdr_cls, chip_html = "err", '<span class="chip chip-err">Error</span>' * len(ref_errors)
        elif ref_warnings:
            hdr_cls, chip_html = "warn", '<span class="chip chip-warn">Warning</span>' * len(ref_warnings)
        elif ref_fixed:
            hdr_cls, chip_html = "fixed", '<span class="chip chip-fix">Auto-corrected</span>' * len(ref_fixed)
        else:
            hdr_cls, chip_html = "ok", '<span class="chip chip-ok">✓ OK</span>'

        findings_html = ""
        for f in ref_findings:
            css = "err-f" if f.severity == Severity.ERROR else (
                  "warn-f" if f.severity == Severity.WARNING else "fix-f")
            aflag = (' <span class="chip chip-fix" style="font-size:.68rem">auto-corrected</span>'
                     if f.auto_fixed else "")
            orig = f"<br><b>Original:</b> <code>{_esc(f.original)}</code>" if f.original else ""
            sugg = f"<br><b>Suggested:</b> <code>{_esc(f.suggested)}</code>" if f.suggested else ""
            findings_html += (
                f'<div class="finding {css}">'
                f'<code>{_esc(f.check_id)}</code>{aflag} — {_esc(f.message)}{orig}{sugg}'
                f'</div>\n'
            )

        diff_html = ""
        if changed:
            diff_html = f"""
<table class="diff-table">
  <tr><th style="width:50%">Before</th><th style="width:50%">After (auto-corrected)</th></tr>
  <tr>
    <td class="orig"><div class="raw-text">{_esc(orig_txt)}</div></td>
    <td class="corr"><div class="raw-text">{_esc(corr_txt)}</div></td>
  </tr>
</table>"""
        else:
            diff_html = f'<div class="raw-text">{_esc(orig_txt)}</div>'

        if not ref_findings:
            findings_html = '<p class="no-issues">No issues found for this reference.</p>'

        cards_html += f"""
<div class="ref-card">
  <div class="ref-header {hdr_cls}">
    <span>[{n}]</span>
    <span>{chip_html}</span>
  </div>
  <div class="ref-body">
    {diff_html}
    {findings_html}
  </div>
</div>
"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Word Reference Check — {_esc(paper_id)}</title>
  {_STYLE}
</head>
<body>
<header>
  <h1>Word Submission Reference Check
    <span class="badge {badge_cls}">{badge_txt}</span>
  </h1>
  <p>
    <b>Paper:</b> {_esc(paper_id)}
    &nbsp;|&nbsp;
    <b>Generated:</b> {_esc(generated_at)}
    &nbsp;|&nbsp;
    <b>References checked:</b> {len(refs_before)}
  </p>
</header>
<main>
  {summary_html}
  {global_html}
  {cards_html}
</main>
</body>
</html>"""

    out_path = out_dir / "word_references.html"
    out_path.write_text(html_content, encoding="utf-8")
    return out_path
