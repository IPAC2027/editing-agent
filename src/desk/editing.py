"""The chief editor's own editing desk.

The chief's desk is a managing page: it reads Indico, downloads and prepares
the papers, opens the door editors come in by and keeps Indico's assignments
in step. It does not edit papers. To edit, the chief uses an editor's desk
like everyone else's, joined to their own door, with settings of its own
(``<settings>/editor``: its own desk id and Indico account), so the papers
they take are claimed, sent back and assigned in Indico exactly as anyone's.

**Edit papers** on the managing page starts that desk as a separate process
(:class:`EditingDesk`) and opens it. The process watches its stdin, whose
other end the managing desk holds: when the managing desk closes, or is
killed, the editing desk closes too.

While an editor's desk runs it notes its address in its settings folder
(``desk_open.json``), so a desk already open with those settings, started by
the button or in a terminal, is used rather than started a second time.
"""

from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from src.desk import files
from src.desk import me as me_module

OPEN_FILE = "desk_open.json"
LOG_FILE = "editing_desk.log"
FIRST_PORT = 8766


# ---------------------------------------------------------------------------
# An editor's desk that is open, for its settings folder
# ---------------------------------------------------------------------------

def mark_open(home: Path, port: int) -> None:
    """Note that an editor's desk with the settings in *home* answers on *port*."""
    path = Path(home) / OPEN_FILE
    mine = {"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}/"}
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


def open_desk(home: Path) -> str | None:
    """The address of another editor's desk open with the settings in *home*."""
    try:
        noted = json.loads((Path(home) / OPEN_FILE).read_text(encoding="utf-8"))
        port = int(noted["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if noted.get("pid") == os.getpid():
        return None
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url + "api/setup", timeout=2) as response:
            setup = json.loads(response.read())
    except Exception:  # noqa: BLE001 — closed, or something else on that port
        return None
    return url if isinstance(setup, dict) and setup.get("pool") else None


def _free_port(first: int) -> int:
    for port in range(first, first + 40):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise ValueError("no free port for the editing desk")


# ---------------------------------------------------------------------------
# The chief's editing desk, started from the managing page
# ---------------------------------------------------------------------------

class EditingDesk:
    """Starts, finds and closes the chief editor's own editing desk."""

    def __init__(self, door, *, command: list[str], home: Path,
                 extra_args: list[str] | None = None, port: int = FIRST_PORT,
                 wait: float = 45.0) -> None:
        self.door = door                 # src.desk.pool.Pool: the managing desk's door
        self.command = list(command)     # how to run the desk: [python, main.py]
        self.home = Path(home)           # the editing desk's own settings folder
        self.extra_args = list(extra_args or [])
        self.port = port
        self.wait = wait
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        atexit.register(self.close)

    def view(self) -> dict:
        url = open_desk(self.home)
        return {"open": bool(url), "url": url or ""}

    def open(self) -> str:
        """The editing desk's address, starting it first if it is not open."""
        with self.lock:
            url = open_desk(self.home)
            if url:
                return url
            if self.process is None or self.process.poll() is not None:
                self._start()
            return self._ready()

    def _start(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env[me_module.HOME_ENV] = str(self.home)
        args = self.command + [
            "--join", f"127.0.0.1:{self.door.port}", "--code", self.door.code,
            "--port", str(_free_port(self.port)), "--no-open", "--with-chief",
            *self.extra_args]
        with open(self.home / LOG_FILE, "w", encoding="utf-8") as log:
            self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log,
                                            stderr=subprocess.STDOUT, env=env)

    def _ready(self) -> str:
        deadline = time.monotonic() + self.wait
        while time.monotonic() < deadline:
            url = open_desk(self.home)
            if url:
                return url
            if self.process.poll() is not None:
                raise ValueError("Your editing desk did not start:\n" + self._log_tail())
            time.sleep(0.25)
        raise ValueError("Your editing desk is slow to start; click Edit papers again "
                         "in a moment.")

    def _log_tail(self, lines: int = 8) -> str:
        try:
            text = (self.home / LOG_FILE).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(no output)"
        return "\n".join(text.strip().splitlines()[-lines:]) or "(no output)"

    def close(self) -> None:
        """Close the editing desk this managing desk started (not one from a terminal)."""
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            process.stdin.close()            # the desk closes itself when this ends
        except (OSError, AttributeError):
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
