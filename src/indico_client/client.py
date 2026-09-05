"""An editor's own credential, against Indico's editing API.

Deliberately not a service account. JACoW's Indico has one editing-service slot
per event and it is taken, so this agent reaches Indico the only way left: as
the editor sitting in front of it. That has one virtue and one cost, and both
are worth stating where the code is.

The virtue is provenance. Everything this client writes is done *by that
editor*, under their name, in their event — there is no machine identity to
explain to an author, and no way for the tool to act when nobody asked it to.

The cost is the credential. Indico has no fine-grained scope for the editing
module: reads need ``read:everything`` and writes need ``full:everything``,
which is everything that person can do anywhere in Indico. So this client:

* never accepts a token as a function argument that might get logged — it comes
  from the environment or the OS keyring, and :meth:`redacted` is the only way
  it is ever rendered;
* refuses to run against a base URL it was not configured with, so a redirect
  cannot walk the token to another host;
* sends nothing that is not a direct consequence of something the editor asked
  for.

The routes are Indico's own, verified against a running 3.x instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.indico_client.models import ContributionRow, EditableDetail, IndicoTag

TOKEN_ENV = "INDICO_TOKEN"
KEYRING_SERVICE = "jacow-prescreen"


class IndicoError(RuntimeError):
    """Anything the API refused, phrased for an editor rather than a developer."""


class IndicoAuthError(IndicoError):
    pass


class ReadOnlyViolation(IndicoError):
    """A client opened read-only was asked to send a modifying request."""


class RevisionMoved(IndicoError):
    """The paper changed in Indico since it was pulled.

    The one failure that matters most in an offline tool: an editor works for an
    hour on revision 3 while the author submits revision 4. Pushing then would
    bury the author's newer file under an older one. Every write checks first.
    """


def load_token(*, keyring_user: str | None = None) -> str:
    """The editor's personal token, from the environment or the OS keyring."""
    token = os.environ.get(TOKEN_ENV, "").strip()
    if token:
        return token
    try:
        import keyring  # noqa: PLC0415 — optional dependency

        stored = keyring.get_password(KEYRING_SERVICE, keyring_user or "default")
    except Exception:  # noqa: BLE001 — no keyring on this machine is normal
        stored = None
    if not stored:
        raise IndicoAuthError(
            "No Indico token found. Create one at <indico>/user/tokens/ with the "
            f"'read:everything' scope (and 'full:everything' to send results "
            f"back), then set {TOKEN_ENV} or store it in your keyring."
        )
    return stored.strip()


@dataclass
class IndicoClient:
    """One conference, one editable type, one editor."""

    base_url: str
    event_id: int
    token: str
    editable_type: str = "paper"
    timeout: float = 60.0
    read_only: bool = False
    """Refuse to send anything but GET.

    Not a promise in a docstring — a latch. When a task is "read the whole
    conference and touch nothing", the guarantee has to be enforced where the
    request is made, so that no later change to a caller can quietly turn a pull
    into a write. :class:`ReadOnlyViolation` is raised before the socket opens.
    """

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url.startswith("https://"):
            raise IndicoError(
                f"Refusing to send a token over an insecure connection: {self.base_url}"
            )

    # -- presentation ----------------------------------------------------
    @property
    def redacted(self) -> str:
        """The only rendering of the token that may appear anywhere."""
        return f"{self.token[:9]}…" if len(self.token) > 12 else "…"

    def __repr__(self) -> str:  # never let a traceback print the token
        return (f"IndicoClient(base_url={self.base_url!r}, event_id={self.event_id}, "
                f"token={self.redacted!r})")

    # -- urls ------------------------------------------------------------
    @property
    def _event(self) -> str:
        return f"{self.base_url}/event/{self.event_id}"

    def _api(self, tail: str) -> str:
        return f"{self._event}/editing/api/{tail}"

    def _contrib(self, contribution_id: int, tail: str = "") -> str:
        stem = f"{self._event}/api/contributions/{contribution_id}/editing/{self.editable_type}"
        return f"{stem}/{tail}" if tail else stem

    def timeline_url(self, contribution_id: int) -> str:
        """Where an editor would look at this paper in Indico."""
        return (f"{self._event}/contributions/{contribution_id}/"
                f"editing/{self.editable_type}")

    # -- plumbing --------------------------------------------------------
    def _guard(self, method: str, url: str) -> None:
        if self.read_only and method.upper() not in ("GET", "HEAD"):
            raise ReadOnlyViolation(
                f"This client was opened read-only and refuses to {method.upper()} "
                f"{url}. Nothing has been sent."
            )

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,  # a redirect to /login means "not authenticated"
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "jacow-prescreen",
            },
        )

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.status_code in (301, 302, 303, 307, 308):
            target = response.headers.get("location", "")
            if "/login" in target:
                raise IndicoAuthError(
                    "Indico did not accept the token. Check that the header is "
                    "'Authorization: Bearer <token>' and that the token has the "
                    "'read:everything' scope."
                )
            raise IndicoError(f"Unexpected redirect to {target}")
        if response.status_code == 401:
            raise IndicoAuthError("Indico rejected the token (401).")
        if response.status_code == 403:
            raise IndicoAuthError(
                "The token was accepted but is not allowed to do this (403). "
                "It probably needs a wider scope, or you are not an editor on "
                "this event."
            )
        if response.status_code >= 400:
            raise IndicoError(
                f"Indico returned {response.status_code} for "
                f"{response.request.url.path}: {response.text[:200]}"
            )
        return response

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """The single place every request goes through, guard included."""
        self._guard(method, url)
        with self._client() as http:
            return self._check(http.request(method, url, **kwargs))

    def _get_json(self, url: str):
        return self.request("GET", url).json()

    # -- reads -----------------------------------------------------------
    def ping(self) -> int:
        """Number of contributions visible. The one-call 'is this set up right'."""
        return len(self.list_editables())

    def list_editables(self) -> list[ContributionRow]:
        """The table an editor sees, including papers not yet submitted."""
        raw = self._get_json(self._api(f"{self.editable_type}/list"))
        return [ContributionRow.model_validate(row) for row in raw]

    def tags(self) -> list[IndicoTag]:
        """This event's tag vocabulary — the codes editors classify with."""
        raw = self._get_json(self._api("tags"))
        return [IndicoTag.model_validate(tag) for tag in raw]

    def editable(self, contribution_id: int) -> EditableDetail:
        """One editable in full: its revisions, their files, and your rights."""
        return EditableDetail.model_validate(self._get_json(self._contrib(contribution_id)))

    def file_types(self) -> dict[int, str]:
        """``{id: name}`` for this event — files carry the id, not the name."""
        raw = self._get_json(self._api(f"{self.editable_type}/file-types"))
        return {ft["id"]: ft.get("name", str(ft["id"])) for ft in raw}

    def download_file(self, file: "object", destination: Path) -> Path:
        """One file of a revision, by the url Indico gave for it.

        Server-supplied urls are used rather than constructed ones: they are
        right by definition, and they have moved between Indico versions.
        """
        url = getattr(file, "external_download_url", "") or (
            self.base_url + getattr(file, "download_url", ""))
        self._guard("GET", url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._client() as http, http.stream("GET", url) as response:
            self._check(response)
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return destination

    def download_revision_files(self, contribution_id: int, revision_id: int,
                                destination: Path) -> Path:
        """The revision's files, as the zip Indico builds for exactly this."""
        url = (f"{self._event}/contributions/{contribution_id}/editing/"
               f"{self.editable_type}/{revision_id}/files.zip")
        self._guard("GET", url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._client() as http, http.stream("GET", url) as response:
            self._check(response)
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return destination

    # -- the guard every write goes through -------------------------------
    def current_revision_id(self, contribution_id: int) -> int | None:
        """The newest revision id, or ``None`` if nothing has been submitted.

        Newest by creation time, not by position in the list: relying on the
        order Indico happens to serialise them in is the kind of assumption that
        holds for a year and then quietly writes to the wrong revision.
        """
        return self.editable(contribution_id).latest_id

    def assert_unchanged(self, contribution_id: int, revision_id: int) -> None:
        """Refuse to write against a paper the author has moved on from."""
        current = self.current_revision_id(contribution_id)
        if current != revision_id:
            raise RevisionMoved(
                f"This paper was revision {revision_id} when you pulled it and is "
                f"revision {current} in Indico now — the author has submitted "
                "again. Pull it again before sending anything back; your "
                "decisions are kept."
            )
