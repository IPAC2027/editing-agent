"""The chief editor's part of the desk: the conference in Indico, and fetching it.

In chief mode (``aiagent --manage``) the desk shows the event's papers as Indico
lists them, which of them are already in the papers folder, and a button that
downloads the rest and prepares them, so a chief starting on an empty folder
sees the conference rather than an empty page.

Indico is only read, through a client opened ``read_only=True``. The token
stays on the server side: the page is told only whether one was found. The
page may choose the event, but never the site: the token is sent only to the
Indico given on the command line, recorded in the folder, or indico.jacow.org,
so another page in the browser cannot make the desk send it elsewhere.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "https://indico.jacow.org"


def recorded(root: Path) -> dict:
    """What an earlier download recorded about the conference in *root*."""
    try:
        data = json.loads((root / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass
class Event:
    """Which Indico event the chief's folder belongs to. Shared by every request."""

    url: str = DEFAULT_URL
    event_id: int | None = None

    @classmethod
    def for_folder(cls, root: Path, *, url: str | None = None,
                   event_id: int | None = None) -> "Event":
        known = recorded(root)
        if event_id and known.get("event_id") and int(known["event_id"]) != int(event_id):
            raise ValueError(f"{root} holds event {known['event_id']}, not {event_id}. "
                             "Use a separate folder for each conference.")
        chosen = event_id or known.get("event_id")
        return cls(url=(url or known.get("base_url") or DEFAULT_URL).rstrip("/"),
                   event_id=int(chosen) if chosen else None)

    def choose(self, root: Path, event_id: int) -> None:
        """Set the event from the page; refused once the folder holds another one."""
        if event_id <= 0:
            raise ValueError("an event id is a positive number, e.g. 194")
        known = recorded(root).get("event_id")
        if known and int(known) != event_id:
            raise ValueError(f"This folder already holds event {known}. Use a separate "
                             "folder for each conference.")
        self.event_id = event_id

    def client(self):
        from src.indico_client.client import IndicoClient, load_token

        if not self.event_id:
            raise ValueError("choose the Indico event first")
        return IndicoClient(base_url=self.url, event_id=self.event_id, token=load_token(),
                            read_only=True)

    def view(self) -> dict:
        from src.indico_client.client import IndicoError, load_token

        try:
            load_token()
            token, token_problem = True, ""
        except IndicoError as exc:
            token, token_problem = False, str(exc)
        return {"url": self.url, "event": self.event_id,
                "event_url": f"{self.url}/event/{self.event_id}" if self.event_id else "",
                "token": token, "token_problem": token_problem}


def papers(event: Event, root: Path) -> dict:
    """The event's papers as Indico lists them, and which are here already."""
    from src.indico_client.pull import _safe

    rows = event.client().list_editables()
    out = []
    for row in rows:
        folder = root / _safe(row.code or f"c{row.friendly_id}")
        revisions = row.editable.revision_count if row.editable else 0
        out.append({
            "code": row.label, "name": folder.name, "title": row.title,
            "submitted": row.submitted, "state": row.state, "editor": row.editor_name,
            "revisions": revisions,
            "here": (folder / "manifest.json").exists(),
            "prepared": any(folder.glob("*/aiagent_prescreen/report.json"))
                        or (folder / "aiagent_prescreen" / "report.json").exists(),
            **newer(folder, revisions),
        })
    return {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "papers": out,
            "submitted": sum(1 for p in out if p["submitted"]),
            "here": sum(1 for p in out if p["here"])}


def newer(folder: Path, indico_revisions: int) -> dict:
    """Which is newer, Indico's paper or the copy here.

    Indico is newer when it has revisions the copy was downloaded without
    (the author submitted again, or someone judged it in Indico); the copy is
    newer when an editor has worked on it here, which Indico has not seen.
    ``newer`` is ``indico``, ``local``, ``both``, ``same``, or ``""`` when
    there is no copy here.
    """
    from src.desk.state import AUTHOR_REVISION, ReviewState

    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"newer": "", "local_revisions": 0}
    local = int(manifest.get("revision_count") or 0)
    revision = folder / AUTHOR_REVISION
    worked_on = ReviewState.load(revision if revision.is_dir() else folder).status != "new"
    indico_newer = indico_revisions > local
    which = ("both" if indico_newer and worked_on else "indico" if indico_newer
             else "local" if worked_on else "same")
    return {"newer": which, "local_revisions": local}


def download_and_prepare(event: Event, root: Path, progress, *, prepare) -> None:
    """Fetch the papers not yet in *root*, ask Indico who holds each, prepare the new ones.

    *progress(label=, done=, total=, current=)* reports to the page;
    *prepare(folder)* screens one paper. Indico is only read.
    """
    from src.desk import claim as claim_module
    from src.desk import indico as indico_module
    from src.desk.state import submission_folders, submission_name
    from src.indico_client.pull import build_plan, pull

    client = event.client()
    progress(step="Step 1 of 4", label="Asking Indico what is new", done=0, total=0,
             current="")

    def reading(index: int, total: int) -> None:
        progress(done=index, total=total)

    plan = build_plan(client, destination=root, on_read=reading)
    fetchable = plan.fetchable
    progress(step="Step 2 of 4", label=f"Downloading {len(fetchable)} paper(s)", done=0,
             total=len(fetchable))

    def fetched(index: int, total: int, paper) -> None:
        progress(done=index - 1, total=total, current=paper.folder)

    pull(client, root, plan=plan, on_paper=fetched)
    progress(done=len(fetchable))
    for line in plan.failures:
        progress(error=f"not downloaded (try again): {line}")

    progress(step="Step 3 of 4", label="Asking Indico who holds each paper", done=0, total=0,
             current="")
    try:
        indico_module.refresh(root, client=client)
    except Exception as exc:  # noqa: BLE001 — the papers are here; who holds them can wait
        progress(error=f"Could not read who holds each paper: {exc}")

    new = [f for f in submission_folders(root)
           if not (f / "aiagent_prescreen" / "report.json").exists()
           and claim_module.current(f) is None]
    progress(step="Step 4 of 4", label=f"Preparing {len(new)} paper(s)", done=0,
             total=len(new), current="")
    for index, folder in enumerate(new, start=1):
        progress(current=submission_name(folder))
        try:
            prepare(folder)
        except Exception as exc:  # noqa: BLE001 — one bad paper must not stop the rest
            progress(error=f"{submission_name(folder)}: {type(exc).__name__}: {exc}")
        progress(done=index)
