"""A local review desk: one page, no terminal, no git.

Runs a small web server on this machine only (``127.0.0.1``) and opens a
browser at it. Nothing leaves the computer and nothing is installed. The
editor sees a list of papers, opens one, works through it, closes it and moves
to the next.

Deliberately built on the standard library alone. Adding a web framework would
mean the editor's machine needs a working package install before they can
review a paper, and the whole point of this module is that they should not have
to know what a package is.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.desk import account as account_module
from src.desk import indico as indico_module
from src.desk import claim as claim_module
from src.desk import me as me_module
from src.desk import paper as paper_module
from src.desk import remote as remote_module
from src.desk import state as state_module
from src.desk.state import EditorNote, ManualEdit, ReviewState

#: Where the editor's name used to be kept: in the paper folder, shared by
#: every desk opened on it. Now kept per person (see ``src.desk.me``); the
#: name is still git-ignored so an old file never ends up in a commit.
LEGACY_CONFIG_FILENAME = ".aiagent_desk.json"

#: What the chief editor's managing page may change. It manages: Indico, the
#: download, preparing papers, the editors' door. Papers are edited on an
#: editor's desk, the chief's own included (src.desk.editing).
MANAGING_ROUTES = frozenset({
    "/api/editor", "/api/prepare", "/api/indico-refresh", "/api/format-references",
    "/api/indico-account", "/api/chief/event", "/api/chief/papers",
    "/api/chief/download", "/api/chief/indico-sync", "/api/chief/given-up",
    "/api/chief/free", "/api/chief/editing-desk",
})
NOT_ON_THE_MANAGING_PAGE = ("This is the chief editor's managing page: papers are not "
                            "edited here. Click Edit papers at the top to open your "
                            "editing desk.")


# ---------------------------------------------------------------------------
# Background jobs (preparing papers)
# ---------------------------------------------------------------------------

class JobRunner:
    """Runs a screening pass without blocking the page.

    Preparing a paper takes seconds without a build and a minute or so with
    one; the editor should see progress rather than a frozen tab.
    """

    def __init__(self, *, llm: bool = False) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        # Whether preparing a paper may consult a local model.  Held here
        # rather than read from the environment inside the worker, so that what
        # the launcher window announced is exactly what every paper gets.
        self.llm = llm

    def start(self, label: str, folders: list[Path], *, compile_pdf: bool) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "label": label,
                "total": len(folders),
                "done": 0,
                "current": "",
                "finished": False,
                "errors": [],
                "started": time.time(),
                "current_since": time.time(),
            }
        thread = threading.Thread(
            target=self._run, args=(job_id, folders, compile_pdf), daemon=True,
        )
        thread.start()
        return job_id

    def _run(self, job_id: str, folders: list[Path], compile_pdf: bool) -> None:
        from src.workflow.prescreen import prescreen

        for folder in folders:
            with self._lock:
                self._jobs[job_id]["current"] = state_module.submission_name(folder)
                self._jobs[job_id]["current_since"] = time.time()
            try:
                prescreen(folder, compile=compile_pdf, git=True, llm=self.llm)
            except Exception as exc:  # noqa: BLE001 — one bad paper must not stop a batch
                with self._lock:
                    self._jobs[job_id]["errors"].append(
                        f"{folder.name}: {type(exc).__name__}: {exc}"
                    )
            finally:
                with self._lock:
                    self._jobs[job_id]["done"] += 1
        with self._lock:
            self._jobs[job_id]["finished"] = True
            self._jobs[job_id]["current"] = ""

    def start_task(self, label: str, work) -> str:
        """Run *work(progress)* in the background; *progress* updates the job.

        ``progress(label=, done=, total=, current=)`` changes what the page
        shows; ``progress(error=...)`` adds a line to the job's errors.
        """
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "label": label, "total": 0, "done": 0,
                                  "current": "", "finished": False, "errors": [],
                                  "step": "", "started": time.time(),
                                  "current_since": time.time()}

        def progress(**changes) -> None:
            with self._lock:
                job = self._jobs[job_id]
                if "error" in changes:
                    job["errors"].append(str(changes.pop("error")))
                if changes.get("current") and changes["current"] != job["current"]:
                    job["current_since"] = time.time()
                job.update(changes)

        def run() -> None:
            try:
                work(progress)
            except Exception as exc:  # noqa: BLE001 — reported on the page, not lost
                progress(error=f"{type(exc).__name__}: {exc}")
            finally:
                progress(finished=True, current="")

        threading.Thread(target=run, daemon=True).start()
        return job_id

    @staticmethod
    def _view(job: dict) -> dict:
        """The job as the page shows it, with how long it and its paper have taken."""
        view = dict(job)
        now = time.time()
        if "started" in job:
            view["elapsed"] = round(now - job["started"])
            view["current_elapsed"] = round(now - job.get("current_since", now))
        return view

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._view(job) if job else {"id": job_id, "missing": True}

    def active(self) -> list[dict]:
        with self._lock:
            return [self._view(job) for job in self._jobs.values() if not job["finished"]]


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------

class DeskHandler(BaseHTTPRequestHandler):
    server_version = "JACoWReviewDesk/1.0"

    def __init__(self, *args, root: Path, jobs: JobRunner,
                 home: Path | None = None, chief=None, pool=None, sharing=None,
                 sync=None, editing=None, **kwargs) -> None:
        self.root = root
        self.jobs = jobs
        # An editor's desk joined to the chief's (src.desk.remote.Joined):
        # *root* then holds this editor's copies, and the papers themselves
        # live on the chief's desk. None for a desk on its own folder.
        self.pool = pool
        # The chief's door for editors (src.desk.pool.Pool), or None.
        self.sharing = sharing
        # The chief's desk keeping Indico in step (src.desk.indico_sync), or None.
        self.sync = sync
        # The chief editor's Indico event (src.desk.chief.Event), or None for
        # an editor's desk: then the chief's routes do not exist.
        self.chief = chief
        # Where this editor's own settings live; None means their home folder.
        self.home = home
        # The chief's own editing desk (src.desk.editing.EditingDesk), or None.
        self.editing = editing
        super().__init__(*args, **kwargs)

    # -- plumbing -------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return  # the console belongs to the launcher's instructions, not to logs

    def _send(self, status: HTTPStatus, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # -- who may talk to the desk ----------------------------------------
    # The desk listens on 127.0.0.1, but any web page the editor visits can
    # still send requests to it.  Two checks close that door:
    #   * Host must name this server, which defeats DNS rebinding (a hostile
    #     domain re-pointed at 127.0.0.1 sends its own name as Host);
    #   * a write must be a JSON request from this page.  A cross-site page
    #     can only send JSON after a CORS preflight, which the desk never
    #     approves, and browsers label its requests with a foreign Origin.
    def _allowed_hosts(self) -> set[str]:
        addr, port = self.server.server_address[:2]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if addr not in ("", "0.0.0.0", "::"):
            hosts.add(f"{addr}:{port}")
        return hosts

    def _refusal(self, *, write: bool) -> str | None:
        hosts = self._allowed_hosts()
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in hosts:
            return "The review desk only answers requests addressed to this computer."
        if write:
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in hosts}:
                return "The review desk only accepts changes made from its own page."
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return "The review desk only accepts changes made from its own page."
        return None

    def _json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"error": message}, status)

    def _drain(self, limit: int = 1 << 20) -> None:
        try:
            length = min(int(self.headers.get("Content-Length") or 0), limit)
        except ValueError:
            return
        if length > 0:
            self.rfile.read(length)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _folder(self, raw: str | None) -> Path:
        """Resolve a folder from a request, refusing anything outside the root."""
        if not raw:
            raise ValueError("no paper was named")
        candidate = Path(raw).expanduser().resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("that paper is outside the folder this desk was opened on")
        if not candidate.is_dir():
            raise ValueError("that paper folder no longer exists")
        return candidate

    # -- the editor's own settings ----------------------------------------
    # Kept on this computer, not in the paper folder, which other editors'
    # desks may be reading too.
    def _config(self) -> dict:
        return me_module.load_settings(self.home)

    def _me(self) -> me_module.Me:
        return self.pool.me() if self.pool else me_module.current(self.home)

    def _account(self) -> dict:
        return account_module.view(self.home, typed_only=self.pool is not None)

    # -- routing --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        refusal = self._refusal(write=False)
        if refusal:
            self._error(refusal, HTTPStatus.FORBIDDEN)
            return
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        try:
            if route in ("/", "/index.html"):
                from src.desk.ui import PAGE

                self._send(HTTPStatus.OK, PAGE.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif route == "/references":
                from src.desk.references_page import PAGE as REFERENCES_PAGE

                self._send(HTTPStatus.OK, REFERENCES_PAGE.encode("utf-8"),
                           "text/html; charset=utf-8")
            elif route == "/api/setup":
                me = self._me()
                self._json({
                    "root": str(self.root),
                    "root_name": self.root.name,
                    "editor": me.name,
                    "machine": me.machine,
                    "compile": self._config().get("compile", True),
                    "llm": _llm_state(self.jobs.llm),
                    "jobs": self.jobs.active(),
                    "chief": self.chief.view() if self.chief else None,
                    "sharing": self.sharing.view() if self.sharing else None,
                    "pool": self.pool.view() if self.pool else None,
                    "account": self._account(),
                    "indico_sync": self.sync.view() if self.sync else None,
                    "editing": self.editing.view() if self.editing else None,
                })
            elif route == "/api/worklist":
                conference = (indico_module.Conference.open(self.root)
                              if state_module.is_pulled_conference(self.root) else None)
                me = self._me()
                rows = [row.model_dump() for row in state_module.worklist(
                    self.root, me=me.name, desk_id=me.desk_id)]
                activity = self.sharing.activity().get("papers", {}) if self.sharing else {}
                for row in rows:
                    if self.pool:
                        row["sync"] = self.pool.sync_view(Path(row["folder"]))
                    if self.sharing:
                        row["received_at"] = activity.get(row["name"], {}).get(
                            "received_at", "")
                        # Whether the editor with the paper here is the one
                        # Indico says has it: the chief settles any difference.
                        indico_editor = (row.get("indico") or {}).get("editor", "")
                        who = (row.get("claim") or {}).get("who", "")
                        row["claim_vs_indico"] = "" if not (who and indico_editor) else (
                            "same" if indico_module.same_person(who, indico_editor)
                            else "differs")
                self._json({
                    "papers": rows,
                    "indico": conference.summary() if conference else None,
                    "sharing": self.sharing.view() if self.sharing else None,
                    "indico_sync": self.sync.view() if self.sync else None,
                })
            elif route == "/api/paper":
                self._json(self._view(self._folder(_one(query, "folder"))))
            elif route == "/api/job":
                self._json(self.jobs.status(_one(query, "id") or ""))
            elif route == "/file":
                self._serve_file(query)
            else:
                self._error("unknown address", HTTPStatus.NOT_FOUND)
        except remote_module.PoolError as exc:
            self._error(str(exc), HTTPStatus.BAD_GATEWAY)
        except ValueError as exc:
            self._error(str(exc))
        except paper_module.DeskError as exc:
            self._error(str(exc))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._error(f"something went wrong: {exc}",
                        HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        refusal = self._refusal(write=True)
        if refusal:
            # Read (and discard) the request body before answering: closing
            # with unread data makes Windows reset the connection, so the
            # sender saw "connection aborted" instead of the 403.
            self._drain()
            self._error(refusal, HTTPStatus.FORBIDDEN)
            return
        route = urlparse(self.path).path
        if self.chief is not None and route not in MANAGING_ROUTES:
            self._drain()
            self._error(NOT_ON_THE_MANAGING_PAGE, HTTPStatus.FORBIDDEN)
            return
        body = self._body()
        try:
            handler = {
                "/api/editor": self._set_editor,
                "/api/decide": self._decide,
                "/api/edit-note": self._edit_note,
                "/api/finding": self._finding,
                "/api/my-note": self._my_note,
                "/api/my-note/delete": self._delete_my_note,
                "/api/my-edit": self._my_edit,
                "/api/my-edit/delete": self._delete_my_edit,
                "/api/paper-note": self._paper_note,
                "/api/letter": self._letter,
                "/api/prepare": self._prepare,
                "/api/close": self._close,
                "/api/reopen": self._reopen,
                "/api/format-references": self._format_references,
                "/api/indico-refresh": self._indico_refresh,
                "/api/title-authors": self._title_authors,
                "/api/claim": self._claim,
                "/api/chief/event": self._chief_event,
                "/api/chief/papers": self._chief_papers,
                "/api/chief/download": self._chief_download,
                "/api/pool/papers": self._pool_papers,
                "/api/pool/take": self._pool_take,
                "/api/pool/send": self._pool_send,
                "/api/qa": self._qa,
                "/api/indico-account": self._indico_account,
                "/api/chief/indico-sync": self._chief_indico_sync,
                "/api/chief/given-up": self._chief_given_up,
                "/api/chief/free": self._chief_free,
                "/api/chief/editing-desk": self._chief_editing_desk,
            }.get(route)
            if handler is None:
                self._error("unknown address", HTTPStatus.NOT_FOUND)
                return
            handler(body)
        except remote_module.Refused as exc:
            self._error(str(exc), HTTPStatus.CONFLICT)
        except remote_module.PoolError as exc:
            self._error(str(exc), HTTPStatus.BAD_GATEWAY)
        except claim_module.Held as exc:
            # 409: the paper is being edited at another desk. The page gets the
            # claim with the message so it can say who, without a reload.
            self._json({"error": str(exc), "claim": exc.view}, HTTPStatus.CONFLICT)
        except ValueError as exc:
            self._error(str(exc))
        except paper_module.DeskError as exc:
            self._error(str(exc))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._error(f"something went wrong: {exc}",
                        HTTPStatus.INTERNAL_SERVER_ERROR)

    # -- the chief editor's actions ----------------------------------------
    def _chief_only(self):
        if self.chief is None:
            raise ValueError("only the chief editor's desk (aiagent --manage) fetches papers")
        return self.chief

    def _chief_event(self, body: dict) -> None:
        chief = self._chief_only()
        try:
            event_id = int(str(body.get("event", "")).strip())
        except ValueError:
            raise ValueError("an event id is a number, e.g. 194") from None
        chief.choose(self.root, event_id)
        self._json(chief.view())

    def _chief_papers(self, body: dict) -> None:
        import httpx

        from src.desk import chief as chief_module
        from src.indico_client.client import IndicoError

        chief = self._chief_only()
        try:
            self._json(chief_module.papers(chief, self.root))
        except IndicoError as exc:
            self._error(str(exc), HTTPStatus.BAD_GATEWAY)
        except httpx.HTTPError as exc:
            self._error(f"Could not reach Indico ({type(exc).__name__}). Check the "
                        "internet connection.", HTTPStatus.BAD_GATEWAY)

    def _chief_download(self, body: dict) -> None:
        from src.desk import chief as chief_module
        from src.workflow.prescreen import prescreen

        from src.indico_client.client import IndicoError

        chief = self._chief_only()
        try:
            chief.client()                # no event or no token: say so now, not in a job
        except IndicoError as exc:
            raise ValueError(str(exc)) from None
        if any(job.get("label", "").startswith(("Downloading", "Asking Indico", "Preparing"))
               for job in self.jobs.active()):
            raise ValueError("a download or preparation is already running")
        compile_pdf = bool(self._config().get("compile", True))
        llm = self.jobs.llm
        root = self.root

        def work(progress) -> None:
            chief_module.download_and_prepare(
                chief, root, progress,
                prepare=lambda folder: prescreen(folder, compile=compile_pdf, git=True,
                                                 llm=llm))

        job_id = self.jobs.start_task("Asking Indico what is new", work)
        self._json({"job": self.jobs.status(job_id)})

    # -- actions --------------------------------------------------------
    def _indico_refresh(self, body: dict) -> None:
        import httpx

        from src.indico_client.client import IndicoError

        if self.pool:
            # An editor joined to the chief's desk has no Indico token: the
            # chief's desk keeps Indico's answer, and this copies it.
            self._json(self.pool.refresh_conference())
            return
        try:
            self._json(indico_module.refresh(self.root))
        except IndicoError as exc:
            self._error(str(exc), HTTPStatus.BAD_GATEWAY)
        except httpx.HTTPError as exc:
            self._error(f"Could not reach Indico ({type(exc).__name__}). Check the "
                        "internet connection; the list still shows what the pull "
                        "recorded.", HTTPStatus.BAD_GATEWAY)

    def _title_authors(self, body: dict) -> None:
        from src.desk import title_check

        folder, review = self._with_state(body)
        conference = indico_module.Conference.open(folder.parent.parent)
        title_check.act(
            review, str(body.get("action", "")), body,
            front=title_check.front_for(folder, paper_module.Paper(folder).report),
            record=conference.record(folder) if conference else None,
        )
        review.touch()
        review.save(folder)
        self._json(self._view(folder))

    def _format_references(self, body: dict) -> None:
        from src.desk.references_page import check_reference_list

        text = str(body.get("text") or "")
        if not text.strip():
            raise ValueError("paste at least one reference")
        self._json(check_reference_list(text, lookups=bool(body.get("lookups", True))))

    def _view(self, folder: Path) -> dict:
        me = self._me()
        view = paper_module.view(folder, default_editor=me.name)
        view["claim"] = claim_module.view(folder, me.desk_id)
        if self.pool:
            # The claim that counts is the one on the chief's desk.
            sync = self.pool.sync_view(folder)
            view["claim"] = {"state": "mine" if sync["held"] else "copy",
                             "who": me.name, "machine": me.machine, "since": ""}
            view["sync"] = sync
        review = ReviewState.load(folder)
        view["qa"] = state_module.qa_view(review)
        view["stage"] = state_module.stage_of(review, prepared=bool(view.get("screened")))
        return view

    def _with_state(self, body: dict):
        """The paper named in *body* and its review state, ready to change.

        Every change to a paper comes through here, so this is where the paper
        is claimed: the first change claims a free paper, and a paper another
        desk is editing refuses the change (``claim.Held``) before anything is
        written.
        """
        folder = self._folder(body.get("folder"))
        me = self._me()
        if self.pool:
            self.pool.require_held(folder)
            # Sent to the chief's desk a few seconds after the last change
            # (marked before the change is saved; the send comes after it).
            self.pool.changed(folder)
        was_free = claim_module.current(folder) is None
        claim_module.take(folder, me)
        if was_free:
            self._indico_wants(folder)
        review = ReviewState.load(folder)
        if self.pool and self.pool.mode_of(folder) == "qa":
            return folder, review       # a QA does not make anyone the paper's editor
        # Whoever picks a free paper up is its editor from now on, so a paper
        # reopened for the author's next round is signed by the editor doing
        # that round, not the one who did the last.
        if not review.editor or (was_free and me.name):
            review.editor = me.name or review.editor
        return folder, review

    def _claim(self, body: dict) -> None:
        """Take a paper, take it over from a colleague, or let it go."""
        folder = self._folder(body.get("folder"))
        me = self._me()
        action = str(body.get("action", ""))
        if self.pool:
            paper = self.pool.paper_of(folder)
            problem = ""
            if action == "take":
                folder = self.pool.take(paper)
            elif action == "release":
                # Giving the paper up: the work so far goes first, and the
                # chief's page is told, with the editor's reason.
                reason = " ".join(str(body.get("reason", "")).split())[:500]
                try:
                    self.pool.give_back(folder, reason=reason)
                except remote_module.Refused as exc:
                    problem = str(exc)
                except remote_module.PoolError as exc:
                    problem = (f"{exc} The paper is given up as soon as the chief "
                               "editor's desk answers.")
                claim_module.release(folder, me)
            elif action == "send":
                self.pool.send(folder)
            else:
                raise ValueError("only the chief editor can take a paper over from a "
                                 "colleague; ask them")
            view = self._view(folder)
            if problem:
                view["pool_error"] = problem
            self._json(view)
            return
        if action == "take":
            claim_module.take(folder, me)
        elif action == "take_over":
            claim_module.take_over(folder, me)
            self._indico_wants(folder)
            # The letter is signed by the paper's editor: from now on, that is us.
            if me.name:
                review = ReviewState.load(folder)
                review.editor = me.name
                review.save(folder)
        elif action == "release":
            if claim_module.release(folder, me) and ReviewState.load(folder).status not in (
                    "done", "needs_author"):
                self._indico_wants(folder, unassign=True)
        else:
            raise ValueError("a claim is take, take_over or release")
        self._json(self._view(folder))

    def _set_editor(self, body: dict) -> None:
        changes = {"editor": str(body.get("editor", "")).strip()[:120]}
        if "compile" in body:
            changes["compile"] = bool(body.get("compile"))
        config = me_module.update_settings(self.home, **changes)
        self._json({"editor": config.get("editor", ""),
                    "compile": config.get("compile", True)})

    def _decide(self, body: dict) -> None:
        folder, review = self._with_state(body)
        edit_id = str(body.get("id", ""))
        decision = str(body.get("decision", "undecided"))
        if decision not in ("accepted", "rejected", "reverted", "undecided"):
            raise ValueError(
                "a decision is accept, reject, revert or undecided"
            )
        review.decide(edit_id, decision)
        review.save(folder)
        self._json(self._view(folder))

    def _edit_note(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.set_edit_note(str(body.get("id", "")), str(body.get("note", "")))
        review.save(folder)
        self._json({"ok": True})

    def _finding(self, body: dict) -> None:
        folder, review = self._with_state(body)
        key = str(body.get("key", ""))
        if "handled" in body:
            review.set_handled(key, bool(body.get("handled")))
        if "note" in body:
            review.set_finding_note(key, str(body.get("note", "")))
        review.save(folder)
        self._json({"ok": True})

    def _my_note(self, body: dict) -> None:
        folder, review = self._with_state(body)
        text = str(body.get("text", "")).strip()
        if not text:
            raise ValueError("the note is empty")
        severity = str(body.get("severity", "worth_a_look"))
        if severity not in state_module.SEVERITY_CHOICES:
            severity = "worth_a_look"
        note = review.add_note(EditorNote(
            text=text[:4000],
            where=str(body.get("where", "")).strip()[:200],
            severity=severity,
            for_author=bool(body.get("for_author", True)),
        ))
        review.save(folder)
        self._json({"note": note.model_dump(), "paper": self._view(folder)})

    def _delete_my_note(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.remove_note(str(body.get("id", "")))
        review.save(folder)
        self._json(self._view(folder))

    def _my_edit(self, body: dict) -> None:
        folder, review = self._with_state(body)
        try:
            line = int(body.get("line"))
        except (TypeError, ValueError) as exc:
            raise ValueError("no line number was given") from exc
        before = str(body.get("before", ""))
        after = str(body.get("after", ""))
        if before == after:
            raise ValueError("that line is unchanged, so there is nothing to save")
        if "\n" in after or "\r" in after:
            raise ValueError("a line edit cannot add new lines — edit one line at a time")

        # Verify the line still says what the editor was shown.
        current = paper_module.compose(paper_module.Paper(folder))
        lines = current.splitlines()
        if not (0 < line <= len(lines)) or lines[line - 1] != before:
            raise ValueError(
                "that line has changed since the page was loaded. Reload the paper "
                "and try again — nothing was saved."
            )

        edit = review.add_manual_edit(ManualEdit(
            line=line, before=before, after=after,
            note=str(body.get("note", "")).strip()[:2000],
        ))
        review.save(folder)
        self._json({"edit": edit.model_dump(), "paper": self._view(folder)})

    def _delete_my_edit(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.remove_manual_edit(str(body.get("id", "")))
        review.save(folder)
        self._json(self._view(folder))

    def _paper_note(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.paper_note = str(body.get("note", "")).strip()[:8000]
        review.touch()
        review.save(folder)
        self._json({"ok": True})

    def _letter(self, body: dict) -> None:
        folder, review = self._with_state(body)
        text = str(body.get("letter", ""))
        review.letter_override = "" if body.get("reset") else text[:40000]
        review.touch()
        review.save(folder)
        self._json({"letter": paper_module.letter_text(paper_module.Paper(folder)),
                    "letter_override": review.letter_override})

    def _prepare(self, body: dict) -> None:
        # Preparing rewrites the agent's files under a paper (the editor's
        # decisions are kept), so a paper another desk is editing is left alone.
        if self.pool:
            raise ValueError("Papers are prepared on the chief editor's desk. Ask them "
                             "to prepare this one again if it needs it.")
        compile_pdf = bool(self._config().get("compile", True))
        desk_id = self._me().desk_id

        def theirs(folder: Path) -> claim_module.Claim | None:
            held = claim_module.current(folder)
            return held if held and held.desk_id != desk_id else None

        skipped = 0
        if body.get("all"):
            folders = []
            for folder in state_module.submission_folders(self.root):
                if not body.get("force") and (
                        folder / "aiagent_prescreen" / "report.json").exists():
                    continue
                if theirs(folder):
                    skipped += 1
                    continue
                folders.append(folder)
            label = f"Preparing {len(folders)} paper(s)"
        else:
            folders = [self._folder(body.get("folder"))]
            held = theirs(folders[0])
            if held:
                raise claim_module.Held(held, desk_id)
            label = f"Preparing {state_module.submission_name(folders[0])}"
        if not folders:
            message = "Every paper is already prepared."
            if skipped:
                message = (f"Nothing to prepare: {skipped} paper(s) left alone because "
                           "another editor is working on them.")
            self._json({"job": None, "message": message})
            return
        job_id = self.jobs.start(label, folders, compile_pdf=compile_pdf)
        self._json({"job": self.jobs.status(job_id), "skipped": skipped})

    def _close(self, body: dict) -> None:
        if self.pool and self.pool.mode_of(self._folder(body.get("folder"))) == "qa":
            raise ValueError("this paper was taken for QA: pass or fail its QA instead")
        folder, review = self._with_state(body)
        # Edited again after a failed QA: it waits for a new QA (the failed one
        # stays in the history).
        if review.qa.status == "failed":
            review.qa = state_module.QAState(history=review.qa.history)
        editor = str(body.get("editor", "")).strip()
        if editor:
            review.editor = editor[:120]
        status = str(body.get("status", "done"))
        if status not in ("done", "needs_author"):
            status = "done"
        review.save(folder)
        result = paper_module.close_paper(
            folder, status=status,
            compile_pdf=bool(self._config().get("compile", True)),
        )
        # Finished, or back with the author: either way nobody is editing it now.
        claim_module.release(folder, self._me())
        if self.pool:
            # Sent to the chief one last time, and given back. If the chief's
            # desk cannot be reached now, it is sent (and given back) later.
            try:
                self.pool.give_back(folder)
                result["pool"] = "sent"
            except remote_module.Refused as exc:
                result["pool_error"] = str(exc)
            except remote_module.PoolError as exc:
                result["pool_error"] = (f"{exc} It is sent as soon as the chief "
                                        "editor's desk answers.")
        self._json(result)

    def _reopen(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.status = "in_review"
        review.closed_at = ""
        review.save(folder)
        self._json(self._view(folder))

    # -- Indico: the account, and keeping it in step --------------------------
    def _indico_wants(self, folder: Path, *, unassign: bool = False) -> None:
        """The chief's own desk took (or let go of) a paper: tell Indico."""
        if not self.sync:
            return
        found = account_module.user(self.home)
        self.sync.want(state_module.submission_name(folder), indico_id=found.get("id"),
                       name=found.get("name") or self._me().name, unassign=unassign)

    def _indico_url(self) -> str:
        if self.chief:
            return self.chief.url
        if self.pool:
            url = self.pool.view().get("indico", "")
            if not url:
                raise ValueError("the chief editor's desk has not said which Indico it uses "
                                 "yet; try again once it is reachable")
            return url
        conference = indico_module.Conference.open(self.root)
        from src.desk.chief import DEFAULT_URL

        return (conference.base_url if conference and conference.base_url else DEFAULT_URL)

    def _indico_account(self, body: dict) -> None:
        if body.get("disconnect"):
            account_module.disconnect(self.home)
            self._json(self._account())
            return
        account_module.connect(str(body.get("token", "")), self._indico_url(), self.home)
        if self.sync:
            self.sync.wake.set()              # read Indico with it straight away
        self._json(self._account())

    def _chief_indico_sync(self, body: dict) -> None:
        if not self.sync:
            raise ValueError("only the chief editor's desk keeps Indico in step")
        was_on = self.sync.enabled
        self.sync.set_enabled(bool(body.get("enabled")))
        if self.sync.enabled and not was_on and self.sharing:
            # Papers taken while it was off are assigned now.
            self.sharing.assign_held()
        self._json(self.sync.view())

    def _chief_given_up(self, body: dict) -> None:
        """Papers editors gave up; with ``dismiss``, the chief has seen one (or "all")."""
        if not self.sharing:
            raise ValueError("only the chief editor's desk hears from editors")
        notice = str(body.get("dismiss", "")).strip()
        if notice:
            self.sharing.dismiss(notice)
        self._json({"given_up": self.sharing.given_up()})

    def _chief_free(self, body: dict) -> None:
        """Free a paper from whoever holds it, so any editor can take it."""
        if not self.sharing:
            raise ValueError("only the chief editor's desk frees papers")
        folder = self._folder(body.get("folder"))
        self._json({"freed": self.sharing.free(state_module.submission_name(folder))})

    def _chief_editing_desk(self, body: dict) -> None:
        """Open the chief's own editing desk (starting it if need be)."""
        if not self.editing:
            raise ValueError("this desk cannot open an editing desk")
        self._json({"url": self.editing.open()})

    # -- an editor joined to the chief's desk ------------------------------
    def _joined(self):
        if self.pool is None:
            raise ValueError("this desk is not joined to a chief editor's desk "
                             "(start it with --join)")
        return self.pool

    def _pool_papers(self, body: dict) -> None:
        self._json(self._joined().listing())

    def _pool_take(self, body: dict) -> None:
        mode = str(body.get("mode") or "edit")
        folder = self._joined().take(str(body.get("paper", "")), mode)
        self._json({"folder": str(folder), "mode": mode})

    def _qa(self, body: dict) -> None:
        """The QA of a paper taken for QA: passed, or failed back to editing."""
        pool = self._joined()
        folder = self._folder(body.get("folder"))
        if pool.mode_of(folder) != "qa":
            raise ValueError("this paper was taken to edit it, not for QA")
        verdict = str(body.get("verdict", ""))
        if verdict not in ("passed", "failed"):
            raise ValueError("a QA is passed or failed")
        note = " ".join(str(body.get("note", "")).split())[:2000]
        if verdict == "failed" and not note:
            raise ValueError("say what needs fixing: the editor who takes it to re-edit "
                             "reads it")
        folder, review = self._with_state(body)
        me = self._me()
        at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        review.qa.status, review.qa.by, review.qa.at, review.qa.note = verdict, me.name, at, note
        review.qa.history.append({"status": verdict, "by": me.name, "at": at, "note": note})
        if verdict == "failed":
            review.status, review.closed_at = "in_review", ""    # back to editing
        review.save(folder)
        claim_module.release(folder, me)
        result = {"verdict": verdict}
        # Sent to the chief one last time, and given back, as when finishing.
        try:
            pool.give_back(folder)
            result["pool"] = "sent"
        except remote_module.Refused as exc:
            result["pool_error"] = str(exc)
        except remote_module.PoolError as exc:
            result["pool_error"] = (f"{exc} It is sent as soon as the chief editor's "
                                    "desk answers.")
        self._json(result)

    def _pool_send(self, body: dict) -> None:
        pool = self._joined()
        folder = self._folder(body.get("folder"))
        pool.require_held(folder)
        pool.send(folder)
        self._json(self._view(folder))

    # -- files ----------------------------------------------------------
    def _serve_file(self, query: dict) -> None:
        folder = self._folder(_one(query, "folder"))
        name = _one(query, "name") or ""
        if not name or "\\" in name:
            raise ValueError("no file was named")

        base = (folder / "aiagent_prescreen").resolve()
        target = (base / name).resolve()
        # Allow the author's original PDF, which sits one level up.
        if base not in target.parents and target.parent != base:
            allowed_parent = (folder / "PDF").resolve()
            if target.parent != allowed_parent:
                raise ValueError("that file is not part of this paper")
        if not target.is_file():
            self._error("that file does not exist", HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() in (".tex", ".md", ".txt", ".bib", ".patch", ".log"):
            content_type = "text/plain; charset=utf-8"
        data = target.read_bytes()
        disposition = "inline" if target.suffix.lower() == ".pdf" else "inline"
        self._send(HTTPStatus.OK, data, content_type,
                   {"Content-Disposition": f'{disposition}; filename="{target.name}"'})


def _one(query: dict, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _settle_model(enabled: bool) -> tuple[bool, str]:
    """Decide once whether a model is really in play.

    Returns ``(in_use, line_for_the_launcher_window)``.  Asked here, at
    start-up, rather than discovered by each paper in turn: an editor who
    asked for a model and is quietly not getting one has the worst of both
    worlds — they wait for it and do not get it — so this says which of the
    two is happening, in words that suggest what to do about it.

    When the model is not usable the environment is put back to "off" as well
    as the flag, because one sanctioned use of a model reads the environment
    directly.  Half a model is worse than none: it is the state nobody can
    describe afterwards.
    """
    import os
    import textwrap

    if not enabled:
        return False, ""

    from src.llm import client

    ok, reason = client.reachable()
    if ok:
        return True, f"  Model:    {reason}\n"

    os.environ["LLM_ENABLED"] = "false"
    line = textwrap.fill(
        f"NOT USED — {reason} Papers are screened without it; "
        "every check that does not need a model still runs.",
        width=68, initial_indent="  Model:    ",
        subsequent_indent="            ",
    ) + "\n"
    return False, line


def _llm_state(enabled: bool) -> dict:
    """What to tell the page about the model backend."""
    from src.llm import client

    conf = client.settings()
    return {"enabled": bool(enabled), "model": conf["model"] if enabled else "",
            "base_url": conf["base_url"] if enabled else ""}


def serve(root: Path, *, host: str = "127.0.0.1", port: int = 8765,
          open_browser: bool = True, llm: bool = False,
          home: Path | None = None, chief=None, pool=None, sharing=None,
          sync=None, door_host: str = "0.0.0.0", editing=None,
          close_with_stdin: bool = False) -> None:
    """Start the desk and block until interrupted.

    *door_host*: where the chief's door for editors listens (127.0.0.1 with
    --no-share). *close_with_stdin*: the chief's own editing desk, started by
    the managing desk, closes when the managing desk does (src.desk.editing).
    """
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a folder.")

    jobs = JobRunner(llm=llm)
    if sharing is not None:
        from src.desk import pool as pool_module

        pool_module.start(sharing, host=door_host)
    handler = partial(DeskHandler, root=root, jobs=jobs, home=home, chief=chief,
                      pool=pool, sharing=sharing, sync=sync, editing=editing)

    # Find a free port rather than failing when one desk is already open.
    last_error: OSError | None = None
    httpd = None
    for candidate in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((host, candidate), handler)
            port = candidate
            break
        except OSError as exc:
            last_error = exc
    if httpd is None:
        raise SystemExit(f"Could not start the review desk: {last_error}")

    url = f"http://{host}:{port}/"
    stamp = datetime.now().strftime("%H:%M")
    if pool is not None:
        # So the chief's managing page, or a second start, finds this desk.
        from src.desk import editing as editing_module

        editing_module.mark_open(me_module.settings_dir(home), port)
    if close_with_stdin:
        import sys

        def close_when_the_managing_desk_does() -> None:
            try:
                sys.stdin.read()
            except (OSError, ValueError, AttributeError):
                pass
            print("\n  The managing desk closed, so this editing desk closes too.",
                  flush=True)
            httpd.shutdown()

        threading.Thread(target=close_when_the_managing_desk_does, daemon=True).start()

    jobs.llm, model_line = _settle_model(llm)
    mode_line = ""
    if chief is not None:
        mode_line = "\n  Mode:     chief editor, managing" + (
            f" (Indico event {chief.event_id})" if chief.event_id else " (no Indico event chosen yet)")
        mode_line += ("\n  Editing:  not on this page: its Edit papers button opens "
                      "your editing desk")
    if sharing is not None:
        view = sharing.view()
        if view["local_only"]:
            mode_line += ("\n  Editors:  this computer only (--no-share): your own "
                          "editing desk")
        else:
            mode_line += ("\n  Editors:  join at " + "  or  ".join(view["addresses"])
                          + f"\n            with the code {view['code']}")
    papers_line = f"Papers:   {root}"
    if pool is not None:
        mode_line += f"\n  Mode:     editor, joined to the chief's desk at {pool.pool.url}"
        papers_line = f"Copies:   {root}  (kept by the desk; nothing to set up)"
    # flush=True matters: Python buffers stdout when it is not a terminal, and
    # the launcher window is exactly where an editor reads the address if the
    # browser did not open by itself.  Without this the window stays blank.
    banner = f"""
  ┌──────────────────────────────────────────────────────────┐
  │  JACoW review desk                                       │
  └──────────────────────────────────────────────────────────┘

  {papers_line}{mode_line}
  Address:  {url}
{model_line}
  A browser window should have opened. If it did not, copy the
  address above into your browser.

  Leave this window open while you work.
  To finish for the day, close this window.

  Your work is saved as you go — there is nothing to save.
  (started {stamp})
"""
    print(banner, flush=True)

    if open_browser:
        import webbrowser

        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Review desk closed. Your work is saved.\n", flush=True)
    finally:
        httpd.server_close()
