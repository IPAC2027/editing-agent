"""Who has each paper in Indico, as the desk shows it.

Indico gives every paper to at most one editor at a time. The desk works on
copies, so nothing stops two editors preparing, deciding and writing a letter
for the same paper on two machines — an hour of work thrown away at best, two
sets of corrections reaching one author at worst. So every row in the worklist
and every open paper says who holds it in Indico.

Two sources, the newer one wins:

* the ``manifest.json`` that ``indico-pull`` left beside each paper — always
  there, but only as fresh as the pull;
* a live check (:func:`refresh`) — one read-only GET of the event's paper list,
  remembered beside the papers in ``indico_assignments.json``. The pull's own
  files are never rewritten: they record what Indico said when the papers were
  fetched, and the corpus measurements read them as that.

"Yours" is decided by name: the name typed at the top of the desk against the
editor's full name in Indico, ignoring case and accents. The desk has no other
way to know who is sitting in front of it, and within one conference's editors
a name is unambiguous.
"""

from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

PULL_INDEX = "index.json"
MANIFEST = "manifest.json"
LIVE_FILE = "indico_assignments.json"


class Assignment(BaseModel):
    """Who holds one paper in Indico, relative to whoever is at this desk."""

    contribution_id: int
    editor: str = ""                 # Indico's full name; "" when nobody has taken it
    state: str = ""                  # Indico's editable state, e.g. "ready_for_review"
    holder: str = "nobody"           # you | other | nobody
    url: str = ""                    # the paper's page in Indico
    source: str = "pull"             # pull | indico — where `editor` came from
    as_of: str = ""                  # when that source said so


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _mtime(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat(timespec="seconds")


def _person(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name or "")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(folded.casefold().split())


def same_person(a: str, b: str) -> bool:
    """Whether two renderings of a name are the same editor."""
    return bool(_person(a)) and _person(a) == _person(b)


@dataclass
class Conference:
    """One conference pulled from Indico, and what is known of its assignments."""

    root: Path
    base_url: str = ""
    event_id: int | None = None
    editable_type: str = "paper"
    pulled_at: str = ""
    checked_at: str = ""
    live: dict[str, dict] = field(default_factory=dict)   # contribution id -> paper

    @classmethod
    def open(cls, root: Path) -> "Conference | None":
        """The conference at *root*, or ``None`` if it was not pulled from Indico."""
        index_path = root / PULL_INDEX
        if not index_path.is_file():
            return None
        index = _read_json(index_path)
        live = _read_json(root / LIVE_FILE)
        return cls(
            root=root,
            base_url=str(index.get("base_url") or "").rstrip("/"),
            event_id=index.get("event_id"),
            editable_type=index.get("editable_type") or "paper",
            pulled_at=_mtime(index_path),
            checked_at=str(live.get("checked_at") or ""),
            live=live.get("papers") or {},
        )

    def paper_url(self, contribution_id: int) -> str:
        if not (self.base_url and self.event_id):
            return ""
        return (f"{self.base_url}/event/{self.event_id}/contributions/"
                f"{contribution_id}/editing/{self.editable_type}")

    def assignment(self, folder: Path, *, me: str = "") -> Assignment | None:
        """Who holds the paper whose revision is *folder*, or ``None`` if unknown.

        A pulled paper is ``<root>/<CODE>/<revision>``; its manifest is in
        ``<CODE>``.
        """
        manifest = _read_json(folder.parent / MANIFEST)
        contribution_id = manifest.get("contribution_id")
        if not isinstance(contribution_id, int):
            return None

        live = self.live.get(str(contribution_id))
        if live is not None:
            editor, state = live.get("editor", ""), live.get("state", "")
            source, as_of = "indico", self.checked_at
        else:
            editor, state = manifest.get("editor", ""), manifest.get("state", "")
            source, as_of = "pull", _mtime(folder.parent / MANIFEST) or self.pulled_at

        if not editor:
            holder = "nobody"
        elif same_person(editor, me):
            holder = "you"
        else:
            holder = "other"
        return Assignment(
            contribution_id=contribution_id, editor=editor, state=state,
            holder=holder, url=self.paper_url(contribution_id),
            source=source, as_of=as_of,
        )

    def summary(self) -> dict:
        """For the page: where the assignments come from, and how old they are."""
        live = bool(self.checked_at)
        return {
            "source": "indico" if live else "pull",
            "as_of": self.checked_at if live else self.pulled_at,
            "event_url": (f"{self.base_url}/event/{self.event_id}"
                          if self.base_url and self.event_id else ""),
        }


def assignment_for(folder: Path, *, me: str = "") -> Assignment | None:
    """Who holds this one paper, for a desk opened on its conference."""
    conference = Conference.open(folder.parent.parent)
    return conference.assignment(folder, me=me) if conference else None


def refresh(root: Path, *, client=None) -> dict:
    """Ask Indico who has each paper now, and remember the answer.

    One GET of the event's paper list, through a client opened read-only, so
    this cannot change anything in Indico whatever a later edit does to it.
    """
    conference = Conference.open(root)
    if conference is None or not (conference.base_url and conference.event_id):
        raise ValueError("this folder was not pulled from Indico, so there is "
                         "nothing to check it against")
    if client is None:
        from src.indico_client.client import IndicoClient, load_token

        client = IndicoClient(
            base_url=conference.base_url, event_id=int(conference.event_id),
            token=load_token(), editable_type=conference.editable_type,
            read_only=True,
        )
    rows = client.list_editables()

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    papers = {
        str(row.id): {"code": row.code, "editor": row.editor_name, "state": row.state}
        for row in rows if row.submitted
    }
    target = root / LIVE_FILE
    partial = target.with_name(target.name + ".part")
    partial.write_text(json.dumps({"checked_at": checked_at, "papers": papers},
                                  indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(partial, target)
    return {"checked_at": checked_at, "papers": len(papers)}
