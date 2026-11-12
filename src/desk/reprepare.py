"""Preparing papers again, after the way they are prepared has improved.

Preparing a paper again rewrites everything the agent wrote under it and keeps
what the editor owns (``prescreen.EDITOR_OWNED``: the review state, the claim).
That alone is not enough, because the editor's decisions are stored by edit id
(``E001``, ``E002``, …) and ids are numbered by position: once the rules change,
``E003`` can be a different edit, and a decision would silently land on a change
the editor never saw.

So a paper is prepared again through :func:`prepare_keeping_work`. It notes what
each decided edit *says* (its check, its text before and after), prepares the
paper, and moves every decision, note and editor's wording to the new edit that
says the same thing. A decision whose suggestion no longer exists is dropped, and
the paper records which (``ReviewState.reprepared``), so the editor is told
rather than surprised. Hand edits, notes on findings and the editor's own
references are kept as they are: they are matched by content already.

Two kinds of paper are not prepared again by "prepare all again"
(:func:`left_alone`): one another desk is editing, whose editor would otherwise
be working on files changing under them; and one already finished or sent back
to the author, whose reviewed files and letter are written.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.desk import claim as claim_module
from src.desk.state import ReviewState, bib_id

OUT_DIR = "aiagent_prescreen"

#: Papers being prepared right now, so the chief's door does not hand out a
#: half-written one.
_BUSY: set[str] = set()
_LOCK = threading.Lock()


def is_busy(folder: Path) -> bool:
    with _LOCK:
        return str(Path(folder).resolve()) in _BUSY


def left_alone(folder: Path, desk_id: str) -> str:
    """Why "prepare all again" leaves this paper alone: ``held``, ``finished`` or ""."""
    held = claim_module.current(folder)
    if held is not None and held.desk_id != desk_id:
        return "held"
    if (folder / OUT_DIR / "report.json").is_file() and \
            ReviewState.load(folder).status in ("done", "needs_author"):
        return "finished"
    return ""


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fingerprints(folder: Path) -> dict[str, tuple]:
    """Edit id -> what the edit says, for every edit the paper's files name."""
    out = Path(folder) / OUT_DIR
    said: dict[str, tuple] = {}
    for name in ("edits.json", "edits_bib.json"):
        for e in _read(out / name).get("edits", []):
            edit_id = bib_id(e.get("id", "")) if name == "edits_bib.json" else e.get("id", "")
            said[edit_id] = (name, e.get("check_id", ""), e.get("before", ""),
                             e.get("after", ""), e.get("context_before", ""),
                             e.get("context_after", ""))
    for c in _read(out / "word_edits.json").get("corrections", []):
        said[c.get("id", "")] = ("word", c.get("check_id", ""), c.get("before", ""),
                                 c.get("after", ""), str(c.get("paragraph_index", "")),
                                 json.dumps(c.get("format") or {}, sort_keys=True))
    reorder = _read(out / "structural.json").get("reorder") or {}
    if reorder.get("desired_order"):
        said[reorder.get("id", "R1")] = ("reorder", "REF-NUM-02",
                                         json.dumps(reorder.get("current_order")),
                                         json.dumps(reorder.get("desired_order")), "", "")
    said.pop("", None)
    return said


def carry_over(folder: Path, before: dict[str, tuple]) -> dict:
    """Move the editor's decisions from the old edit ids to the new ones.

    Returns ``{"kept": n, "dropped": [...]}``; the dropped ones are also recorded
    on the paper.
    """
    state = ReviewState.load(folder)
    decided = set(state.decisions) | set(state.edit_notes) | set(state.edit_texts)
    if not decided:
        return {"kept": 0, "dropped": []}
    after = fingerprints(folder)
    exact: dict[tuple, list[str]] = {}
    loose: dict[tuple, list[str]] = {}
    for edit_id, said in after.items():
        exact.setdefault(said, []).append(edit_id)
        loose.setdefault(said[:4], []).append(edit_id)

    taken: set[str] = set()
    moved: dict[str, str] = {}
    dropped: list[dict] = []
    for old_id in sorted(decided):
        said = before.get(old_id)
        new_id = ""
        if said is not None:
            same = [c for c in exact.get(said, []) if c not in taken]
            # Without the surrounding text, only when it is the only one: two
            # identical edits in different places must not swap decisions.
            near = [c for c in loose.get(said[:4], []) if c not in taken]
            new_id = same[0] if same else (near[0] if len(near) == 1 else "")
        if new_id:
            taken.add(new_id)
            moved[old_id] = new_id
        else:
            dropped.append({
                "id": old_id,
                "check_id": said[1] if said else "",
                "before": (said[2] if said else "")[:200],
                "after": (said[3] if said else "")[:200],
                "decision": state.decisions.get(old_id, ""),
                "note": state.edit_notes.get(old_id, ""),
            })

    state.decisions = {moved[k]: v for k, v in state.decisions.items() if k in moved}
    state.edit_notes = {moved[k]: v for k, v in state.edit_notes.items() if k in moved}
    state.edit_texts = {moved[k]: v for k, v in state.edit_texts.items() if k in moved}
    state.reprepared.append({
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kept": len(moved), "dropped": dropped,
    })
    state.reprepared = state.reprepared[-5:]
    state.save(folder)
    return {"kept": len(moved), "dropped": dropped}


def prepare_keeping_work(folder: Path, run, *, desk_id: str | None = None) -> dict:
    """``run(folder)`` (the preparation), with the editor's decisions carried over.

    With *desk_id*, a paper another desk took meanwhile is left alone
    (``{"skipped": "held"}``): it is checked once the paper is marked busy, so the
    chief's door cannot hand it out half-prepared either.
    """
    key = str(Path(folder).resolve())
    with _LOCK:
        _BUSY.add(key)
    try:
        if desk_id is not None:
            held = claim_module.current(folder)
            if held is not None and held.desk_id != desk_id:
                return {"kept": 0, "dropped": [], "skipped": "held"}
        before = fingerprints(folder)
        run(folder)
        return carry_over(folder, before)
    finally:
        with _LOCK:
            _BUSY.discard(key)


__all__ = ["carry_over", "fingerprints", "is_busy", "left_alone", "prepare_keeping_work"]
