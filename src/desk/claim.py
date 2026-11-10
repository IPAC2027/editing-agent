"""Who is editing a paper right now, so two desks never write over each other.

Indico decides which editor a paper belongs to. This is the safety net under
that decision for a pool shared over the network: a small file,
``aiagent_prescreen/claim.json``, saying which desk is editing the paper.

* An editor's first change to a paper claims it. Opening a paper to look at it
  claims nothing, so browsing the list costs nobody anything.
* While another desk holds the claim, every change is refused with a message
  saying who has it and since when. The editor can still read everything.
* Finishing a paper (or sending it back to the author) lets it go. So does
  the "Let it go" button.
* A claim does not expire on its own: an editor may hold a paper for days.
  Anyone can take a paper over, after a confirmation that names the holder —
  in one room that is a conversation, not a protocol.

The claim file is created with ``O_EXCL``: the file server, not the desk,
decides who was first, so two editors clicking at the same moment cannot both
win.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from src.desk import files
from src.desk.me import Me

CLAIM_FILENAME = "claim.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Claim(BaseModel):
    desk_id: str = ""
    name: str = ""
    machine: str = ""
    since: str = ""
    mode: str = "edit"          # edit | qa: what the paper was taken for
    indico_id: int | None = None  # the taker's Indico user, on the chief's desk

    @property
    def who(self) -> str:
        if self.name:
            return self.name
        if self.machine:
            return f"Someone on {self.machine}"
        return "Another editor"

    def view(self, desk_id: str) -> dict:
        return {"state": "mine" if self.desk_id and self.desk_id == desk_id else "other",
                "who": self.who, "machine": self.machine, "since": self.since,
                "mode": self.mode}


class Held(Exception):
    """A change was refused because another desk is editing the paper."""

    def __init__(self, claim: Claim, desk_id: str = "") -> None:
        self.claim = claim
        self.view = claim.view(desk_id)
        since = f" (since {claim.since.replace('T', ' ').rstrip('Z')} UTC)" if claim.since else ""
        super().__init__(
            f"{claim.who} is editing this paper{since}. Nothing was saved. You can "
            "still read it; if they have finished with it, take it over."
        )


def path_for(folder: Path) -> Path:
    return Path(folder) / "aiagent_prescreen" / CLAIM_FILENAME


def current(folder: Path) -> Claim | None:
    """The claim on *folder*, or None when nobody is editing it.

    A claim file that cannot be read still counts as a claim: it is most often
    one being written at this very moment, and treating it as free would let a
    second desk in. A stuck one is cleared by taking the paper over.
    """
    path = path_for(folder)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return Claim()
    try:
        return Claim.model_validate(json.loads(text))
    except Exception:  # noqa: BLE001
        return Claim()


def view(folder: Path, desk_id: str) -> dict | None:
    """What the page shows: None when free, else who holds it."""
    claim = current(folder)
    return claim.view(desk_id) if claim else None


def _record(me: Me, mode: str = "edit", indico_id: int | None = None) -> Claim:
    return Claim(desk_id=me.desk_id, name=me.name, machine=me.machine, since=_now(),
                 mode=mode, indico_id=indico_id)


def take(folder: Path, me: Me, *, mode: str = "edit",
         indico_id: int | None = None) -> Claim:
    """Claim *folder* for *me*; fine if *me* already has it; Held if someone else does."""
    path = path_for(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        record = _record(me, mode, indico_id)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            existing = current(folder)
            if existing is None:
                continue  # let go between our attempt and our look: try again
            if existing.desk_id == me.desk_id:
                if existing.name != me.name and me.name:
                    return take_over(folder, me, since=existing.since, mode=existing.mode)
                return existing
            raise Held(existing, me.desk_id) from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(record.model_dump_json())
            handle.flush()
            os.fsync(handle.fileno())
        return record
    existing = current(folder) or Claim()
    raise Held(existing, me.desk_id)


def take_over(folder: Path, me: Me, *, since: str = "", mode: str = "edit") -> Claim:
    """Make *me* the holder whoever held it before."""
    record = _record(me, mode)
    if since:
        record.since = since
    files.write_text(path_for(folder), record.model_dump_json())
    return record


def release(folder: Path, me: Me) -> bool:
    """Let *folder* go, if *me* holds it. Returns whether anything was released."""
    existing = current(folder)
    if existing is None or existing.desk_id != me.desk_id:
        return False
    try:
        path_for(folder).unlink()
    except FileNotFoundError:
        pass
    return True
