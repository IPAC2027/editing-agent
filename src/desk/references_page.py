"""The desk's "Check a reference list" tab.

Paste a bibliography, press Check, and each reference comes back formatted,
looked up and verified by the same engine the paper screening uses
(:func:`src.references.screen_reference`).  It replaces the reference
formatter's separate Streamlit app, so editors have one place to work.
"""

from __future__ import annotations

import re

from src.edits import Tier
from src.references import screen_reference, split_refs

MAX_REFERENCES = 200


def check_reference_list(text: str, *, lookups: bool = True) -> dict:
    """Screen every reference in *text*; the payload the page renders."""
    raw_refs = [r for r in split_refs(text or "") if r.strip()][:MAX_REFERENCES]
    rows = []
    for number, raw in enumerate(raw_refs, start=1):
        shown = re.sub(r"^\s*\[\d+\]\s*", "", raw).strip()
        result = screen_reference(shown, label=f"Reference [{number}]", offline=not lookups)
        rows.append({
            "n": number,
            "before": shown,
            "after": result.after,
            "kind": ("automatic" if result.tier is Tier.AUTO else
                     "suggested" if result.tier is Tier.SUGGEST else "unchanged"),
            "message": result.message,
            "added_from": result.added_from,
            "integrity": result.integrity,
            "notes": [f.message for f in result.findings],
        })
    return {"references": rows, "truncated": len(split_refs(text or "")) > MAX_REFERENCES}


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check a reference list — JACoW review desk</title>
<style>
:root{--ink:#16191d;--ink2:#48525c;--muted:#78838d;--paper:#f2f5f6;--surface:#fff;
 --rule:#d6dbdf;--accent:#255a7a;--accent-soft:#e2edf3;--on-accent:#fff;--good:#1c7a4a;
 --good-soft:#e2f3e9;--warn:#8f6f08;--warn-soft:#faf1d8;--bad:#9c2135;--bad-soft:#fbe9ec;
 --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
 --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
@media (prefers-color-scheme:dark){:root{--ink:#e8ecef;--ink2:#a8b2ba;--muted:#7b858e;
 --paper:#0f1317;--surface:#171c21;--rule:#2c343b;--accent:#79b0d1;--accent-soft:#1a2a35;
 --on-accent:#0d1216;--good:#39a06f;--good-soft:#14261d;--warn:#c19a3c;--warn-soft:#2a2313;
 --bad:#d6607a;--bad-soft:#2a161a}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans)}
.top{background:var(--surface);border-bottom:1px solid var(--rule);padding:12px 20px;display:flex;gap:16px;align-items:center}
.top a{color:var(--accent);text-decoration:none}.top b{font-weight:650}
main{max-width:980px;margin:0 auto;padding:20px}
textarea{width:100%;min-height:200px;font:13px/1.5 var(--mono);padding:10px;border:1px solid var(--rule);
 border-radius:7px;background:var(--surface);color:var(--ink)}
.bar{display:flex;gap:14px;align-items:center;margin:10px 0 18px}
button{background:var(--accent);color:var(--on-accent);border:0;border-radius:7px;padding:8px 16px;font:inherit;cursor:pointer}
button[disabled]{opacity:.6;cursor:wait}
.ref{background:var(--surface);border:1px solid var(--rule);border-radius:7px;padding:12px 14px;margin:0 0 10px}
.ref h3{margin:0 0 6px;font-size:13px;color:var(--ink2);font-weight:600}
.tag{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;margin-left:6px}
.automatic{background:var(--good-soft);color:var(--good)}.suggested{background:var(--accent-soft);color:var(--accent)}
.unchanged{background:var(--warn-soft);color:var(--warn)}
.before{color:var(--ink2);text-decoration:line-through;text-decoration-color:var(--muted)}
.after{margin-top:4px}.note{font-size:13px;color:var(--ink2);margin-top:6px}
.copy{background:transparent;color:var(--accent);border:1px solid var(--rule);padding:3px 10px;font-size:13px;margin-top:8px}
</style></head><body>
<div class="top"><a href="/">&larr; Review desk</a><b>Check a reference list</b></div>
<main>
<p>Paste a reference list, one reference per paragraph or numbered [1], [2], …
Each one is formatted to JACoW style and checked against Crossref, DataCite and the
JACoW proceedings. Nothing is saved.</p>
<textarea id="refs" placeholder="[1] A. Alpha, B. Beta and C. Gamma, &ldquo;Title&rdquo;, in Proc. IPAC 2023, …"></textarea>
<div class="bar"><button id="go">Check</button>
<span id="status"></span></div>
<div id="out"></div>
</main>
<script>
const $ = s => document.querySelector(s);
const esc = s => (s || "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const label = {automatic:"Punctuation fixed", suggested:"Reformatted — your decision", unchanged:"Left as written"};
$("#go").onclick = async () => {
  $("#go").disabled = true; $("#status").textContent = "Checking…"; $("#out").innerHTML = "";
  try {
    const res = await fetch("/api/format-references", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({text: $("#refs").value})});
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    $("#status").textContent = data.references.length + " reference(s)" +
      (data.truncated ? " — only the first 200 were checked" : "");
    $("#out").innerHTML = data.references.map(r => `
      <div class="ref"><h3>[${r.n}] <span class="tag ${r.kind}">${label[r.kind]}</span></h3>
      ${r.after ? `<div class="before">${esc(r.before)}</div><div class="after">${esc(r.after)}</div>
        <button class="copy" data-text="${esc(r.after)}">Copy</button>` : `<div>${esc(r.before)}</div>`}
      ${r.added_from ? `<div class="note">Added from ${esc(r.added_from)}.</div>` : ""}
      ${r.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}</div>`).join("");
    document.querySelectorAll(".copy").forEach(b => b.onclick = () =>
      navigator.clipboard.writeText(b.dataset.text).then(() => b.textContent = "Copied"));
  } catch (e) { $("#status").textContent = "Something went wrong: " + e.message; }
  $("#go").disabled = false;
};
</script></body></html>
"""
