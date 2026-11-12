"""The pool on the chief editor's computer, and the door editors reach it by.

The chief's desk holds every paper. Editors' desks never open that folder:
they talk to this small server over the network, and it does everything to
the pool on their behalf.

* An editor **takes** a paper: the claim is made here (``claim.take``, the
  same ``O_EXCL`` file the chief's own desk uses), so two editors, or an
  editor and the chief, can never both have it. Editors are known by their
  Indico account (their desk sends its user id and name, never the token): a
  desk without one cannot take a paper, and neither can an account that is
  neither one of the conference's paper editors in Indico (the chief's desk
  reads that list) nor one of its editing managers (Indico tells the editor's
  own desk, which says so): ``IndicoSync.may_edit``.
* The editor **downloads** a copy and edits it on their own computer.
* As they work their desk **sends** the paper's review files back
  (``aiagent_prescreen/``, nothing else). Only the desk holding the claim may
  send; each send keeps a backup of what it replaces.
* Finishing a paper, or **giving it up**, lets the claim go. A paper given up
  unfinished is announced on the chief's page, with the editor's reason, and
  is free for the next editor at once.

The chief's page reads the same claim files, so it shows who is editing which
paper next to who has it in Indico. This module never writes to Indico; the
chief's ``IndicoSync`` follows the claims there.

**Who holds a paper** (:meth:`Pool.holder`) is either kind of taking: a claim
here, or an editor Indico shows for it (someone who took it in Indico itself,
or whom the chief assigned there). Either way nobody else may take it to edit
it, whether or not the chief's desk writes to Indico; Indico's assignments are
read again just before a paper is handed out. Only the chief frees it
(:meth:`Pool.free`): the claim goes, and Indico's editor is unassigned there
when the desk keeps Indico in step, or, when it does not, is no longer honoured
here until Indico shows someone else (the chief unassigns them in Indico).

While the door is open, ``.pool_door.json`` in the folder says so, and no
other desk opens the folder directly (:func:`door_open`).

Editors get in with a **join code** the chief's page shows, sent as a bearer
token. The server listens on the local network, separately from the chief's
own page, which still answers this computer only.
"""

from __future__ import annotations

import atexit
import hmac
import json
import os
import re
import secrets
import socket
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.desk import bundle, files
from src.desk import claim as claim_module
from src.desk import me as me_module
from src.desk.me import Me

POOL_PORT = 8770
CODE_SETTING = "pool_code"
ACTIVITY_FILE = "pool_activity.json"
BACKUP_DIR = ".pool_backups"
KEEP_BACKUPS = 5
#: In the pool folder while the chief's desk shares it: which port, which process.
DOOR_FILE = ".pool_door.json"
#: How many "given up" notices the chief's page keeps.
GIVEN_UP_KEPT = 50
OUT_DIR = "aiagent_prescreen"
#: Root-level files an editor's copy needs to know the conference by.
CONFERENCE_FILES = ("index.json", "indico_assignments.json", "indico_abstracts.json")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_code() -> str:
    """Twelve characters an editor can read out and type: no 0/o, 1/l/i."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


def join_code(home: Path | None = None) -> str:
    """The chief's join code, made once and kept with the chief's settings."""
    code = str(me_module.load_settings(home).get(CODE_SETTING) or "")
    if not code:
        code = make_code()
        me_module.update_settings(home, **{CODE_SETTING: code})
    return code


def lan_addresses() -> list[str]:
    """This computer's addresses on the local network, best guess first."""
    found: list[str] = []
    try:
        # Connecting a UDP socket sends nothing; it only picks the interface
        # that would be used, whose address is the one others can reach.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            if address not in found:
                found.append(address)
    except OSError:
        pass
    return [a for a in found if not a.startswith("127.")] or ["127.0.0.1"]


class NotHeld(Exception):
    """A send or download from a desk that does not hold the paper (HTTP 409)."""


class Pool:
    """The papers folder on the chief's computer, as editors' desks see it."""

    def __init__(self, root: Path, *, code: str, port: int = POOL_PORT,
                 addresses: list[str] | None = None, sync=None,
                 local_only: bool = False) -> None:
        self.root = Path(root).resolve()
        self.code = code
        self.port = port
        # --no-share: the door answers this computer only, which is where the
        # chief's own editing desk is.
        self.local_only = local_only
        self.addresses = ["127.0.0.1"] if local_only and addresses is None else addresses
        self.lock = threading.Lock()
        # The chief's own desk: an editor's desk must have settings of its own.
        self.own_desk_id = me_module.current().desk_id
        self.editors: dict[str, dict] = {}       # desk id -> who, last seen
        # desk id -> the editor's Indico user, as their desk vouched for it
        # with their own token ({"id", "name"}); none for an editor who has
        # not connected an Indico account (then their name is matched).
        self.identities: dict[str, dict] = {}
        self.sync = sync                         # src.desk.indico_sync.IndicoSync

    # -- papers ------------------------------------------------------------
    def folder_for(self, paper: str) -> Path:
        from src.desk.state import submission_folders, submission_name

        for folder in submission_folders(self.root):
            if submission_name(folder) == paper and folder != self.root:
                return folder
        raise LookupError(f"there is no paper {paper!r} on the chief's desk")

    def top(self, folder: Path) -> Path:
        """The paper's own folder in the pool (``<root>/MOP001``)."""
        return self.root / folder.relative_to(self.root).parts[0]

    def indico_user(self, me: Me) -> tuple[int | None, str]:
        ident = self.identities.get(me.desk_id) or {}
        return ident.get("id"), ident.get("name") or me.name

    def manages_editing(self, me: Me) -> bool:
        """Whether *me*'s desk says Indico has them as an editing manager."""
        return bool((self.identities.get(me.desk_id) or {}).get("manager"))

    def may_edit(self, me: Me) -> str:
        """Why *me* may not take papers: "" when Indico has them as a paper editor
        or an editing manager.

        The chief's desk always has Indico behind it (``--manage``); a pool
        without it (tests) has nobody to ask.
        """
        if self.sync is None:
            return ""
        return self.sync.may_edit(*self.indico_user(me), manager=self.manages_editing(me))

    def you(self, me: Me) -> dict:
        """Who the chief's desk takes *me* for, and whether they may take papers."""
        indico_id, name = self.indico_user(me)
        why = self.may_edit(me) if indico_id else ""
        role = ("" if why or not indico_id or self.sync is None
                else "editing manager" if self.manages_editing(me) else "paper editor")
        return {"indico_id": indico_id, "name": name if indico_id else "",
                "may_edit": bool(indico_id) and not why, "why": why, "role": role}

    def papers(self, desk_id: str = "", me: Me | None = None) -> list[dict]:
        from src.desk.indico import same_person

        from src.desk import plain
        from src.desk.indico import Conference
        from src.desk.state import (TAKE_FOR, ReviewState, has_edited, is_pulled_conference,
                                    qa_view, stage_of, submission_folders, submission_name)

        conference = Conference.open(self.root) if is_pulled_conference(self.root) else None
        activity = self.activity().get("papers", {})
        rows = []
        for folder in submission_folders(self.root):
            if folder == self.root:
                continue
            name = submission_name(folder)
            report = _read_json(folder / OUT_DIR / "report.json")
            state = ReviewState.load(folder)
            held = claim_module.current(folder)
            assignment = conference.assignment(folder) if conference else None
            indico_id, indico_name = self.indico_user(me) if me else (None, "")
            yours = bool(assignment and assignment.editor and (
                (indico_id and assignment.editor_id == indico_id)
                or same_person(assignment.editor, indico_name)))
            stage = stage_of(state, prepared=bool(report))
            edited_it = bool(me) and has_edited(state, indico_id, indico_name)
            take = "" if held else TAKE_FOR.get(stage, "")
            if take == "qa" and edited_it:
                take = ""                         # someone else does its QA
            # Indico's assignment decides who may edit it; anyone else may QA it.
            blocked = (self.indico_blocks(folder, indico_id, indico_name,
                                          conference=conference, activity=activity)
                       if (me and held is None and TAKE_FOR.get(stage) == "edit") else "")
            rows.append({
                "paper": name,
                "paper_id": report.get("paper_id") or name,
                "title": plain.readable_title(report.get("title", "")),
                "prepared": bool(report),
                "status": state.status,
                "status_word": state.status_word if report else "Not prepared yet",
                "stage": stage,
                "take": take,
                "edited_by_you": edited_it,
                "editor": state.editor,
                "qa": qa_view(state),
                "claim": None if held is None else {
                    "who": held.who, "machine": held.machine, "since": held.since,
                    "mode": held.mode,
                    "mine": bool(desk_id) and held.desk_id == desk_id},
                "indico": None if assignment is None else {
                    "editor": assignment.editor, "state": assignment.state,
                    "yours": yours},
                "blocked": blocked,
                "received_at": activity.get(name, {}).get("received_at", ""),
            })
        return rows

    def conference(self) -> dict[str, dict]:
        found = {name: _read_json(self.root / name) for name in CONFERENCE_FILES
                 if (self.root / name).is_file()}
        # Indico's signed identities are for the chief's desk's requests only.
        for entry in (found.get("indico_assignments.json", {}).get("papers") or {}).values():
            if isinstance(entry, dict):
                entry.pop("editor_identifier", None)
        return found

    # -- what editors do ------------------------------------------------------
    def take(self, paper: str, me: Me, mode: str = "edit") -> dict:
        """*me* takes *paper* to edit it (``edit``) or to QA it (``qa``).

        Which one is decided by where the paper is (``state.stage_of``): a
        paper not edited yet, or whose QA failed, is taken to edit; an edited
        one is taken for QA. Only taking to edit makes the editor its editor
        (here and, with the sync on, in Indico).
        """
        from src.desk.state import TAKE_FOR, ReviewState, has_edited, stage_of

        if mode not in ("edit", "qa"):
            raise ValueError("a paper is taken to edit it or to QA it")
        indico_id, indico_name = self.indico_user(me)
        if not indico_id:
            raise ValueError("connect your Indico account on your desk first (paste "
                             "your Indico token there): the chief editor's desk knows "
                             "editors by their Indico account")
        if not me.name:
            me = replace(me, name=indico_name or f"Indico user {indico_id}")
        folder = self.folder_for(paper)
        from src.desk.reprepare import is_busy

        if is_busy(folder):
            raise ValueError(f"{paper} is being prepared again on the chief editor's desk; "
                             "try again in a minute")
        if not (folder / OUT_DIR / "report.json").is_file():
            raise ValueError(f"{paper} is not prepared yet on the chief editor's desk")
        held_now = claim_module.current(folder)
        if held_now is None or held_now.desk_id != me.desk_id:
            # Indico decides who edits: its paper editors, nobody else.
            refused = self.may_edit(me)
            if refused:
                raise ValueError(refused)
            state = ReviewState.load(folder)
            stage = stage_of(state)
            if TAKE_FOR.get(stage) != mode:
                raise ValueError(_cannot_take(paper, stage, mode))
            if mode == "qa" and has_edited(state, indico_id, indico_name):
                raise ValueError(f"You edited {paper}, so its QA is done by another "
                                 "editor.")
        if mode == "edit" and held_now is None:
            if self.sync:
                self.sync.ensure_fresh()          # someone may have taken it in Indico
            blocked = self.indico_blocks(folder, indico_id, indico_name)
            if blocked:
                raise ValueError(blocked + " Ask the chief editor if it should be yours.")
        with self.lock:
            was_free = claim_module.current(folder) is None
            held = claim_module.take(folder, me, mode=mode,     # Held if someone
                                     indico_id=indico_id)       # else has it
            if was_free and mode == "edit":
                # Whoever picks a free paper up to edit it is its editor from
                # now on, as on the chief's own desk.
                review = ReviewState.load(folder)
                review.editor = me.name
                review.save(folder)
            self._note(paper, taken_at=_now(), by=me.name, taken_for=held.mode,
                       freed_indico=None)
        if self.sync and held.mode == "edit":
            self.sync.want(paper, indico_id=indico_id, name=indico_name)
        return {"paper": paper, "since": held.since, "mode": held.mode,
                "path": folder.relative_to(self.root).as_posix()}

    def assign_held(self) -> list[str]:
        """Ask Indico to show each paper being edited here as its editor's.

        For when the chief switches the sync on: papers taken while it was off
        were never sent. Indico's own conflict check still decides; a paper
        Indico gives to someone else is left alone and reported.
        """
        from src.desk.state import submission_folders, submission_name

        if not (self.sync and self.sync.enabled):
            return []
        waiting = {p for p, e in self.sync.papers().items() if e.get("status") == "waiting"}
        asked = []
        for folder in submission_folders(self.root):
            if folder == self.root:
                continue
            held = claim_module.current(folder)
            paper = submission_name(folder)
            if held is None or held.mode != "edit" or paper in waiting:
                continue
            ident = self.identities.get(held.desk_id) or {}
            self.sync.want(paper, indico_id=held.indico_id or ident.get("id"),
                           name=ident.get("name") or held.name)
            asked.append(paper)
        return asked

    def package(self, paper: str, me: Me) -> bytes:
        """The whole paper, for the desk that holds it."""
        folder = self.folder_for(paper)
        self._require(folder, me)
        return bundle.pack(self.root, self.top(folder))

    def receive(self, paper: str, me: Me, data: bytes, *, release: bool = False,
                reason: str = "") -> dict:
        """Put the editor's review files into the pool, replacing what was there."""
        folder = self.folder_for(paper)
        prefix = folder.relative_to(self.root).as_posix() + f"/{OUT_DIR}/"
        incoming = bundle.read(data, prefix)
        from src.desk.state import STATE_FILENAME

        if STATE_FILENAME not in incoming:
            raise bundle.BadBundle("it holds no review state")
        from src.desk.state import ReviewState

        with self.lock:
            self._require(folder, me)
            held = claim_module.current(folder)
            before = ReviewState.load(folder)
            out = folder / OUT_DIR
            self._backup(paper, out)
            bundle.write_tree(out, incoming)
            self._edited(folder, me, before,
                         editing=held is not None and held.mode == "edit")
            # What the editor's copy no longer has goes too (a paper prepared
            # again leaves different files); the claim stays.
            for path in sorted(out.rglob("*"), reverse=True):
                rel = path.relative_to(out).as_posix()
                if path.is_file() and rel not in incoming and path.name != claim_module.CLAIM_FILENAME:
                    path.unlink()
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            received = _now()
            self._note(paper, received_at=received, by=me.name)
            released = claim_module.release(folder, me) if release else False
        if released:
            self._released(paper, folder, me, reason, mode=held.mode if held else "edit")
        return {"paper": paper, "received_at": received, "released": released}

    def _edited(self, folder: Path, me: Me, before, *, editing: bool) -> None:
        """Keep the record of who edited the paper across a send.

        The editor's copy never sees who the chief's desk noted since it was
        downloaded, so those are kept; and *me* is added when this send, from
        a desk editing the paper, changed its editing (a paper given up
        untouched has not been edited by them).
        """
        from src.desk.state import ReviewState, work_of

        review = ReviewState.load(folder)
        merged = list(review.edited_by)
        for entry in before.edited_by:
            if entry not in merged:
                merged.append(entry)
        if editing and work_of(review) != work_of(before):
            indico_id, name = self.indico_user(me)
            if not any((indico_id and e.get("id") == indico_id)
                       or (not indico_id and e.get("name") == name) for e in merged):
                merged.append({"id": indico_id, "name": name})
        if merged != review.edited_by:
            review.edited_by = merged
            review.save(folder)

    def release(self, paper: str, me: Me, reason: str = "") -> bool:
        folder = self.folder_for(paper)
        with self.lock:
            held = claim_module.current(folder)
            released = claim_module.release(folder, me)
        if released:
            self._released(paper, folder, me, reason, mode=held.mode if held else "edit")
        return released

    def _released(self, paper: str, folder: Path, me: Me, reason: str = "", *,
                  mode: str = "edit") -> None:
        """Let go of: a finished paper stays as it is; one given up unfinished is
        announced on the chief's page and unassigned in Indico, so the next
        editor can take it. A QA given back with its verdict is finished too
        (a failed one goes back to editing, with the same Indico editor); one
        given up without a verdict is announced, and Indico is not touched."""
        from src.desk.state import ReviewState

        state = ReviewState.load(folder)
        if mode == "qa":
            if state.status == "done" and not state.qa.status:
                self._given_up(paper, me, reason, mode="qa")
            return
        if state.status in ("done", "needs_author"):
            return
        self._given_up(paper, me, reason)
        indico_id, indico_name = self.indico_user(me)
        # Giving it up here gives it up in Indico too: if Indico shows them, the
        # desk stops honouring that (and unassigns them there when it may).
        from src.desk.indico import same_person

        assignment = self._indico_holder(folder, paper)
        if assignment is not None and (
                (indico_id and assignment.editor_id == indico_id)
                or same_person(assignment.editor, indico_name or me.name)):
            self._note(paper, freed_indico={"editor": assignment.editor,
                                            "editor_id": assignment.editor_id, "at": _now()})
        if self.sync:
            self.sync.want(paper, indico_id=indico_id, name=indico_name, unassign=True)

    # -- papers given up, for the chief's page -------------------------------
    def _given_up(self, paper: str, me: Me, reason: str, *, mode: str = "edit") -> None:
        reason = " ".join(str(reason or "").split())[:500]
        with self.lock:
            activity = self.activity()
            notices = activity.setdefault("given_up", [])
            notices.append({"id": secrets.token_hex(6), "paper": paper, "who": me.name,
                            "machine": me.machine, "reason": reason, "at": _now(),
                            "mode": mode, "dismissed": False})
            activity["given_up"] = notices[-GIVEN_UP_KEPT:]
            activity.setdefault("papers", {}).setdefault(paper, {}).update(
                given_up_at=_now(), given_up_by=me.name)
            files.write_text(self.root / ACTIVITY_FILE, json.dumps(activity, indent=2))

    def given_up(self) -> list[dict]:
        """Papers editors gave up that the chief has not dismissed yet, newest first."""
        notices = self.activity().get("given_up") or []
        return [n for n in reversed(notices) if isinstance(n, dict) and not n.get("dismissed")]

    def dismiss(self, notice: str) -> None:
        """The chief has seen a notice (or, with ``"all"``, every one)."""
        with self.lock:
            activity = self.activity()
            for entry in activity.get("given_up") or []:
                if notice == "all" or entry.get("id") == notice:
                    entry["dismissed"] = True
            files.write_text(self.root / ACTIVITY_FILE, json.dumps(activity, indent=2))

    # -- what the chief does --------------------------------------------------
    def free(self, paper: str) -> dict | None:
        """Free *paper* from whoever holds it, here or in Indico, so any editor can take it.

        A claim here goes; their desk hears the next time it sends, and work it
        had not sent yet stays on their computer. An editor Indico shows for it
        (unfinished) is unassigned there when the desk keeps Indico in step;
        when it does not, the desk stops honouring that assignment (until Indico
        shows nobody, or someone else) and says so, for the chief to unassign
        them in Indico. Returns who held it, or None if nobody did.
        """
        from src.desk.state import ReviewState

        folder = self.folder_for(paper)
        with self.lock:
            held = claim_module.current(folder)
            in_indico = self._indico_holder(folder, paper)
            if held is None and in_indico is None:
                return None
            if held is not None:
                try:
                    claim_module.path_for(folder).unlink()
                except FileNotFoundError:
                    pass
            facts = {"freed_at": _now(), "freed_from": held.who if held else in_indico.editor}
            if in_indico is not None:
                facts["freed_indico"] = {"editor": in_indico.editor,
                                         "editor_id": in_indico.editor_id, "at": _now()}
            self._note(paper, **facts)
        unfinished = ReviewState.load(folder).status not in ("done", "needs_author")
        indico = ""
        if in_indico is not None:
            indico = "still assigned"
            if self.sync and self.sync.enabled and unfinished:
                self.sync.want(paper, indico_id=in_indico.editor_id, name=in_indico.editor,
                               unassign=True)
                indico = "unassigning"
        elif self.sync and held is not None and held.mode == "edit" and unfinished:
            ident = self.identities.get(held.desk_id) or {}
            self.sync.want(paper, indico_id=ident.get("id"),
                           name=ident.get("name") or held.name, unassign=True)
        return {"paper": paper, "who": held.who if held else in_indico.editor,
                "mode": held.mode if held else "edit", "taken": "here" if held else "indico",
                "indico_editor": in_indico.editor if in_indico else "", "indico": indico}

    # -- who holds a paper: a claim here, or Indico's editor ---------------------
    def _indico_holder(self, folder: Path, paper: str, *, conference=None,
                       activity: dict | None = None):
        """Indico's assignment for the paper, when it gives it to an editor the chief
        has not freed it from; else None. A freed editor is forgotten once Indico
        shows nobody (so taking it there again holds it again)."""
        from src.desk.indico import Conference, same_person
        from src.desk.state import is_pulled_conference

        if conference is None:
            if not is_pulled_conference(self.root):
                return None
            conference = Conference.open(self.root)
        assignment = conference.assignment(folder) if conference else None
        activity = self.activity().get("papers", {}) if activity is None else activity
        freed = (activity.get(paper) or {}).get("freed_indico")
        if assignment is None or not assignment.editor:
            if freed:
                self._note(paper, freed_indico=None)
            return None
        if freed and ((freed.get("editor_id") and freed.get("editor_id") == assignment.editor_id)
                      or same_person(freed.get("editor", ""), assignment.editor)):
            return None
        return assignment

    def indico_blocks(self, folder: Path, indico_id: int | None, name: str, *,
                      conference=None, activity: dict | None = None) -> str:
        """Why *name* may not take the paper to edit it: Indico gives it to someone else."""
        from src.desk.indico import same_person
        from src.desk.state import submission_name

        assignment = self._indico_holder(folder, submission_name(folder),
                                         conference=conference, activity=activity)
        if assignment is None:
            return ""
        if indico_id and assignment.editor_id == indico_id:
            return ""
        if same_person(assignment.editor, name):
            return ""
        return f"This paper is assigned to {assignment.editor} in Indico."

    def holder(self, folder: Path, *, conference=None, activity: dict | None = None) -> dict:
        """Who holds the paper, for the chief's page.

        ``taken`` is ``here`` (a claim on this desk), ``indico`` (an editor in
        Indico, nobody here), ``both`` (the same person both ways), ``conflict``
        (one person here, another in Indico) or ``""`` (free). ``freed`` names an
        Indico editor the chief freed the paper from who is still assigned there.
        """
        from src.desk.indico import Conference, same_person
        from src.desk.state import is_pulled_conference, submission_name

        paper = submission_name(folder)
        if conference is None and is_pulled_conference(self.root):
            conference = Conference.open(self.root)
        activity = self.activity().get("papers", {}) if activity is None else activity
        held = claim_module.current(folder)
        in_indico = self._indico_holder(folder, paper, conference=conference,
                                        activity=activity)
        assignment = conference.assignment(folder) if conference else None
        freed = (activity.get(paper) or {}).get("freed_indico")
        here = None
        if held is not None:
            ident = self.identities.get(held.desk_id) or {}
            here = {"who": held.who, "mode": held.mode, "since": held.since,
                    "indico_id": held.indico_id or ident.get("id")}
        taken = ""
        if here and in_indico:
            same = ((here["indico_id"] and here["indico_id"] == in_indico.editor_id)
                    or same_person(here["who"], in_indico.editor))
            taken = "both" if same else ("conflict" if here["mode"] == "edit" else "here")
        elif here:
            taken = "here"
        elif in_indico:
            taken = "indico"
        return {
            "taken": taken,
            "here": here,
            "indico": in_indico.editor if in_indico else "",
            "freed": (assignment.editor if assignment and assignment.editor and freed
                      and in_indico is None else ""),
            "can_free": bool(here or in_indico),
        }

    def _require(self, folder: Path, me: Me) -> None:
        held = claim_module.current(folder)
        if held is None:
            raise NotHeld("This paper is no longer yours on the chief editor's desk (it "
                          "was given back, finished, or freed by the chief editor). "
                          "Your copy is kept on this computer; take the paper again "
                          "to send it.")
        if held.desk_id != me.desk_id:
            raise NotHeld(f"{held.who} has this paper on the chief editor's desk now, so "
                          "your changes were not sent. Your copy is kept on this computer.")

    # -- records -----------------------------------------------------------
    def activity(self) -> dict:
        return _read_json(self.root / ACTIVITY_FILE)

    def _note(self, paper: str, **facts) -> None:
        activity = self.activity()
        activity.setdefault("papers", {}).setdefault(paper, {}).update(facts)
        files.write_text(self.root / ACTIVITY_FILE, json.dumps(activity, indent=2))

    def _backup(self, paper: str, out: Path) -> None:
        if not out.is_dir():
            return
        target = self.root / BACKUP_DIR / paper
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (target / f"{stamp}.zip").write_bytes(bundle.pack(out.parent, out))
        for old in sorted(target.glob("*.zip"))[:-KEEP_BACKUPS]:
            old.unlink()

    def seen(self, me: Me) -> None:
        ident = self.identities.get(me.desk_id) or {}
        self.editors[me.desk_id] = {"name": me.name, "machine": me.machine,
                                    "indico_id": ident.get("id"),
                                    "editing_manager": bool(ident.get("manager")),
                                    "last_seen": _now()}

    def view(self) -> dict:
        """What the chief's page shows about the door editors come in by."""
        addresses = self.addresses if self.addresses is not None else lan_addresses()
        return {"code": self.code, "port": self.port, "local_only": self.local_only,
                "addresses": [f"http://{a}:{self.port}" for a in addresses],
                "given_up": self.given_up(),
                "editors": sorted((self._editor_view(e) for e in self.editors.values()),
                                  key=lambda e: e["last_seen"], reverse=True)}

    def _editor_view(self, entry: dict) -> dict:
        # From the editing team read last (no request to Indico here):
        # True / False, or None when it is not known yet.
        listed = self.sync.listed(entry.get("indico_id")) if self.sync else None
        return {**entry, "paper_editor": listed}


def _cannot_take(paper: str, stage: str, mode: str) -> str:
    """Why *paper*, at *stage*, cannot be taken for *mode*."""
    if stage == "qa_passed":
        return f"{paper} is edited and its QA is done: there is nothing left to take it for."
    if mode == "qa":
        return f"{paper} has not been edited yet, so it cannot be QA'd: take it to edit it."
    return f"{paper} has been edited and is waiting for its QA: take it for QA instead."


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# The door: a small HTTP server for editors' desks
# ---------------------------------------------------------------------------

_DESK_ID = re.compile(r"^[0-9a-f]{16,64}$")
MAX_JSON = 1 << 20


class PoolHandler(BaseHTTPRequestHandler):
    """Answers editors' desks only, and only with the join code.

    Browsers cannot use it: every request needs an ``Authorization`` header,
    which a page from elsewhere can only send after a CORS preflight that this
    server never approves.
    """

    server_version = "JACoWPool/1.0"

    def __init__(self, *args, pool: Pool, **kwargs) -> None:
        self.pool = pool
        super().__init__(*args, **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, message: str, status: HTTPStatus) -> None:
        self._json({"error": message}, status)

    def _visitor(self) -> Me | None:
        """The editor's desk, or None (and an answer sent) if it may not come in."""
        given = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), self.pool.code.encode()):
            time.sleep(0.5)     # a wrong code costs time, so guessing one is slow
            self.close_connection = True
            self._error("The chief editor's desk did not accept that join code.",
                        HTTPStatus.UNAUTHORIZED)
            return None
        desk_id = (self.headers.get("X-Desk-Id") or "").strip().lower()
        if not _DESK_ID.match(desk_id):
            self._error("no desk id was sent", HTTPStatus.BAD_REQUEST)
            return None
        if desk_id == self.pool.own_desk_id:
            self._error("This desk has the chief editor's own desk id, so it would be "
                        "the chief, not an editor. Stop it and start it again with "
                        "--join: on the chief's computer it then keeps an editor's "
                        "settings of its own. If its settings were copied from the "
                        "chief's computer, delete desk.json in the copy first.",
                        HTTPStatus.FORBIDDEN)
            return None
        # The editor is who their Indico account says, when their desk has
        # one; the name typed into an older desk is only a fallback.
        indico_id = (self.headers.get("X-Indico-User-Id") or "").strip()
        indico_name = unquote(self.headers.get("X-Indico-User-Name") or "").strip()[:120]
        typed = unquote(self.headers.get("X-Desk-Name") or "").strip()[:120]
        if indico_id.isdigit():
            # Whether Indico told the editor's own token that it manages the
            # conference's editing (Indico lists editing managers to nobody).
            manager = (self.headers.get("X-Indico-Editing-Manager") or "").strip() == "1"
            self.pool.identities[desk_id] = {"id": int(indico_id), "name": indico_name,
                                             "manager": manager}
        else:
            self.pool.identities.pop(desk_id, None)
            indico_name = ""
        me = Me(desk_id=desk_id, name=indico_name or typed,
                machine=unquote(self.headers.get("X-Desk-Machine") or "").strip()[:80])
        self.pool.seen(me)
        return me

    def _length(self, limit: int) -> int | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > limit:
            self.close_connection = True
            self._error("that request is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        return length

    def _dispatch(self, work) -> None:
        try:
            work()
        except claim_module.Held as exc:
            self._json({"error": str(exc), "claim": {"who": exc.claim.who,
                        "since": exc.claim.since}}, HTTPStatus.CONFLICT)
        except NotHeld as exc:
            self._error(str(exc), HTTPStatus.CONFLICT)
        except LookupError as exc:
            self._error(str(exc).strip("'\""), HTTPStatus.NOT_FOUND)
        except bundle.BadBundle as exc:
            self._error(f"The paper sent was refused: {exc}. Nothing was changed.",
                        HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            self._error(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            self._error(f"something went wrong on the chief's desk: {exc}",
                        HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self) -> None:  # noqa: N802
        me = self._visitor()
        if me is None:
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        paper = (query.get("paper") or [""])[0]

        def work() -> None:
            if parsed.path == "/pool/hello":
                conference = self.pool.conference().get("index.json", {})
                self._json({"pool": self.pool.root.name,
                            "event": conference.get("event_id"),
                            "indico": conference.get("base_url", "")})
            elif parsed.path == "/pool/papers":
                self._json({"papers": self.pool.papers(me.desk_id, me),
                            "you": self.pool.you(me)})
            elif parsed.path == "/pool/conference":
                self._json({"files": self.pool.conference()})
            elif parsed.path == "/pool/paper":
                self._send(HTTPStatus.OK, self.pool.package(paper, me), "application/zip")
            else:
                self._error("unknown address", HTTPStatus.NOT_FOUND)

        self._dispatch(work)

    def do_POST(self) -> None:  # noqa: N802
        me = self._visitor()
        if me is None:
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        sending = parsed.path == "/pool/send"
        length = self._length(bundle.MAX_BYTES if sending else MAX_JSON)
        if length is None:
            return
        data = self.rfile.read(length) if length else b""

        def work() -> None:
            if sending:
                paper = (query.get("paper") or [""])[0]
                release = (query.get("release") or ["0"])[0] == "1"
                reason = (query.get("reason") or [""])[0]
                self._json(self.pool.receive(paper, me, data, release=release,
                                             reason=reason))
                return
            try:
                body = json.loads(data.decode("utf-8")) if data else {}
            except (ValueError, UnicodeDecodeError):
                raise ValueError("that request was not JSON") from None
            paper = str(body.get("paper", ""))
            if parsed.path == "/pool/take":
                self._json(self.pool.take(paper, me, str(body.get("mode") or "edit")))
            elif parsed.path == "/pool/release":
                self._json({"released": self.pool.release(paper, me,
                                                          str(body.get("reason", "")))})
            else:
                self._error("unknown address", HTTPStatus.NOT_FOUND)

        self._dispatch(work)


def start(pool: Pool, *, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    """Open the door in a background thread; the port actually used is in ``pool.port``."""
    last_error: OSError | None = None
    for candidate in range(pool.port, pool.port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), partial(PoolHandler, pool=pool))
        except OSError as exc:
            last_error = exc
            continue
        server.daemon_threads = True
        pool.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _mark_door(pool)
        return server
    raise OSError(f"could not open the editors' door: {last_error}")


def _mark_door(pool: Pool) -> None:
    """Note in the folder that this desk shares it, until the desk closes."""
    path = pool.root / DOOR_FILE
    mine = {"pid": os.getpid(), "port": pool.port, "since": _now()}
    try:
        files.write_text(path, json.dumps(mine, indent=2))
    except OSError:
        return

    def unmark() -> None:
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
                path.unlink()
        except (OSError, ValueError):
            pass

    atexit.register(unmark)


def door_open(root: Path) -> dict | None:
    """The chief's desk sharing *root* right now, from another process, if any.

    Read from ``.pool_door.json`` and checked by knocking on that port, so a
    note left behind by a desk that crashed does not count.
    """
    try:
        door = json.loads((Path(root) / DOOR_FILE).read_text(encoding="utf-8"))
        pid, port = int(door.get("pid", 0)), int(door.get("port", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    if pid == os.getpid() or not 0 < port < 65536:
        return None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return door
    except OSError:
        return None
