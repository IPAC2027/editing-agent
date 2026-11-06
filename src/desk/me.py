"""Who is at this desk: settings kept on the editor's own computer.

The editor's name used to live in the paper folder (``.aiagent_desk.json``).
That is right for one editor on one computer and wrong as soon as the folder is
shared: every desk on the share read the same file, so the last name typed
became "you" for everybody — the wrong papers showed as "Yours", and letters
went out signed by a colleague.

So the name, and the choice of whether to build PDFs (which depends on whether
*this* computer has TeX), are kept in the editor's home folder. Each desk also
has a random id, made once and kept there, which is what a claim on a paper
records: names can be blank, mistyped or shared, and a computer's network name
changes with the network it is on.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.desk import files

#: Set this to keep the settings somewhere else (the tests do).
HOME_ENV = "AIAGENT_HOME"
SETTINGS_FILENAME = "desk.json"


def settings_dir(home: Path | None = None) -> Path:
    if home is not None:
        return Path(home)
    configured = os.environ.get(HOME_ENV)
    return Path(configured).expanduser() if configured else Path.home() / ".aiagent"


def settings_path(home: Path | None = None) -> Path:
    return settings_dir(home) / SETTINGS_FILENAME


def load_settings(home: Path | None = None) -> dict:
    try:
        data = json.loads(settings_path(home).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — no settings yet, or unreadable ones
        return {}
    return data if isinstance(data, dict) else {}


def update_settings(home: Path | None = None, **changes) -> dict:
    """Change some settings and keep the rest; returns them all."""
    settings = load_settings(home)
    settings.update(changes)
    try:
        files.write_text(settings_path(home), json.dumps(settings, indent=2))
    except OSError:
        pass
    return settings


def _machine() -> str:
    try:
        return socket.gethostname().split(".")[0] or "this computer"
    except OSError:
        return "this computer"


def _account() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — no login name in this environment
        return ""


@dataclass(frozen=True)
class Me:
    """The editor at this desk."""

    desk_id: str
    name: str = ""
    machine: str = ""
    account: str = ""

    @property
    def label(self) -> str:
        """How others see this desk: the editor's name, else who and where."""
        if self.name:
            return self.name
        if self.account:
            return f"{self.account} on {self.machine}"
        return f"the editor on {self.machine}"


#: Desk ids that could not be saved (a read-only home folder), kept for as
#: long as the desk runs so its claims stay its own.
_UNSAVED_IDS: dict[str, str] = {}


def current(home: Path | None = None) -> Me:
    """The editor at this desk, making the desk's id the first time."""
    settings = load_settings(home)
    desk_id = str(settings.get("desk_id") or "")
    if not desk_id:
        key = str(settings_path(home))
        desk_id = _UNSAVED_IDS.get(key) or uuid.uuid4().hex
        settings = update_settings(home, desk_id=desk_id)
        if load_settings(home).get("desk_id") != desk_id:
            _UNSAVED_IDS[key] = desk_id
    return Me(desk_id=desk_id, name=str(settings.get("editor") or "").strip(),
              machine=_machine(), account=_account())
