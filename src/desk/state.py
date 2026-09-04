"""Review state: what the editor decided, noted and changed, per paper.

Everything an editor does at the desk lands in one file per submission,
``aiagent_prescreen/review_state.json``. That file is the record: it survives
closing the browser, re-running the screen, moving the folder, and having a
second editor pick the paper up. Nothing lives only in a browser tab.

Three kinds of editor input are tracked, deliberately kept distinct:

**Decisions** — accept or reject one of the agent's suggestions. Stored by edit
id, so re-screening a paper keeps the decisions whose text has not changed.

**Notes** — free text attached to a suggestion, to a finding, or to the paper
as a whole. Notes are how an editor records *why* they rejected something,
which is the part a colleague picking the paper up later actually needs.

**The editor's own work** — issues they spotted that the agent missed, and
edits they made by hand. A hand edit is stored as a line replacement against
the text the editor was looking at, so it is as reversible and as reviewable as
anything the agent proposed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from src.desk import plain

STATE_FILENAME = "review_state.json"

SEVERITY_CHOICES = ("must_fix", "worth_a_look", "note")
SEVERITY_TO_REPORT = {
    "must_fix": "error",
    "worth_a_look": "warning",
    "note": "info",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def finding_key(check_id: str, line: int | None, original: str | None) -> str:
    """A stable id for a finding, which the report format does not give them.

    Built from the check, the line and a digest of the flagged text, so it
    survives a re-screen as long as the underlying problem is still there — an
    editor who ticked something off does not get it back for free.
    """
    digest = hashlib.sha256((original or "").encode("utf-8")).hexdigest()[:8]
    return f"{check_id}:{line if line is not None else '-'}:{digest}"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EditorNote(BaseModel):
    """Something the editor spotted that the agent did not."""

    id: str = ""
    text: str
    where: str = ""                 # "reference 4", "Figure 2 caption", "page 3"
    severity: str = "worth_a_look"
    for_author: bool = True         # include it in the letter back to the author
    created_at: str = Field(default_factory=_now)
    resolved: bool = False

    @property
    def report_severity(self) -> str:
        return SEVERITY_TO_REPORT.get(self.severity, "warning")


class ManualEdit(BaseModel):
    """A line the editor rewrote by hand."""

    id: str = ""
    line: int
    before: str
    after: str
    note: str = ""
    created_at: str = Field(default_factory=_now)

    @property
    def summary(self) -> str:
        def _short(text: str, width: int = 70) -> str:
            flat = " ".join(text.split())
            return flat if len(flat) <= width else flat[: width - 1] + "…"
        return f"{_short(self.before)} → {_short(self.after)}"


class ReviewState(BaseModel):
    """One editor's work on one paper."""

    schema_version: int = 1
    paper_id: str = ""
    status: str = "new"                    # new | in_review | done | needs_author
    editor: str = ""
    decisions: dict[str, str] = Field(default_factory=dict)   # edit id -> accepted/rejected
    edit_notes: dict[str, str] = Field(default_factory=dict)  # edit id -> note
    handled: dict[str, bool] = Field(default_factory=dict)     # finding key -> ticked off
    finding_notes: dict[str, str] = Field(default_factory=dict)
    editor_notes: list[EditorNote] = Field(default_factory=list)
    manual_edits: list[ManualEdit] = Field(default_factory=list)
    paper_note: str = ""                   # a note about the paper as a whole
    letter_override: str = ""              # an edited author letter, if any
    opened_at: str = ""
    updated_at: str = ""
    closed_at: str = ""

    # -- persistence ----------------------------------------------------
    @classmethod
    def path_for(cls, folder: Path) -> Path:
        return folder / "aiagent_prescreen" / STATE_FILENAME

    @classmethod
    def load(cls, folder: Path) -> "ReviewState":
        path = cls.path_for(folder)
        if not path.exists():
            return cls()
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt state file must not lock a paper
            backup = path.with_suffix(".json.broken")
            try:
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
            return cls()

    def save(self, folder: Path) -> Path:
        path = self.path_for(folder)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = _now()
        if not self.opened_at:
            self.opened_at = self.updated_at
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    # -- mutation -------------------------------------------------------
    def touch(self) -> None:
        if self.status == "new":
            self.status = "in_review"

    def decide(self, edit_id: str, decision: str) -> None:
        if decision == "undecided":
            self.decisions.pop(edit_id, None)
        else:
            self.decisions[edit_id] = decision
        self.touch()

    def set_edit_note(self, edit_id: str, note: str) -> None:
        if note.strip():
            self.edit_notes[edit_id] = note.strip()
        else:
            self.edit_notes.pop(edit_id, None)
        self.touch()

    def set_handled(self, key: str, value: bool) -> None:
        if value:
            self.handled[key] = True
        else:
            self.handled.pop(key, None)
        self.touch()

    def set_finding_note(self, key: str, note: str) -> None:
        if note.strip():
            self.finding_notes[key] = note.strip()
        else:
            self.finding_notes.pop(key, None)
        self.touch()

    def add_note(self, note: EditorNote) -> EditorNote:
        note.id = self._next_id("N", [n.id for n in self.editor_notes])
        self.editor_notes.append(note)
        self.touch()
        return note

    def remove_note(self, note_id: str) -> bool:
        before = len(self.editor_notes)
        self.editor_notes = [n for n in self.editor_notes if n.id != note_id]
        self.touch()
        return len(self.editor_notes) != before

    def add_manual_edit(self, edit: ManualEdit) -> ManualEdit:
        edit.id = self._next_id("M", [e.id for e in self.manual_edits])
        self.manual_edits.append(edit)
        self.touch()
        return edit

    def remove_manual_edit(self, edit_id: str) -> bool:
        before = len(self.manual_edits)
        self.manual_edits = [e for e in self.manual_edits if e.id != edit_id]
        self.touch()
        return len(self.manual_edits) != before

    @staticmethod
    def _next_id(prefix: str, existing: list[str]) -> str:
        numbers = [
            int(match.group(1))
            for value in existing
            if (match := re.match(rf"^{prefix}(\d+)$", value or ""))
        ]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"

    # -- queries --------------------------------------------------------
    def decision_for(self, edit_id: str) -> str:
        return self.decisions.get(edit_id, "undecided")

    def accepted_ids(self, suggested_ids: list[str], auto_ids: list[str]) -> list[str]:
        """Automatic edits, plus the suggestions the editor accepted."""
        return list(auto_ids) + [
            edit_id for edit_id in suggested_ids
            if self.decisions.get(edit_id) == "accepted"
        ]

    def undecided_count(self, suggested_ids: list[str]) -> int:
        return sum(1 for i in suggested_ids if i not in self.decisions)

    @property
    def status_word(self) -> str:
        return plain.status_word(self.status)


# ---------------------------------------------------------------------------
# The worklist
# ---------------------------------------------------------------------------

class PaperRow(BaseModel):
    """One line in the worklist."""

    folder: str
    name: str
    paper_id: str
    title: str = ""
    kind: str = "latex"              # latex | word | unknown
    screened: bool = False
    status: str = "new"
    status_word: str = "Not started"
    editor: str = ""
    applied: int = 0
    to_decide: int = 0
    decided: int = 0
    must_fix: int = 0
    worth_a_look: int = 0
    my_notes: int = 0
    my_edits: int = 0
    build: str = ""
    updated_at: str = ""

    @property
    def progress(self) -> float:
        total = self.to_decide + self.decided
        return 1.0 if total == 0 else self.decided / total


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def submission_folders(root: Path) -> list[Path]:
    """Submission folders under *root*, or *root* itself if it is one."""
    from src.workflow.prescreen import detect_source_format

    if detect_source_format(root) != "unknown":
        return [root]
    found = [
        child for child in sorted(root.iterdir())
        if child.is_dir() and detect_source_format(child) != "unknown"
    ]
    return found


def describe(folder: Path) -> PaperRow:
    """Build a worklist row for one submission folder."""
    from src.workflow.prescreen import detect_source_format

    out_dir = folder / "aiagent_prescreen"
    report = _read_json(out_dir / "report.json")
    state = ReviewState.load(folder)

    kind = detect_source_format(folder)
    paper_id = report.get("paper_id") or state.paper_id or _guess_paper_id(folder)

    row = PaperRow(
        folder=str(folder),
        name=folder.name,
        paper_id=paper_id,
        title=plain.readable_title(report.get("title", "")),
        kind=kind,
        screened=bool(report),
        status=state.status,
        status_word=state.status_word,
        editor=state.editor,
        my_notes=len([n for n in state.editor_notes if not n.resolved]),
        my_edits=len(state.manual_edits),
        build=report.get("build", ""),
        updated_at=state.updated_at,
    )

    if not report:
        row.status_word = "Not prepared yet"
        return row

    findings = report.get("findings", [])
    row.must_fix = sum(1 for f in findings if f.get("severity") == "error")
    row.worth_a_look = sum(1 for f in findings if f.get("severity") == "warning")

    edits = report.get("summary", {}).get("edits", {})
    row.applied = edits.get("applied_automatically", 0)

    suggested = _suggested_ids(out_dir)
    row.decided = sum(1 for i in suggested if i in state.decisions)
    row.to_decide = len(suggested) - row.decided
    return row


def _guess_paper_id(folder: Path) -> str:
    match = re.match(r"^([A-Za-z0-9]+)", folder.name)
    return match.group(1) if match else folder.name


def _suggested_ids(out_dir: Path) -> list[str]:
    """Ids of everything awaiting a decision: span suggestions plus structural."""
    ids: list[str] = []
    edits = _read_json(out_dir / "edits.json")
    ids += [
        e.get("id", "") for e in edits.get("edits", [])
        if e.get("tier") == "suggest"
    ]
    structural = _read_json(out_dir / "structural.json")
    reorder = structural.get("reorder")
    if reorder and reorder.get("desired_order") and (
        reorder.get("desired_order") != reorder.get("current_order")
    ):
        ids.append(reorder.get("id", "R1"))
    return [i for i in ids if i]


def worklist(root: Path) -> list[PaperRow]:
    return [describe(folder) for folder in submission_folders(root)]
