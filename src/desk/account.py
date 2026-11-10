"""The Indico account a desk works with, typed into the desk's own page.

The token is pasted once into the page, checked against Indico (``GET
/api/user/``, which names its owner) and kept in the editor's settings folder,
in a file only they can read. It never goes back to the page, into the papers
folder, or to another desk: the page is told only whose account it is.

* The chief's desk uses it to read the conference and keep Indico's editor
  assignments in step with who is working on what.
* An editor's desk uses it only to prove who the editor is in Indico: it is
  how they are known, in place of a typed name, and a desk without one cannot
  take a paper. Their desk tells the chief's desk that Indico user id and
  name (never the token), so the chief's desk can assign papers to the right
  person. Editors never have to open Indico.
* It also asks Indico, once in a while, whether that account is one of the
  conference's editing managers (:func:`manages_editing`): Indico lists no
  editing managers to anyone, but answers each account about itself. The
  chief's desk is told the answer, never the token.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from src.desk import me as me_module
from src.indico_client.client import TOKEN_ENV, TOKEN_FILE, IndicoClient, IndicoError

USER_SETTING = "indico_user"
_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_\-.~+/=]{16,256}$")


def token_path(home: Path | None = None) -> Path:
    return me_module.settings_dir(home) / TOKEN_FILE


def _write_private(path: Path, text: str) -> None:
    """Write *text* so that only this user can read it, replacing the file whole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.part")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def connect(token: str, base_url: str, home: Path | None = None) -> dict:
    """Check *token* with Indico at *base_url* and keep it; returns :func:`view`."""
    token = (token or "").strip()
    if not _TOKEN_SHAPE.match(token):
        raise ValueError("That does not look like an Indico token: copy the whole token "
                         "from Indico → My profile → API tokens.")
    try:
        user = IndicoClient(base_url=base_url, event_id=0, token=token).whoami()
    except IndicoError as exc:
        raise ValueError(f"Indico did not accept that token: {exc}") from None
    if not user:
        raise ValueError("Indico did not accept that token.")
    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p).strip()
    _write_private(token_path(home), token)
    settings = me_module.update_settings(home, **{USER_SETTING: {
        "id": int(user["id"]), "name": name, "url": base_url.rstrip("/")}})
    if not str(settings.get("editor") or "").strip() and name:
        me_module.update_settings(home, editor=name)
    return view(home)


def disconnect(home: Path | None = None) -> dict:
    try:
        token_path(home).unlink()
    except FileNotFoundError:
        pass
    me_module.update_settings(home, **{USER_SETTING: None})
    return view(home)


def user(home: Path | None = None) -> dict:
    """The Indico user whose token this desk holds: ``{id, name, url}`` or ``{}``."""
    if not token_path(home).is_file():
        return {}
    found = me_module.load_settings(home).get(USER_SETTING)
    return found if isinstance(found, dict) else {}


def manages_editing(event_url: str, event_id, home: Path | None = None
                    ) -> tuple[bool | None, str]:
    """Whether this desk's Indico account manages the event's editing.

    Indico is asked with the account's own token: ``(True | False, "")``, or
    ``(None, why)`` when it could not be asked. The token only ever goes to the
    Indico it was connected to; a conference somewhere else is not asked about.
    """
    found = user(home)
    if not found.get("id"):
        return None, ""
    mine = str(found.get("url") or "").rstrip("/")
    theirs = str(event_url or "").rstrip("/")
    if not theirs or not event_id:
        return None, "The chief editor's desk names no Indico event."
    if mine != theirs:
        return None, (f"Your Indico token is for {mine or 'another Indico'}, but the "
                      f"conference is on {theirs}: connect a token from {theirs}.")
    try:
        token = token_path(home).read_text(encoding="utf-8").strip()
        client = IndicoClient(base_url=mine, event_id=int(event_id), token=token,
                              timeout=15.0)
        return client.can_manage_editing(), ""
    except IndicoError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 — network trouble: asked again later
        return None, f"Could not ask Indico whether you manage its editing ({type(exc).__name__})."


def view(home: Path | None = None, *, typed_only: bool = False) -> dict:
    """What the page is told: whose account, never the token.

    *typed_only*: an editor's desk joined to the chief's, which is known by
    the account typed into it. A token in the environment names nobody there.
    """
    from src.indico_client import client

    found = user(home)
    if found:
        return {"connected": True, "name": found.get("name", ""), "id": found.get("id"),
                "url": found.get("url", ""), "source": "page"}
    if (os.environ.get(TOKEN_ENV, "").strip() and not typed_only
            and not client.TYPED_TOKEN_ONLY):
        return {"connected": True, "name": "", "id": None, "url": "",
                "source": "environment"}
    return {"connected": False, "name": "", "id": None, "url": "", "source": ""}
