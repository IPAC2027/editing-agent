"""Report writers: report.json, report.md, and index.html."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.models import Paper, Severity


def write_report(paper: Paper, out_dir: Path) -> None:
    """Write ``report.json``, ``report.md``, and ``index.html`` into *out_dir*."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _write_json(paper, out_dir / "report.json", generated_at)
    _write_markdown(paper, out_dir / "report.md", generated_at)
    _write_index_html(paper, out_dir / "index.html", generated_at)


def _write_json(paper: Paper, path: Path, generated_at: str) -> None:
    data = {
        "paper_id": paper.paper_id,
        "generated_at": generated_at,
        "source": str(paper.source_path),
        "title": paper.title,
        "findings": [f.model_dump() for f in paper.findings],
        "summary": {
            "errors":     sum(1 for f in paper.findings if f.severity == Severity.ERROR),
            "warnings":   sum(1 for f in paper.findings if f.severity == Severity.WARNING),
            "info":       sum(1 for f in paper.findings if f.severity == Severity.INFO),
            "auto_fixed": sum(1 for f in paper.findings if f.auto_fixed),
        },
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_markdown(paper: Paper, path: Path, generated_at: str) -> None:
    errors    = [f for f in paper.findings if f.severity == Severity.ERROR   and not f.auto_fixed]
    warnings  = [f for f in paper.findings if f.severity == Severity.WARNING and not f.auto_fixed]
    fixed     = [f for f in paper.findings if f.auto_fixed]
    info      = [f for f in paper.findings if f.severity == Severity.INFO    and not f.auto_fixed]
    llm_review_path = paper.__dict__.get("llm_review_path")
    repair_plan_path = paper.__dict__.get("repair_plan_path")

    traffic = "🔴 RED"   if errors else ("🟡 YELLOW" if warnings else "🟢 GREEN")

    lines = [
        f"# Pre-screen Report — {paper.paper_id}",
        "",
        f"**Status:** {traffic}",
        f"**Title:** {paper.title or '(unknown)'}",
        f"**Generated:** {generated_at}",
        "",
        "| Errors | Warnings | Auto-fixed | Info |",
        "|--------|----------|------------|------|",
        f"| {len(errors)} | {len(warnings)} | {len(fixed)} | {len(info)} |",
        "",
        "## How to review",
        "",
        "- Open **`changes.html`** in a browser for a side-by-side view of every auto-fix.",
        "- The **`changes.patch`** can be applied (`patch < changes.patch`) or reviewed in any diff tool.",
        f"- **`{paper.paper_id}_edited.tex`** is the source with all safe fixes already applied.",
        "- Items below marked ✏️ were auto-fixed; items marked ⚠️ or ❌ need human attention.",
        "",
    ]
    if llm_review_path:
        lines += [f"- **`{llm_review_path}`** contains the optional local-model review; verify every suggestion before editing.", ""]
    if repair_plan_path:
        lines += [f"- **`{repair_plan_path}`** records every auto-fix, its evidence, and the final build validation status.", ""]

    for group, heading, icon in [
        (errors,   "Errors (must fix)",           "❌"),
        (warnings, "Warnings (should fix)",        "⚠️"),
        (fixed,    "Auto-fixed (review & accept)", "✏️"),
        (info,     "Info",                         "ℹ️"),
    ]:
        if not group:
            continue
        lines += [f"## {icon} {heading}", ""]
        for f in group:
            loc = f" *(line {f.line})*" if f.line else ""
            lines.append(f"### `{f.check_id}`{loc}")
            lines.append(f"{f.message}")
            if f.original:
                lines.append(f"\n**Original:** `{f.original}`")
            if f.suggested:
                lines.append(f"\n**Suggested:** `{f.suggested}`")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


_INDEX_STYLE = """
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       margin:0;background:#f5f5f5;}
  header{background:#2c3e50;color:#fff;padding:16px 24px;}
  header h1{margin:0;font-size:1.3rem;}
  header p{margin:4px 0 0;font-size:.9rem;opacity:.8;}
  .badge{display:inline-block;padding:4px 12px;border-radius:20px;
         font-weight:600;font-size:1rem;margin-left:10px;}
  .green{background:#27ae60;color:#fff;}
  .yellow{background:#f39c12;color:#fff;}
  .red{background:#e74c3c;color:#fff;}
  main{padding:24px;max-width:900px;}
  .card{background:#fff;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.12);
        padding:20px;margin-bottom:20px;}
  .card h2{margin:0 0 12px;font-size:1rem;color:#2c3e50;}
  .stats{display:flex;gap:20px;margin-bottom:16px;}
  .stat{text-align:center;min-width:70px;}
  .stat .n{font-size:1.8rem;font-weight:700;}
  .stat .lbl{font-size:.75rem;color:#888;text-transform:uppercase;}
  .err{color:#e74c3c;} .warn{color:#f39c12;} .fix{color:#27ae60;} .inf{color:#3498db;}
  .links a{display:inline-block;margin-right:12px;padding:6px 14px;
           border-radius:4px;background:#3498db;color:#fff;
           text-decoration:none;font-size:.9rem;}
  .links a:hover{background:#2980b9;}
  .links a.sec{background:#7f8c8d;}
  .finding{border-left:3px solid #ddd;padding:8px 12px;margin:8px 0;
           font-size:.88rem;}
  .finding.err-f{border-color:#e74c3c;background:#fdf0ef;}
  .finding.warn-f{border-color:#f39c12;background:#fef9ef;}
  .finding.fix-f{border-color:#27ae60;background:#edfaf1;}
  code{background:#ecf0f1;padding:1px 5px;border-radius:3px;
       font-family:monospace;font-size:.85em;}
  pre{background:#ecf0f1;padding:10px;border-radius:4px;
      overflow-x:auto;font-size:.82rem;}
</style>
"""


def _write_index_html(paper: Paper, path: Path, generated_at: str) -> None:
    errors   = [f for f in paper.findings if f.severity == Severity.ERROR   and not f.auto_fixed]
    warnings = [f for f in paper.findings if f.severity == Severity.WARNING and not f.auto_fixed]
    fixed    = [f for f in paper.findings if f.auto_fixed]
    info     = [f for f in paper.findings if f.severity == Severity.INFO    and not f.auto_fixed]
    llm_review_path = paper.__dict__.get("llm_review_path")
    repair_plan_path = paper.__dict__.get("repair_plan_path")

    badge_cls = "red" if errors else ("yellow" if warnings else "green")
    badge_txt = "🔴 Needs fixes" if errors else ("🟡 Review suggested fixes" if (warnings or fixed) else "🟢 Pass")

    def _finding_html(f, css: str) -> str:
        loc  = f" <small style='color:#888'>line {f.line}</small>" if f.line else ""
        orig = f"<br><b>Original:</b> <code>{_esc(f.original)}</code>" if f.original else ""
        sugg = f"<br><b>Suggested:</b> <code>{_esc(f.suggested)}</code>" if f.suggested else ""
        aflag = " <span style='background:#27ae60;color:#fff;padding:1px 6px;border-radius:3px;font-size:.75rem;'>auto-fixed</span>" if f.auto_fixed else ""
        return (f'<div class="finding {css}">'
                f'<code>{_esc(f.check_id)}</code>{loc}{aflag}<br>'
                f'{_esc(f.message)}{orig}{sugg}'
                f'</div>')

    findings_html = ""
    for f in errors:
        findings_html += _finding_html(f, "err-f")
    for f in warnings:
        findings_html += _finding_html(f, "warn-f")
    for f in fixed:
        findings_html += _finding_html(f, "fix-f")

    llm_link = (
        f'<a href="{_esc(llm_review_path)}" class="sec">&#129302; LLM review</a>'
        if llm_review_path else ""
    )
    repair_plan_link = (
        f'<a href="{_esc(repair_plan_path)}" class="sec">&#128221; repair plan</a>'
        if repair_plan_path else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pre-screen — {_esc(paper.paper_id)}</title>
  {_INDEX_STYLE}
</head>
<body>
<header>
  <h1>AI Pre-screen Report
    <span class="badge {badge_cls}">{badge_txt}</span>
  </h1>
  <p><b>Paper:</b> {_esc(paper.paper_id)}
     &nbsp;|&nbsp;
     <b>Title:</b> {_esc(paper.title or "(unknown)")}
     &nbsp;|&nbsp;
     <b>Generated:</b> {_esc(generated_at)}
  </p>
</header>
<main>
  <div class="card">
    <h2>Summary</h2>
    <div class="stats">
      <div class="stat"><div class="n err">{len(errors)}</div><div class="lbl">Errors</div></div>
      <div class="stat"><div class="n warn">{len(warnings)}</div><div class="lbl">Warnings</div></div>
      <div class="stat"><div class="n fix">{len(fixed)}</div><div class="lbl">Auto-fixed</div></div>
      <div class="stat"><div class="n inf">{len(info)}</div><div class="lbl">Info</div></div>
    </div>
    <div class="links">
      <a href="changes.html">&#128269; Side-by-side diff</a>
      <a href="report.md" class="sec">&#128196; report.md</a>
      <a href="report.json" class="sec">&#128203; report.json</a>
      <a href="changes.patch" class="sec">&#128203; changes.patch</a>
      {llm_link}
      {repair_plan_link}
    </div>
  </div>

  <div class="card">
    <h2>Findings</h2>
    {findings_html if findings_html else '<p style="color:#27ae60">No issues found!</p>'}
  </div>

  <div class="card">
    <h2>How to review auto-fixes</h2>
    <ol>
      <li>Open <a href="changes.html"><b>changes.html</b></a> in your browser to see
          a colour-coded side-by-side view of every change.</li>
      <li>Open <b>{_esc(paper.paper_id)}_edited.tex</b> if you want to accept all fixes at once.</li>
      <li>For selective adoption, apply <b>changes.patch</b> to your source:<br>
          <pre>patch Source_Files/{_esc(paper.paper_id)}.tex &lt; aiagent_prescreen/changes.patch</pre>
      </li>
      <li>Items marked ❌ (Errors) require human action — the agent did not auto-fix those.</li>
    </ol>
  </div>
</main>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _esc(s: str | None) -> str:
    if not s:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))
