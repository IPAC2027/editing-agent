"""The chief's desk keeping Indico in step with who is working on what.

Editors never open Indico. When one takes a paper on the chief's desk, the
chief's desk assigns them in Indico; when they give it back unfinished, it
unassigns them; a finished paper stays assigned, as it would in Indico. And
every couple of minutes it reads Indico's assignments back, so a paper the
chief assigns in Indico itself shows up on the desks as that editor's.

Only the conference's paper editors and editing managers in Indico edit
papers: before anyone takes a paper the chief's desk looks their account up in
the event's paper editors (:meth:`IndicoSync.may_edit`, a read, whatever the
switch says). Indico lists editing managers to nobody, so those are the ones
whose own desk Indico told so.

Writing is switched on per conference, on the chief's page, and is limited to
those two requests (``src.indico_client.assign``). Indico's own conflict check
means a paper someone reassigned in Indico meanwhile is left alone and shown
as a problem, never taken from them.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from src.desk import files

SETTINGS_FILE = "indico_sync.json"
READ_EVERY = 120.0          # seconds between reads of Indico's assignments
EDITORS_FOR = 600.0         # how long the event's editor list is trusted
EDITORS_RECHECK = 30.0      # someone not in it: Indico is read again at most this often
EDITORS_KEPT = 3600.0       # Indico out of reach: an editor listed this recently still is


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IndicoSync:
    """Reads Indico's assignments, and (when switched on) sets them."""

    def __init__(self, root: Path, event, *, home: Path | None = None,
                 writer_factory=None, background: bool = True,
                 read_every: float = READ_EVERY) -> None:
        self.root = Path(root)
        self.event = event                      # src.desk.chief.Event
        self.home = home
        self._writer_factory = writer_factory
        self.read_every = read_every
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.last_read = ""
        self.read_error = ""
        self._editors: tuple[float, list] = (0.0, [])
        self._editors_lock = threading.Lock()
        if background:
            threading.Thread(target=self._loop, daemon=True).start()

    # -- the switch, and what is waiting --------------------------------------
    def _settings(self) -> dict:
        try:
            data = json.loads((self.root / SETTINGS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, settings: dict) -> None:
        files.write_text(self.root / SETTINGS_FILE, json.dumps(settings, indent=2))

    @property
    def enabled(self) -> bool:
        settings = self._settings()
        return bool(settings.get("assign")) and settings.get("event") == self.event.event_id

    def set_enabled(self, on: bool) -> None:
        with self.lock:
            settings = self._settings()
            settings.update(assign=bool(on), event=self.event.event_id)
            self._save(settings)
        if on:
            self.wake.set()

    def _paper(self, paper: str, **facts) -> None:
        with self.lock:
            settings = self._settings()
            settings.setdefault("papers", {}).setdefault(paper, {}).update(facts)
            self._save(settings)

    def papers(self) -> dict:
        return self._settings().get("papers", {})

    # -- who someone is in Indico ----------------------------------------------
    def editors(self, *, fresh_for: float = EDITORS_FOR) -> list:
        """The event's paper editors in Indico, read again when older than *fresh_for*.

        Indico lists the accounts given the paper-editing permission, themselves
        or through a group; event managers are not in it unless they are given
        it too.
        """
        with self._editors_lock:
            when, found = self._editors
            if time.time() - when > fresh_for:
                found = self.event.client().editors()
                self._editors = (time.time(), found)
            return found

    def listed(self, indico_id: int | None) -> bool | None:
        """Whether *indico_id* was in the editing team last read (None: not read yet).

        Never reads Indico, so pages that ask often stay quick.
        """
        when, found = self._editors
        if not when or not indico_id:
            return None
        return any(person.id == int(indico_id) for person in found)

    def may_edit(self, indico_id: int | None, name: str = "", *,
                 manager: bool = False) -> str:
        """Why the Indico user *indico_id* may not edit papers: "" if Indico lets them.

        Only the conference's paper editors and editing managers in Indico
        edit (or QA) papers here. *manager*: Indico told the editor's own desk
        that their account manages the conference's editing (event managers
        too: Indico gives them every management right). Anyone else must be in
        the paper editors list; someone not in the list read last is looked up
        again at once (at most every ``EDITORS_RECHECK`` seconds), so an editor
        the chief has just added in Indico gets in without waiting.
        """
        if not indico_id:
            return ("Connect your Indico account on your desk first: the chief "
                    "editor's desk checks in Indico that you are an editor.")
        if manager:
            return ""
        indico_id = int(indico_id)
        when, known = self._editors

        def among(team) -> bool:
            return any(person.id == indico_id for person in team)

        try:
            if among(self.editors()) or among(self.editors(fresh_for=EDITORS_RECHECK)):
                return ""
        except Exception as exc:  # noqa: BLE001 — any failure: nobody is let in on it
            if known and time.time() - when < EDITORS_KEPT and among(known):
                return ""          # Indico is out of reach; they were an editor just now
            reason = str(exc) or type(exc).__name__
            return ("The chief editor's desk could not read the conference's paper "
                    f"editors from Indico ({reason}), so it cannot check that you are "
                    "one. Try again in a minute; if it keeps happening, tell the chief "
                    "editor.")
        who = f"{name} (Indico user {indico_id})" if name else f"Indico user {indico_id}"
        return (f"Your Indico account, {who}, is neither a paper editor nor an editing "
                "manager of this conference in Indico, so you cannot take papers to "
                "edit or QA them. Ask the chief editor to add you to the paper editing "
                "team in Indico (or make you an editing manager), then try again.")

    def resolve(self, indico_id: int | None, name: str) -> tuple[int | None, str]:
        """The editor's Indico user id and name, from their account or their name."""
        from src.desk.indico import same_person

        if indico_id:
            return int(indico_id), name
        try:
            for person in self.editors():
                if same_person(person.full_name, name):
                    return person.id, person.full_name
        except Exception:  # noqa: BLE001 — no list: the problem is reported below
            pass
        return None, name

    def identifier(self, user_id: int | None) -> str:
        """Indico's signed identity for *user_id* (``User:<id>:<signature>``), or "".

        Indico's assignment routes take a person only in that form, and only
        Indico can sign it. It gives it out in the paper editors list and on
        each paper's editor (the paper list this desk reads), so someone in
        neither (an editing manager not in the editing team, say) has none.
        """
        from src.desk.indico import LIVE_FILE

        if not user_id:
            return ""
        user_id = int(user_id)
        mine = f"User:{user_id}:"

        def from_team(team) -> str:
            return next((p.identifier for p in team
                         if p.id == user_id and str(p.identifier).startswith(mine)), "")

        try:
            found = from_team(self.editors())
        except Exception:  # noqa: BLE001 — the paper list may still have it
            found = ""
        if not found:
            try:
                live = json.loads((self.root / LIVE_FILE).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                live = {}
            found = next((str(e.get("editor_identifier")) for e in
                          (live.get("papers") or {}).values()
                          if isinstance(e, dict) and e.get("editor_id") == user_id
                          and str(e.get("editor_identifier") or "").startswith(mine)), "")
        if not found:
            try:
                found = from_team(self.editors(fresh_for=EDITORS_RECHECK))
            except Exception:  # noqa: BLE001
                found = ""
        return found

    def blocks(self, folder: Path, indico_id: int | None, name: str) -> str:
        """Why *name* may not take the paper at *folder*: Indico gives it to someone else."""
        from src.desk.indico import Conference, same_person

        if not self.enabled:
            return ""
        conference = Conference.open(self.root)
        assignment = conference.assignment(folder) if conference else None
        if not assignment or not assignment.editor:
            return ""
        if indico_id and assignment.editor_id == indico_id:
            return ""
        if same_person(assignment.editor, name):
            return ""
        return f"This paper is assigned to {assignment.editor}."

    # -- what the desk wants Indico to show -------------------------------------
    def want(self, paper: str, *, indico_id: int | None = None, name: str = "",
             unassign: bool = False) -> None:
        """Ask for *paper* to be assigned to an editor (or unassigned), soon."""
        if not self.enabled:
            return
        self._paper(paper, want="nobody" if unassign else "editor", indico_id=indico_id,
                    name=name, status="waiting", message="", retry=False, at=_now())
        self.wake.set()

    def _writer(self):
        from src.indico_client.assign import AssignmentWriter
        from src.indico_client.client import load_token

        if self._writer_factory:
            return self._writer_factory()
        return AssignmentWriter(base_url=self.event.url, event_id=int(self.event.event_id),
                                token=load_token())

    def _folder(self, paper: str) -> Path | None:
        from src.desk.state import submission_folders, submission_name

        for folder in submission_folders(self.root):
            if submission_name(folder) == paper:
                return folder
        return None

    def apply(self) -> None:
        """Send every waiting assignment to Indico (the background thread calls this)."""
        from src.desk.indico import Conference
        from src.indico_client.assign import AssignmentConflict
        from src.indico_client.client import IndicoError

        if not self.enabled:
            return
        # Waiting, or a problem that may have cleared up since (tried again at
        # every read of Indico).
        waiting = {p: e for p, e in self.papers().items() if e.get("status") == "waiting"
                   or (e.get("status") == "problem" and e.get("retry"))}
        if not waiting:
            return
        conference = Conference.open(self.root)
        if conference and not conference.checked_at:
            self.read()                       # the ids come from a read of Indico
            conference = Conference.open(self.root)
        for paper, entry in waiting.items():
            folder = self._folder(paper)
            assignment = conference.assignment(folder) if (conference and folder) else None
            if not assignment or not assignment.editable_id:
                self._paper(paper, status="problem", retry=False,
                            message="Indico has no submitted paper for it yet.")
                continue
            try:
                if entry.get("want") == "nobody":
                    if not assignment.editor_id:
                        self._paper(paper, status="done", message="")
                        continue
                    who, _ = self.resolve(entry.get("indico_id"), entry.get("name", ""))
                    if who and who != assignment.editor_id:
                        # Someone else has it in Indico now: theirs, leave it.
                        self._paper(paper, status="done", message="")
                        continue
                    current = (assignment.editor_identifier
                               or self.identifier(assignment.editor_id))
                    if not current:
                        self._paper(paper, status="problem", retry=False, message=(
                            f"Indico did not give this desk a signed identity for "
                            f"{assignment.editor or 'its editor'}, which it needs to "
                            "unassign them; unassign the paper in Indico."))
                        continue
                    self._writer().unassign(assignment.editable_id, current=current)
                    self._record(assignment.editable_id, None, "")
                else:
                    who, name = self.resolve(entry.get("indico_id"), entry.get("name", ""))
                    if not who:
                        self._paper(paper, status="problem", retry=False, message=(
                            f"{entry.get('name') or 'The editor'} is not in the event's "
                            "editing team in Indico under that name. Add them there, or "
                            "ask them to connect their Indico account on their desk."))
                        continue
                    if assignment.editor_id == who:
                        self._paper(paper, status="done", message="")
                        continue
                    if assignment.editor_id:
                        self._paper(paper, status="problem", retry=False, message=(
                            f"Indico gives it to {assignment.editor}; not changed."))
                        continue
                    signed = self.identifier(who)
                    if not signed:
                        self._paper(paper, status="problem", retry=True, message=(
                            f"Indico assigns a paper only to someone in its paper "
                            f"editing team, and {name or 'this editor'} is not in it "
                            "(an editing manager only, perhaps). Add them to the paper "
                            "editors in Indico (it is assigned at the next try), or "
                            "assign the paper there."))
                        continue
                    self._writer().assign(assignment.editable_id, signed)
                    self._record(assignment.editable_id, who, name, signed)
                self._paper(paper, status="done", message="", done_at=_now())
            except AssignmentConflict as exc:
                self._paper(paper, status="problem", retry=False, message=f"{exc} Not changed.")
            except IndicoError as exc:
                self._paper(paper, status="problem", retry=False, message=str(exc))
            except Exception as exc:  # noqa: BLE001 — reported on the chief's page
                self._paper(paper, status="problem", retry=False,
                            message=f"Could not reach Indico ({type(exc).__name__}).")

    def _record(self, editable_id: int, editor_id: int | None, name: str,
                identifier: str = "") -> None:
        """Note a change in the local copy of Indico's assignments at once."""
        from src.desk.indico import LIVE_FILE

        path = self.root / LIVE_FILE
        try:
            live = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for entry in (live.get("papers") or {}).values():
            if entry.get("editable_id") == editable_id:
                entry.update(editor=name, editor_id=editor_id, editor_identifier=identifier)
        files.write_text(path, json.dumps(live, indent=2, ensure_ascii=False))

    # -- reading Indico ----------------------------------------------------------
    def read(self) -> None:
        from src.desk import indico as indico_module

        try:
            indico_module.refresh(self.root, client=self.event.client())
            self.last_read, self.read_error = _now(), ""
        except Exception as exc:  # noqa: BLE001 — shown on the chief's page
            self.read_error = str(exc) or type(exc).__name__

    def _loop(self) -> None:
        while True:
            self.wake.wait(timeout=self.read_every)
            self.wake.clear()
            if not self.event.event_id or not (self.root / "index.json").is_file():
                continue
            try:
                self.apply()
            except Exception:  # noqa: BLE001 — never let the thread die
                import traceback

                traceback.print_exc()
            self.read()

    def view(self) -> dict:
        papers = self.papers()
        return {
            "enabled": self.enabled,
            "last_read": self.last_read,
            "read_error": self.read_error,
            "waiting": sorted(p for p, e in papers.items() if e.get("status") == "waiting"),
            "problems": [{"paper": p, "message": e.get("message", "")}
                         for p, e in sorted(papers.items()) if e.get("status") == "problem"],
        }
