"""The editor's review surface: per-edit patches, a git history, and review.html.

What this replaces
------------------
The previous output offered an editor exactly one artifact they could use:
``<ID>_edited.tex``, containing every change at once.  ``changes.html`` rendered
Accept and Reject buttons, but the decisions went to ``localStorage`` and could
only be downloaded as a JSON file that no code read.  So the real choice was
*take all of it or none of it*, and one bad edit among twenty meant discarding
the file and hand-editing.

What an editor gets now
-----------------------
``<ID>_edited.tex``
    The source with **only the AUTO tier** applied — the changes that are
    mechanically safe and need no review.  Adoptable wholesale, sight unseen.
``review.html``
    One accept/reject decision per SUGGEST edit, with the exact before/after,
    the rule it comes from, and its evidence.  Decisions are saved as
    ``review_decisions.json`` and are **read back** by ``aiagent apply``.
``edits/E0NN.patch``
    Every edit as a standalone unified diff, applicable on its own with
    ``git apply`` or ``patch``.
``history/``
    A real git repository: the original as the first commit, then one commit
    per edit.  ``git log -p``, ``git revert <sha>`` and any diff tool the editor
    already uses work immediately.
``edits.json``
    The machine-readable :class:`~src.edits.EditSet`, which is what
    ``aiagent apply`` operates on.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.edits import Confidence, Edit, EditSet, Tier
from src.lookup_status import STATUS, label
from src.models import Finding, Severity


# ---------------------------------------------------------------------------
# Per-edit patches
# ---------------------------------------------------------------------------

def write_per_edit_patches(editset: EditSet, source: str, out_dir: Path) -> Path:
    """Write one standalone unified diff per edit into ``out_dir/edits/``."""
    patch_dir = out_dir / "edits"
    patch_dir.mkdir(parents=True, exist_ok=True)
    for edit_id, patch in editset.per_edit_patches(source).items():
        (patch_dir / f"{edit_id}.patch").write_text(patch, encoding="utf-8")
    index = [
        {
            "id": edit.id,
            "check_id": edit.check_id,
            "tier": edit.tier.value,
            "line": edit.line,
            "patch": f"edits/{edit.id}.patch",
            "summary": edit.short(80),
        }
        for edit in editset.edits
    ]
    path = patch_dir / "index.json"
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return patch_dir


# ---------------------------------------------------------------------------
# Git history
# ---------------------------------------------------------------------------

def write_git_history(
    editset: EditSet,
    source: str,
    out_dir: Path,
    *,
    paper_id: str,
) -> Path | None:
    """Build a git repository with one commit per edit.

    This is the cheapest possible "trackable and individually reversible":
    thirty lines of code and the editor gets tooling they already know instead
    of a bespoke review UI.  Returns the repository path, or ``None`` when git
    is unavailable.
    """
    if not shutil.which("git"):
        return None

    repo = out_dir / "history"
    repo.mkdir(parents=True, exist_ok=True)
    target = repo / editset.file

    def _git(*args: str) -> bool:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            env={
                "GIT_AUTHOR_NAME": "aiagent prescreen",
                "GIT_AUTHOR_EMAIL": "aiagent@localhost",
                "GIT_COMMITTER_NAME": "aiagent prescreen",
                "GIT_COMMITTER_EMAIL": "aiagent@localhost",
                "HOME": str(repo),
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
            },
        )
        return result.returncode == 0

    if not (repo / ".git").exists() and not _git("init", "--quiet", "-b", "main"):
        return None

    target.write_text(source, encoding="utf-8")
    _git("add", "--", editset.file)
    _git("commit", "--quiet", "--allow-empty", "-m",
         f"{paper_id}: author submission as received")

    # Apply edits one at a time, in source order, committing each.
    applied: list[str] = []
    for edit in editset.edits:
        applied.append(edit.id)
        try:
            target.write_text(editset.apply(source, applied), encoding="utf-8")
        except Exception:  # noqa: BLE001 — never let history-building break a run
            applied.pop()
            continue
        _git("add", "--", editset.file)
        _git(
            "commit", "--quiet", "--allow-empty", "-m",
            f"[{edit.tier.value}] {edit.check_id} ({edit.id}) line {edit.line}\n\n"
            f"{edit.message}\n\n"
            f"before: {edit.before!r}\nafter:  {edit.after!r}\n"
            f"rule:   {edit.rule or '(none recorded)'}\n"
            f"source: {edit.evidence.source}"
            + ("" if edit.evidence.checked else " (NOT VERIFIED)"),
        )

    (repo / "README.txt").write_text(
        f"""One commit per proposed edit, oldest first.

    git log --oneline          list every edit
    git log -p                 read each edit as a diff
    git show <sha>             one edit, with its reason in the message
    git revert <sha>           undo one edit, keeping the rest

The first commit is the submission exactly as the author sent it, so
`git diff main~{len(applied)} -- {editset.file}` is the complete change set.
""",
        encoding="utf-8",
    )
    return repo


# ---------------------------------------------------------------------------
# review.html
# ---------------------------------------------------------------------------

_STYLE = """
<style>
 :root{
   --ink:#16191d; --ink2:#4a545e; --muted:#79838d; --paper:#f4f6f7;
   --surface:#fff; --surface2:#eef1f3; --rule:#d8dde1;
   --accent:#2c5d7d; --accent-soft:#e4edf3;
   --add:#1c7a4a; --add-soft:#e3f4ea; --del:#9c2135; --del-soft:#fbe9ec;
   --auto:#2c5d7d; --suggest:#a8850a; --flag:#9c2135;
   --mono:ui-monospace,"SFMono-Regular",Consolas,"Liberation Mono",monospace;
 }
 @media (prefers-color-scheme:dark){:root{
   --ink:#e7ebee; --ink2:#a6b0b9; --muted:#79838c; --paper:#101418;
   --surface:#171c21; --surface2:#1f252b; --rule:#2b3339;
   --accent:#7aaecf; --accent-soft:#1b2a35;
   --add:#2f9464; --add-soft:#14261d; --del:#cf4f68; --del-soft:#2a161a;
   --auto:#7aaecf; --suggest:#b58f22; --flag:#cf4f68;
 }}
 *{box-sizing:border-box}
 body{margin:0;background:var(--paper);color:var(--ink);
      font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
 header{position:sticky;top:0;z-index:5;background:var(--surface);
        border-bottom:1px solid var(--rule);padding:14px 22px}
 .hrow{display:flex;flex-wrap:wrap;gap:12px 22px;align-items:baseline;
       max-width:1120px;margin:0 auto}
 h1{margin:0;font-size:1.05rem;font-weight:600}
 h1 .pid{font-family:var(--mono);color:var(--accent)}
 .meta{font-size:.82rem;color:var(--muted)}
 .badge{font-family:var(--mono);font-size:.72rem;letter-spacing:.06em;
        text-transform:uppercase;padding:.22em .6em;border-radius:3px;
        background:var(--accent-soft);color:var(--accent)}
 main{max-width:1120px;margin:0 auto;padding:22px}
 section{margin-bottom:34px}
 h2{font-size:1rem;margin:0 0 4px;font-weight:600}
 .sub{color:var(--ink2);font-size:.88rem;margin:0 0 14px;max-width:78ch}
 .panel{background:var(--surface);border:1px solid var(--rule);border-radius:5px}
 .panel + .panel{margin-top:10px}
 .toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;
          padding:12px 14px;background:var(--surface);border:1px solid var(--rule);
          border-radius:5px;margin-bottom:14px;position:sticky;top:60px;z-index:4}
 button{font:inherit;font-size:.85rem;border:1px solid var(--rule);
        background:var(--surface2);color:var(--ink);border-radius:4px;
        padding:6px 11px;cursor:pointer}
 button:hover{border-color:var(--accent)}
 button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
 button.ok{background:var(--add-soft);border-color:var(--add);color:var(--add)}
 button.no{background:var(--del-soft);border-color:var(--del);color:var(--del)}
 .count{font-family:var(--mono);font-size:.8rem;color:var(--muted);margin-left:auto}
 .edit{padding:14px 16px;border-top:1px solid var(--rule)}
 .edit:first-child{border-top:0}
 .edit.accepted{background:var(--add-soft)}
 .edit.rejected{background:var(--del-soft);opacity:.62}
 .edit.focus{box-shadow:inset 3px 0 0 var(--accent)}
 .ehead{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:baseline;margin-bottom:8px}
 .eid{font-family:var(--mono);font-size:.76rem;color:var(--muted)}
 .chk{font-family:var(--mono);font-size:.76rem;color:var(--accent)}
 .tier{font-family:var(--mono);font-size:.68rem;letter-spacing:.05em;
       text-transform:uppercase;padding:.15em .45em;border-radius:2px;
       border:1px solid currentColor}
 .tier.auto{color:var(--auto)} .tier.suggest{color:var(--suggest)}
 td.revert{white-space:nowrap;font-size:.82rem;color:var(--muted)}
 td.revert label{display:inline-flex;gap:6px;align-items:center;cursor:pointer}
 tr.reverted{opacity:.62}
 tr.reverted td:nth-child(2) code{text-decoration:line-through}
 .loc{font-family:var(--mono);font-size:.76rem;color:var(--muted)}
 .state{margin-left:auto;font-family:var(--mono);font-size:.74rem;color:var(--muted)}
 .msg{font-size:.9rem;color:var(--ink2);margin:0 0 9px;max-width:82ch}
 .ba{display:grid;grid-template-columns:1fr;gap:2px;font-family:var(--mono);
     font-size:.82rem;margin-bottom:9px;overflow-x:auto}
 .ba div{padding:5px 9px;border-radius:3px;white-space:pre-wrap;word-break:break-word}
 .b{background:var(--del-soft);color:var(--del)}
 .a{background:var(--add-soft);color:var(--add)}
 .b::before{content:"− ";opacity:.65} .a::before{content:"+ ";opacity:.65}
 .rule{font-size:.8rem;color:var(--muted);margin:0 0 9px}
 .rule code{font-family:var(--mono);background:var(--surface2);padding:.1em .35em;border-radius:2px}
 .acts{display:flex;gap:7px;flex-wrap:wrap}
 table{width:100%;border-collapse:collapse;font-size:.87rem}
 th,td{text-align:left;padding:9px 13px;border-bottom:1px solid var(--rule);vertical-align:top}
 th{font-family:var(--mono);font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;
    color:var(--muted);font-weight:500;background:var(--surface2)}
 tr:last-child td{border-bottom:0}
 .sev{font-family:var(--mono);font-size:.72rem;white-space:nowrap}
 .sev.error{color:var(--flag)} .sev.warning{color:var(--suggest)} .sev.info{color:var(--muted)}
 pre.cmd{font-family:var(--mono);font-size:.8rem;background:var(--surface2);
         border:1px solid var(--rule);border-radius:4px;padding:10px 12px;
         overflow-x:auto;margin:0 0 8px}
 .note{font-size:.84rem;color:var(--ink2);background:var(--accent-soft);
       border-left:3px solid var(--accent);padding:10px 13px;border-radius:0 4px 4px 0;
       margin-bottom:14px}
 .kbd{font-family:var(--mono);font-size:.72rem;border:1px solid var(--rule);
      border-bottom-width:2px;border-radius:3px;padding:.1em .35em;background:var(--surface2)}
 .empty{padding:16px;color:var(--muted);font-size:.9rem}
 @media(min-width:760px){.ba{grid-template-columns:1fr 1fr}}
</style>
"""

_SCRIPT = r"""
<script>
(() => {
  const cards = [...document.querySelectorAll('.edit[data-id]')];
  const reverts = [...document.querySelectorAll('input[data-revert]')];
  if (!cards.length && !reverts.length) return;
  const key = 'aiagent:' + document.body.dataset.paper + ':' + document.body.dataset.sha;
  let decisions = {};
  try { decisions = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) {}
  let cursor = 0;

  const save = () => { try { localStorage.setItem(key, JSON.stringify(decisions)); } catch (_) {} };

  const render = () => {
    let a = 0, r = 0;
    cards.forEach((card, index) => {
      const state = decisions[card.dataset.id] || 'pending';
      card.classList.toggle('accepted', state === 'accepted');
      card.classList.toggle('rejected', state === 'rejected');
      card.classList.toggle('focus', index === cursor);
      card.querySelector('.state').textContent =
        state === 'pending' ? 'undecided' : state;
      if (state === 'accepted') a++;
      if (state === 'rejected') r++;
    });
    /* An automatic correction stands unless it is explicitly put back, so
       'reverted' is the only value ever stored for one — absence means applied. */
    let put_back = 0;
    reverts.forEach((box) => {
      box.checked = decisions[box.dataset.revert] === 'reverted';
      box.closest('tr').classList.toggle('reverted', box.checked);
      if (box.checked) put_back++;
    });

    const tally = document.getElementById('tally');
    if (tally) {
      tally.textContent =
        `${a} accepted · ${r} rejected · ${cards.length - a - r} undecided`
        + (put_back ? ` · ${put_back} put back` : '');
    }
    const accepted = cards.filter((c) => decisions[c.dataset.id] === 'accepted')
                          .map((c) => c.dataset.id);
    const reverted = reverts.filter((b) => decisions[b.dataset.revert] === 'reverted')
                            .map((b) => b.dataset.revert);
    const parts = [`uv run python main.py apply ${document.body.dataset.folder}`];
    if (accepted.length) parts.push(`--accept ${accepted.join(',')}`);
    if (reverted.length) parts.push(`--reject ${reverted.join(',')}`);
    const cmd = document.getElementById('cmd-accept');
    if (cmd) {
      cmd.textContent = parts.join(' ')
        + (parts.length === 1 ? '   # AUTO edits only' : '');
    }
  };

  const decide = (index, value) => {
    const card = cards[index];
    if (!card) return;
    decisions[card.dataset.id] = value;
    save();
    if (index === cursor && cursor < cards.length - 1) cursor++;
    render();
    cards[cursor]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  };

  document.addEventListener('change', (event) => {
    const box = event.target.closest('input[data-revert]');
    if (!box) return;
    if (box.checked) decisions[box.dataset.revert] = 'reverted';
    else delete decisions[box.dataset.revert];
    save(); render();
  });

  document.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    const action = button.dataset.action;
    if (button.dataset.id) {
      const index = cards.findIndex((c) => c.dataset.id === button.dataset.id);
      decide(index, button.dataset.decision);
      return;
    }
    if (action === 'accept-all' || action === 'reject-all') {
      /* Bulk actions are about suggestions; an automatic correction is put
         back one at a time, deliberately. */
      const value = action === 'accept-all' ? 'accepted' : 'rejected';
      cards.forEach((c) => { decisions[c.dataset.id] = value; });
      save(); render();
    } else if (action === 'reset') {
      decisions = {}; save(); render();
    } else if (action === 'download') {
      const payload = JSON.stringify({
        paper_id: document.body.dataset.paper,
        source_sha256: document.body.dataset.sha,
        generated_at: new Date().toISOString(),
        decisions,
      }, null, 2);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
      link.download = 'review_decisions.json';
      link.click();
      URL.revokeObjectURL(link.href);
    } else if (action === 'copy') {
      const text = document.getElementById('cmd-accept').textContent;
      navigator.clipboard?.writeText(text);
      button.textContent = 'copied';
      setTimeout(() => { button.textContent = 'copy command'; }, 1200);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.target.matches('input,textarea')) return;
    const map = { a: 'accepted', r: 'rejected' };
    if (map[event.key]) { decide(cursor, map[event.key]); event.preventDefault(); }
    else if (event.key === 'j' || event.key === 'ArrowDown') {
      cursor = Math.min(cursor + 1, cards.length - 1); render();
      cards[cursor]?.scrollIntoView({ block: 'center' }); event.preventDefault();
    } else if (event.key === 'k' || event.key === 'ArrowUp') {
      cursor = Math.max(cursor - 1, 0); render();
      cards[cursor]?.scrollIntoView({ block: 'center' }); event.preventDefault();
    }
  });

  render();
})();
</script>
"""


def _esc(text: object) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _edit_card(edit: Edit) -> str:
    evidence = ""
    if edit.evidence.source != "local-rule":
        state = "verified" if edit.evidence.checked else "NOT VERIFIED"
        evidence = (
            f" &middot; evidence: <code>{_esc(label(edit.evidence.source))}</code> "
            f"({_esc(state)})"
        )
    confidence = (
        f" &middot; confidence: {_esc(edit.confidence.value)}"
        if edit.confidence is not Confidence.CERTAIN else ""
    )
    return f"""
  <div class="edit" data-id="{_esc(edit.id)}">
    <div class="ehead">
      <span class="eid">{_esc(edit.id)}</span>
      <span class="chk">{_esc(edit.check_id)}</span>
      <span class="tier {_esc(edit.tier.value)}">{_esc(edit.tier.value)}</span>
      <span class="loc">line {_esc(edit.line)}</span>
      <span class="state">undecided</span>
    </div>
    <p class="msg">{_esc(edit.message)}</p>
    <div class="ba">
      <div class="b">{_esc(edit.before)}</div>
      <div class="a">{_esc(edit.after)}</div>
    </div>
    <p class="rule">{_esc(edit.rule or "")}{evidence}{confidence}
       &middot; patch: <code>edits/{_esc(edit.id)}.patch</code></p>
    <div class="acts">
      <button class="ok" data-id="{_esc(edit.id)}" data-decision="accepted">Accept</button>
      <button class="no" data-id="{_esc(edit.id)}" data-decision="rejected">Reject</button>
    </div>
  </div>"""


def _structural_card(plan) -> str:
    """A structural decision — a permutation, not a span replacement."""
    return f"""
  <div class="edit" data-id="{_esc(plan.id)}">
    <div class="ehead">
      <span class="eid">{_esc(plan.id)}</span>
      <span class="chk">{_esc(plan.check_id)}</span>
      <span class="tier suggest">structural</span>
      <span class="loc">reference list</span>
      <span class="state">undecided</span>
    </div>
    <p class="msg">{_esc(plan.message)}</p>
    <div class="ba"><div class="b">{_esc(plan.summary().splitlines()[0])}</div>
      <div class="a">{_esc(plan.summary().splitlines()[-1])}</div></div>
    <p class="rule">{_esc(plan.rule)} &middot; applied after the span edits &middot;
       patch: <code>edits/{_esc(plan.id)}.patch</code></p>
    <div class="acts">
      <button class="ok" data-id="{_esc(plan.id)}" data-decision="accepted">Accept</button>
      <button class="no" data-id="{_esc(plan.id)}" data-decision="rejected">Reject</button>
    </div>
  </div>"""


def _findings_table(findings: list[Finding], heading: str, blurb: str) -> str:
    if not findings:
        return ""
    rows = "".join(
        f"<tr><td class='sev {_esc(f.severity.value)}'>{_esc(f.severity.value)}</td>"
        f"<td><code>{_esc(f.check_id)}</code>"
        + (f" <span class='loc'>line {_esc(f.line)}</span>" if f.line else "")
        + f"<br>{_esc(f.message)}"
        + (f"<br><code>{_esc(f.original[:200])}</code>" if f.original else "")
        + "</td></tr>"
        for f in findings
    )
    return f"""
  <section>
    <h2>{_esc(heading)}</h2>
    <p class="sub">{_esc(blurb)}</p>
    <div class="panel">
      <table><thead><tr><th>Severity</th><th>Finding</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>
  </section>"""


def write_review_html(
    editset: EditSet,
    out_dir: Path,
    *,
    paper_id: str,
    folder: str,
    findings: list[Finding],
    auto_applied: int,
    build_status: str,
    has_history: bool,
    structural=None,
) -> Path:
    """Render ``review.html`` — one decision per SUGGEST edit, nothing else."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    suggested = editset.suggested
    auto = editset.auto
    structural_decisions = list(structural.decisions) if structural is not None else []

    flags = [f for f in findings if f.severity is Severity.ERROR]
    warnings = [f for f in findings if f.severity is Severity.WARNING]
    notes = [f for f in findings if f.severity is Severity.INFO]

    decisions = len(suggested) + len(structural_decisions)
    verdict = (
        f"{len(flags)} to chase" if flags
        else (f"{decisions} decision{'s' if decisions != 1 else ''}" if decisions
              else "nothing to review")
    )

    cards = "".join(
        [_structural_card(plan) for plan in structural_decisions]
        + [_edit_card(edit) for edit in suggested]
    ) or (
        "<div class='empty'>No edits need a decision. Everything the agent was "
        "confident about is already applied, and everything it was not confident "
        "about is listed below as a finding rather than a change.</div>"
    )

    auto_rows = "".join(
        f"<tr><td class='eid'>{_esc(e.id)}</td>"
        f"<td><code>{_esc(e.check_id)}</code> <span class='loc'>line {_esc(e.line)}</span><br>"
        f"<code>{_esc(e.before)}</code> &rarr; <code>{_esc(e.after)}</code></td>"
        f"<td class='revert'><label><input type='checkbox' data-revert='{_esc(e.id)}'>"
        f" put back</label></td></tr>"
        for e in auto
    )
    auto_section = f"""
  <section>
    <h2>Already applied &mdash; {len(auto)} automatic {'change' if len(auto) == 1 else 'changes'}</h2>
    <p class="sub">Mechanically safe, no judgement involved, and applied without asking.
       They are in <code>{_esc(paper_id)}_edited.tex</code> and each is one commit in
       <code>history/</code>. Nothing here needs you &mdash; but tick
       <b>put back</b> on any one of them and it is dropped from the command below,
       so &ldquo;we did not ask&rdquo; never means &ldquo;you cannot say no&rdquo;.</p>
    <div class="panel"><table><thead><tr><th>Edit</th><th>Change</th>
      <th>Keep the author&rsquo;s?</th></tr></thead>
      <tbody>{auto_rows}</tbody></table></div>
  </section>""" if auto else ""

    history_note = (
        """<pre class="cmd">cd history &amp;&amp; git log --oneline      # one commit per edit
cd history &amp;&amp; git show &lt;sha&gt;         # one edit, with its reason
cd history &amp;&amp; git revert &lt;sha&gt;       # undo one edit, keep the rest</pre>"""
        if has_history else
        "<p class=\"sub\">git was not available, so no commit history was written. "
        "The per-edit patches in <code>edits/</code> serve the same purpose.</p>"
    )

    lookup_note = STATUS.summary_line()

    return _write(out_dir / "review.html", f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review {_esc(paper_id)} &mdash; JACoW prescreen</title>{_STYLE}</head>
<body data-paper="{_esc(paper_id)}" data-sha="{_esc(editset.source_sha256[:16])}"
      data-folder="{_esc(folder)}">
<header><div class="hrow">
  <h1>JACoW prescreen &mdash; <span class="pid">{_esc(paper_id)}</span></h1>
  <span class="badge">{_esc(verdict)}</span>
  <span class="meta">{_esc(generated)} &middot; {_esc(build_status)}</span>
</div></header>
<main>

  <div class="note">
    <b>{_esc(len(auto))}</b> safe change{'' if len(auto) == 1 else 's'} already applied.
    <b>{_esc(decisions)}</b> need{'s' if decisions == 1 else ''} your decision below.
    <b>{_esc(len(flags))}</b> problem{'' if len(flags) == 1 else 's'} the agent will not
    touch. Keys: <span class="kbd">a</span> accept, <span class="kbd">r</span> reject,
    <span class="kbd">j</span>/<span class="kbd">k</span> move.
    <br>{_esc(lookup_note)}
  </div>

  <section>
    <h2>Decisions</h2>
    <p class="sub">Each card is one span of text. Accepting changes only that span;
       rejecting leaves it exactly as the author wrote it. Nothing here is applied
       until you run the command below.</p>
    <div class="toolbar">
      <button data-action="accept-all">Accept all</button>
      <button data-action="reject-all">Reject all</button>
      <button data-action="reset">Clear</button>
      <button class="primary" data-action="download">Save decisions&hellip;</button>
      <span class="count" id="tally"></span>
    </div>
    <div class="panel">{cards}</div>
  </section>

  <section>
    <h2>Apply what you decided</h2>
    <p class="sub">Save the decisions file into this folder, then run either command.
       Both verify that the source still matches before touching anything, and both
       recompile afterwards.</p>
    <pre class="cmd" id="cmd-accept"></pre>
    <button data-action="copy">copy command</button>
    <pre class="cmd" style="margin-top:10px">uv run python main.py apply {_esc(folder)} --decisions review_decisions.json</pre>
    {history_note}
  </section>

  {auto_section}

  {_findings_table(flags, f"Needs a human — {len(flags)} problem" + ("" if len(flags) == 1 else "s"),
                   "The agent found these but will not propose a fix, because fixing them "
                   "needs a fact it cannot verify or a judgement it should not make.")}
  {_findings_table(warnings, f"Worth a look — {len(warnings)}",
                   "Style and consistency points. None of these block acceptance.")}
  {_findings_table(notes, f"For the record — {len(notes)}",
                   "Including any check that did not run, and why. A check that could not "
                   "reach its authority says NOT CHECKED rather than reporting a problem.")}

</main>{_SCRIPT}</body></html>
""")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
