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
import traceback
import uuid
from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.desk import indico as indico_module
from src.desk import claim as claim_module
from src.desk import me as me_module
from src.desk import paper as paper_module
from src.desk import state as state_module
from src.desk.state import EditorNote, ManualEdit, ReviewState

#: Where the editor's name used to be kept: in the paper folder, shared by
#: every desk opened on it. Now kept per person (see ``src.desk.me``); the
#: name is still git-ignored so an old file never ends up in a commit.
LEGACY_CONFIG_FILENAME = ".aiagent_desk.json"


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
                self._jobs[job_id]["current"] = folder.name
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

    def status(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(job_id, {"id": job_id, "missing": True}))

    def active(self) -> list[dict]:
        with self._lock:
            return [dict(job) for job in self._jobs.values() if not job["finished"]]


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------

class DeskHandler(BaseHTTPRequestHandler):
    server_version = "JACoWReviewDesk/1.0"

    def __init__(self, *args, root: Path, jobs: JobRunner,
                 home: Path | None = None, **kwargs) -> None:
        self.root = root
        self.jobs = jobs
        # Where this editor's own settings live; None means their home folder.
        self.home = home
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
        return me_module.current(self.home)

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
                })
            elif route == "/api/worklist":
                conference = (indico_module.Conference.open(self.root)
                              if state_module.is_pulled_conference(self.root) else None)
                me = self._me()
                self._json({
                    "papers": [
                        row.model_dump() for row in state_module.worklist(
                            self.root, me=me.name, desk_id=me.desk_id)
                    ],
                    "indico": conference.summary() if conference else None,
                })
            elif route == "/api/paper":
                self._json(self._view(self._folder(_one(query, "folder"))))
            elif route == "/api/job":
                self._json(self.jobs.status(_one(query, "id") or ""))
            elif route == "/file":
                self._serve_file(query)
            else:
                self._error("unknown address", HTTPStatus.NOT_FOUND)
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
            }.get(route)
            if handler is None:
                self._error("unknown address", HTTPStatus.NOT_FOUND)
                return
            handler(body)
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

    # -- actions --------------------------------------------------------
    def _indico_refresh(self, body: dict) -> None:
        import httpx

        from src.indico_client.client import IndicoError

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
        was_free = claim_module.current(folder) is None
        claim_module.take(folder, me)
        review = ReviewState.load(folder)
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
        if action == "take":
            claim_module.take(folder, me)
        elif action == "take_over":
            claim_module.take_over(folder, me)
            # The letter is signed by the paper's editor: from now on, that is us.
            if me.name:
                review = ReviewState.load(folder)
                review.editor = me.name
                review.save(folder)
        elif action == "release":
            claim_module.release(folder, me)
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
        folder, review = self._with_state(body)
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
        self._json(result)

    def _reopen(self, body: dict) -> None:
        folder, review = self._with_state(body)
        review.status = "in_review"
        review.closed_at = ""
        review.save(folder)
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
          home: Path | None = None) -> None:
    """Start the desk and block until interrupted."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a folder.")

    jobs = JobRunner(llm=llm)
    handler = partial(DeskHandler, root=root, jobs=jobs, home=home)

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

    jobs.llm, model_line = _settle_model(llm)
    # flush=True matters: Python buffers stdout when it is not a terminal, and
    # the launcher window is exactly where an editor reads the address if the
    # browser did not open by itself.  Without this the window stays blank.
    banner = f"""
  ┌──────────────────────────────────────────────────────────┐
  │  JACoW review desk                                       │
  └──────────────────────────────────────────────────────────┘

  Papers:   {root}
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
