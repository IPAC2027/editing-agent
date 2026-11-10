"""An editor's desk joined to the chief editor's: copies here, the pool there.

The editor's desk never opens the chief's papers folder. It asks the chief's
desk (``src.desk.pool``) for the list of papers, takes one, downloads a copy
into a folder on this computer and works on that copy with the ordinary desk.
Every change is sent back a few seconds later, so the chief's page stays up
to date; finishing a paper sends it one last time and gives it back.

The editor never chooses that folder: the desk keeps one per chief editor's
desk in its own settings folder (:func:`working_folder`), so two conferences'
MOP001 never meet. It holds only what the editor is working on. A copy given
back is cleared the next time the desk starts (:meth:`Joined.tidy`); a copy
with changes the chief's desk has not received is never cleared.

What the copies are is recorded in ``.pool_copies.json`` in that folder:
whether this desk still holds each paper on the chief's desk, whether there
are changes not sent yet, and when it last sent.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from src.desk import bundle, files
from src.desk import me as me_module
from src.desk.pool import CONFERENCE_FILES, OUT_DIR, POOL_PORT

URL_SETTING = "pool_url"
CODE_SETTING = "pool_join_code"
COPIES_FILE = ".pool_copies.json"
#: In the desk's settings folder: one folder of copies per chief editor's desk.
WORKING_DIR = "working"
#: How long after the last change a paper is sent.
SEND_DELAY = 4.0
#: How long to wait before trying again when the chief's desk did not answer.
RETRY_DELAY = 30.0
#: How long Indico's answer "does this account manage the editing?" is kept,
#: and how soon it is asked again before taking a paper.
ROLE_FOR = 600.0
ROLE_RECHECK = 30.0
#: Indico out of reach: a "yes" this recent still counts.
ROLE_KEPT = 3600.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PoolError(Exception):
    """The chief's desk could not be reached, or said no."""


class Refused(PoolError):
    """The chief's desk refused because the paper is not this desk's (HTTP 409)."""


def normalise_url(url: str) -> str:
    """``192.168.1.20`` → ``http://192.168.1.20:8770``."""
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError("no address was given for the chief editor's desk")
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"{url} is not an address like http://192.168.1.20:{POOL_PORT}")
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or POOL_PORT}"


def working_folder(url: str, home: Path | None = None) -> Path:
    """Where this desk keeps its copies of papers from the chief's desk at *url*."""
    parsed = urlparse(normalise_url(url))
    name = re.sub(r"[^A-Za-z0-9.-]+", "_", f"{parsed.hostname}-{parsed.port}")
    return me_module.settings_dir(home) / WORKING_DIR / name


class RemotePool:
    """The chief editor's desk, as seen from an editor's."""

    def __init__(self, url: str, code: str, *, timeout: float = 30.0,
                 home: Path | None = None) -> None:
        self.url = normalise_url(url)
        self.code = code.strip()
        self.timeout = timeout
        self.home = home
        # Indico's answer to this desk's own account: it manages the editing.
        self.editing_manager = False

    def _request(self, method: str, path: str, me: me_module.Me, *,
                 data: bytes | None = None, ctype: str = "application/json") -> bytes:
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.code}")
        request.add_header("X-Desk-Id", me.desk_id)
        request.add_header("X-Desk-Name", quote(me.name))
        request.add_header("X-Desk-Machine", quote(me.machine))
        # Who the editor is in Indico, as their own token showed (never the
        # token itself), so the chief's desk can assign papers to them.
        from src.desk import account

        indico_user = account.user(self.home)
        if indico_user.get("id"):
            request.add_header("X-Indico-User-Id", str(int(indico_user["id"])))
            request.add_header("X-Indico-User-Name", quote(indico_user.get("name", "")))
            if self.editing_manager:
                request.add_header("X-Indico-Editing-Manager", "1")
        if data is not None:
            request.add_header("Content-Type", ctype)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:  # noqa: BLE001
                message = ""
            message = message or f"the chief editor's desk answered {exc.code}"
            if exc.code == 409:
                raise Refused(message) from None
            raise PoolError(message) from None
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise PoolError(f"Could not reach the chief editor's desk at {self.url} "
                            f"({reason}). Is it running, and is this computer on the "
                            "same network?") from None

    def _json(self, method: str, path: str, me, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        return json.loads(self._request(method, path, me, data=data).decode("utf-8"))

    def hello(self, me) -> dict:
        return self._json("GET", "/pool/hello", me)

    def listing(self, me) -> dict:
        """The chief's papers, and whether the chief's desk lets this editor take them."""
        return self._json("GET", "/pool/papers", me)

    def papers(self, me) -> list[dict]:
        return self.listing(me)["papers"]

    def conference(self, me) -> dict[str, dict]:
        return self._json("GET", "/pool/conference", me)["files"]

    def take(self, paper: str, me, mode: str = "edit") -> dict:
        return self._json("POST", "/pool/take", me, {"paper": paper, "mode": mode})

    def download(self, paper: str, me) -> bytes:
        return self._request("GET", "/pool/paper?" + urlencode({"paper": paper}), me)

    def send(self, paper: str, me, data: bytes, *, release: bool = False,
             reason: str = "") -> dict:
        fields = {"paper": paper, "release": "1" if release else "0"}
        if release and reason:
            fields["reason"] = reason[:500]
        query = urlencode(fields)
        return json.loads(self._request("POST", "/pool/send?" + query, me, data=data,
                                        ctype="application/zip").decode("utf-8"))

    def release(self, paper: str, me, reason: str = "") -> dict:
        return self._json("POST", "/pool/release", me, {"paper": paper, "reason": reason})


class Joined:
    """This desk's copies of papers taken from the chief's desk, kept in step."""

    def __init__(self, root: Path, pool: RemotePool, *, home: Path | None = None,
                 delay: float = SEND_DELAY, background: bool = True) -> None:
        self.root = Path(root).resolve()
        self.pool = pool
        self.home = home
        pool.home = home
        self.delay = delay
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.last_error = ""
        # Indico's last answer about this account: (when, account id, manages
        # the editing (True / False / None), why it could not tell).
        self._role: tuple[float, object, bool | None, str] = (0.0, None, None, "")
        self._yes: tuple[float, object] = (0.0, None)    # when Indico last said yes
        if background:
            threading.Thread(target=self._sender, daemon=True).start()

    def me(self) -> me_module.Me:
        """This editor, named as their Indico account names them once connected."""
        from dataclasses import replace

        from src.desk import account

        me = me_module.current(self.home)
        name = str(account.user(self.home).get("name") or "").strip()
        return replace(me, name=name) if name else me

    # -- what is recorded about the copies --------------------------------
    def _copies(self) -> dict:
        try:
            data = json.loads((self.root / COPIES_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _record(self, paper: str, **facts) -> dict:
        with self.lock:
            copies = self._copies()
            entry = copies.setdefault(paper, {})
            entry.update(facts)
            files.write_text(self.root / COPIES_FILE, json.dumps(copies, indent=2))
            return entry

    def copy(self, paper: str) -> dict:
        return self._copies().get(paper, {})

    @staticmethod
    def paper_of(folder: Path) -> str:
        from src.desk.state import submission_name

        return submission_name(folder)

    def holds(self, folder: Path) -> bool:
        return bool(self.copy(self.paper_of(folder)).get("held"))

    def require_held(self, folder: Path) -> None:
        if not self.holds(folder):
            raise ValueError("This copy is no longer yours on the chief editor's desk, so "
                             "changes to it would not reach anyone. Take the paper again "
                             "from the list to work on it.")

    def sync_view(self, folder: Path) -> dict:
        entry = self.copy(self.paper_of(folder))
        return {"held": bool(entry.get("held")), "dirty": bool(entry.get("dirty")),
                "sent_at": entry.get("sent_at", ""), "error": entry.get("error", ""),
                "mode": entry.get("mode", "edit")}

    def mode_of(self, folder: Path) -> str:
        """What this desk took the paper for: ``edit`` or ``qa``."""
        return self.copy(self.paper_of(folder)).get("mode", "edit")

    # -- talking to the chief ----------------------------------------------
    def view(self) -> dict:
        try:
            hello = self.pool.hello(self.me())
            self.last_error = ""
        except PoolError as exc:
            hello, self.last_error = {}, str(exc)
        return {"url": self.pool.url, "connected": not self.last_error,
                "error": self.last_error, **hello}

    def editing_role(self, fresh_for: float = ROLE_FOR) -> tuple[bool | None, str]:
        """Whether this editor manages the conference's editing in Indico.

        Indico is asked with this desk's own token (``account.manages_editing``)
        and the answer kept for *fresh_for* seconds; the chief's desk hears it
        with every request, and lets an editing manager take papers as it lets
        a paper editor.
        """
        from src.desk import account

        account_id = account.user(self.home).get("id")
        when, asked_for, manager, why = self._role
        if account_id != asked_for or time.time() - when > fresh_for:
            if not account_id:
                manager, why = None, ""
            else:
                try:
                    hello = self.pool.hello(self.me())
                except PoolError:
                    return manager, why        # the chief's desk is out of reach
                manager, why = account.manages_editing(hello.get("indico", ""),
                                                       hello.get("event"), self.home)
                if manager:
                    self._yes = (time.time(), account_id)
                elif (manager is None and self._yes[1] == account_id
                      and time.time() - self._yes[0] < ROLE_KEPT):
                    manager = True         # Indico out of reach; it said yes just now
            self._role = (time.time(), account_id, manager, why)
            self.pool.editing_manager = bool(manager)
        return manager, why

    def listing(self) -> dict:
        """The chief's papers, with this desk's copies, and ``you``: whether the
        chief's desk lets this editor take papers (Indico's paper editors and
        editing managers only)."""
        _, why = self.editing_role()
        found = self.pool.listing(self.me())
        rows = found.get("papers", [])
        copies = self._copies()
        for row in rows:
            entry = copies.get(row["paper"], {})
            row["here"] = bool(entry.get("folder")) and Path(entry["folder"]).is_dir()
            row["folder"] = entry.get("folder", "") if row["here"] else ""
        you = dict(found.get("you") or {})
        you["indico_said"] = why             # why Indico could not be asked, if so
        return {"papers": rows, "you": you}

    def papers(self) -> list[dict]:
        return self.listing()["papers"]

    def refresh_conference(self) -> dict:
        """The chief's knowledge of the conference (Indico's assignments) copied here."""
        found = self.pool.conference(self.me())
        for name in CONFERENCE_FILES:
            if name in found:
                files.write_text(self.root / name, json.dumps(found[name], indent=2,
                                                              ensure_ascii=False))
        live = found.get("indico_assignments.json", {})
        return {"checked_at": live.get("checked_at", ""),
                "papers": len(live.get("papers", {})),
                "authors": len(found.get("indico_abstracts.json", {})
                               .get("contributions", {})),
                "authors_error": ""}

    def take(self, paper: str, mode: str = "edit") -> Path:
        """Take *paper* on the chief's desk, to edit it or to QA it, and have a
        copy here; returns its folder."""
        from src.desk import account

        if not account.user(self.home).get("id"):
            raise ValueError("Connect your Indico account first: paste your Indico token "
                             "into the box on this page. The chief editor's desk knows "
                             "editors by their Indico account.")
        self.editing_role(fresh_for=ROLE_RECHECK)   # just made a manager: in at once
        me = self.me()
        with self.lock:
            taken = self.pool.take(paper, me, mode)  # Refused if someone else has it
            try:
                # First, so this folder is known as a conference pulled from
                # Indico and its assignments show.
                self.refresh_conference()
            except PoolError:
                pass                           # the paper matters; the rest can wait
            entry = self.copy(paper)
            folder = Path(entry["folder"]) if entry.get("folder") else None
            unsent = entry.get("held") and entry.get("dirty") and folder and folder.is_dir()
            if not unsent:
                folder = self._unpack(self.pool.download(paper, me), taken["path"],
                                      keep_old=bool(entry.get("dirty")))
            self._record(paper, held=True, dirty=False, folder=str(folder),
                         taken_at=_now(), error="", give_back=False,
                         mode=taken.get("mode", mode))
        return folder

    def _unpack(self, data: bytes, path: str, *, keep_old: bool = True) -> Path:
        """Put the paper from *data* in place here; returns its folder (*path* in it).

        An older copy already here is replaced; with *keep_old* (it holds work
        the chief's desk never received) it is set aside in ``.replaced/`` first.
        """
        parts = [part for part in path.split("/") if part]
        if not parts or any(part in (".", "..") or "\\" in part for part in parts):
            raise bundle.BadBundle(f"unexpected paper path {path!r}")
        names = bundle.read(data, "")
        tops = {name.split("/", 1)[0] for name in names}
        if len(tops) != 1:
            raise bundle.BadBundle("it does not hold exactly one paper")
        top = tops.pop()
        incoming = self.root / f".incoming-{uuid.uuid4().hex[:8]}"
        try:
            bundle.write_tree(incoming, names)
            target = self.root / top
            if target.exists() and keep_old:
                old = self.root / ".replaced" / f"{top}-{uuid.uuid4().hex[:6]}"
                old.parent.mkdir(parents=True, exist_ok=True)
                target.rename(old)
            elif target.exists():
                shutil.rmtree(target)
            (incoming / top).rename(target)
        finally:
            shutil.rmtree(incoming, ignore_errors=True)
        folder = self.root.joinpath(*parts)
        if parts[0] != top or not folder.is_dir():
            raise bundle.BadBundle(f"it did not hold {path}")
        return folder

    def changed(self, folder: Path) -> None:
        """A change was saved to *folder*: send it soon."""
        paper = self.paper_of(folder)
        if self.copy(paper).get("held"):
            self._record(paper, dirty=True, changed=time.time())
            self.wake.set()

    def send(self, folder: Path, *, release: bool = False, reason: str = "") -> dict:
        """Send the copy now; with *release*, give the paper back too (*reason*
        is shown on the chief's page if it is given up unfinished)."""
        paper = self.paper_of(folder)
        with self.lock:
            # A paper finished or given up while the chief's desk was out of
            # reach is still to be given back, by whichever send gets through.
            entry = self.copy(paper)
            release = release or bool(entry.get("give_back"))
            reason = reason or entry.get("give_back_reason", "")
            data = bundle.pack(self.root, folder / OUT_DIR)
            try:
                result = self.pool.send(paper, self.me(), data, release=release,
                                        reason=reason if release else "")
            except Refused as exc:
                # What is here never reached the chief: kept, never tidied away.
                self._record(paper, held=False, give_back=False, dirty=True,
                             error=str(exc))
                raise
            except PoolError as exc:
                self._record(paper, dirty=True, error=str(exc),
                             retry_at=time.time() + RETRY_DELAY)
                raise
            self._record(paper, dirty=False, sent_at=result.get("received_at", _now()),
                         error="", held=not release, give_back=False,
                         give_back_reason="", retry_at=0)
        return result

    def give_back(self, folder: Path, reason: str = "") -> dict:
        """Send the copy one last time and give the paper back (or up, with *reason*)."""
        self._record(self.paper_of(folder), give_back=True, give_back_reason=reason)
        return self.send(folder, release=True, reason=reason)

    def tidy(self) -> list[str]:
        """Clear the copies this desk no longer needs; returns their papers.

        A copy goes once it is given back and the chief's desk has all of it.
        Copies still held, or with changes the chief never received, stay.
        """
        removed = []
        with self.lock:
            copies = self._copies()
            for paper, entry in list(copies.items()):
                if entry.get("held") or entry.get("dirty"):
                    continue
                top = self._top(entry.get("folder", ""))
                if top is not None:
                    shutil.rmtree(top, ignore_errors=True)
                del copies[paper]
                removed.append(paper)
            if removed:
                files.write_text(self.root / COPIES_FILE, json.dumps(copies, indent=2))
            for leftover in self.root.glob(".incoming-*"):
                shutil.rmtree(leftover, ignore_errors=True)
        return removed

    def _top(self, folder: str) -> Path | None:
        """The paper's own top folder here, for *folder* inside it (never anything else)."""
        if not folder:
            return None
        try:
            parts = Path(folder).resolve().relative_to(self.root).parts
        except (OSError, ValueError):
            return None
        if not parts or parts[0].startswith("."):
            return None
        return self.root / parts[0]

    def due(self, now: float | None = None) -> list[Path]:
        """Copies with changes old enough to send."""
        now = time.time() if now is None else now
        ready = []
        for entry in self._copies().values():
            if not (entry.get("held") and entry.get("dirty") and entry.get("folder")):
                continue
            if now - float(entry.get("changed", 0)) < self.delay:
                continue
            if now < float(entry.get("retry_at", 0)):
                continue
            ready.append(Path(entry["folder"]))
        return ready

    def flush(self) -> None:
        """Send every copy with changes waiting, now (the tests use this)."""
        for folder in self.due(now=float("inf")):
            try:
                self.send(folder)
            except PoolError:
                pass

    def _sender(self) -> None:
        while True:
            self.wake.wait(timeout=5.0)
            self.wake.clear()
            time.sleep(self.delay)
            for folder in self.due():
                try:
                    self.send(folder)
                except PoolError:
                    pass          # recorded on the copy; the page shows it
                except Exception:  # noqa: BLE001 — never let the sender thread die
                    import traceback

                    traceback.print_exc()
