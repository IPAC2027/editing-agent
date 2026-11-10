"""The one thing the desk changes in Indico: which editor has a paper.

Everything else in ``src.indico_client`` only reads (``IndicoClient`` is a
read-only latch). This writer is separate on purpose, and narrow:

* two requests only, both Indico's own editing-management routes for one
  event and one editable type —
  ``POST /event/<id>/editing/api/<type>/editables/assign`` and ``…/unassign``;
* Indico's own conflict check is used: each request says who Indico should
  have as the editor now, and Indico refuses (409) if that has changed, so a
  paper reassigned in Indico meanwhile is never taken from that editor;
* https only, no redirects followed, the token never rendered;
* people are named the way Indico requires: ``User:<id>:<signature>``, which
  only Indico can sign (``User.identifier``, keyed on the server's secret).
  Indico hands them out in its paper editors list and on each paper's
  editor; an unsigned ``User:<id>`` is refused (422 "User id signature
  missing"), so this writer refuses it before sending anything.

Read from the Indico 3.3 source (``editing/controllers/backend/editable_list.py``,
``editing/operations.py``): assigning and unassigning change the editor and
write an event-log entry; neither sends an email.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from src.indico_client.client import IndicoAuthError, IndicoError

ACTIONS = ("assign", "unassign")
#: Indico's signed identity for a user, e.g. ``User:1606:MTYwNg.abc…``.
SIGNED = re.compile(r"^User:(\d+):[A-Za-z0-9_\-.]+$")


def signed(identifier: str) -> str:
    """*identifier* if it is Indico's signed form for a user; IndicoError if not."""
    if not isinstance(identifier, str) or not SIGNED.match(identifier):
        raise IndicoError("Indico takes an editor only by the signed identity it gives "
                          f"out (User:<id>:<signature>), not {str(identifier)[:40]!r}.")
    return identifier


class AssignmentConflict(IndicoError):
    """Indico has a different editor on the paper than the desk expected."""


@dataclass
class AssignmentWriter:
    base_url: str
    event_id: int
    token: str
    editable_type: str = "paper"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url.startswith("https://"):
            raise IndicoError(f"Refusing to send a token over an insecure connection: "
                              f"{self.base_url}")
        if self.editable_type not in ("paper", "slides", "poster"):
            raise IndicoError(f"unknown editable type {self.editable_type!r}")

    def __repr__(self) -> str:
        return (f"AssignmentWriter(base_url={self.base_url!r}, event_id={self.event_id}, "
                "token='…')")

    def url(self, action: str) -> str:
        if action not in ACTIONS:
            raise IndicoError(f"the desk does not {action} anything in Indico")
        return (f"{self.base_url}/event/{int(self.event_id)}/editing/api/"
                f"{self.editable_type}/editables/{action}")

    def _post(self, action: str, body: dict) -> list:
        with httpx.Client(timeout=self.timeout, follow_redirects=False, headers={
                "Authorization": f"Bearer {self.token}", "Accept": "application/json",
                "User-Agent": "jacow-prescreen"}) as http:
            response = http.post(self.url(action), json=body)
        if response.status_code in (301, 302, 303, 307, 308):
            raise IndicoAuthError("Indico did not accept the token.")
        if response.status_code == 401:
            raise IndicoAuthError("Indico rejected the token (401).")
        if response.status_code == 403:
            raise IndicoAuthError(
                "Indico refused (403): the chief editor's token needs the "
                "'full:everything' scope and editing management on this event, and the "
                f"editor must be in the event's {self.editable_type} editing team.")
        if response.status_code == 409:
            raise AssignmentConflict("Indico has a different editor on this paper now.")
        if response.status_code >= 400:
            raise IndicoError(f"Indico returned {response.status_code} for {action}: "
                              f"{response.text[:200]}")
        try:
            return response.json()
        except ValueError:
            return []

    @staticmethod
    def _now(editable_id: int, current: str | None) -> dict:
        # Who Indico should have as the editor now (its conflict check);
        # omitted means "nobody".
        return {str(editable_id): signed(current)} if current else {}

    def assign(self, editable_id: int, editor: str, *, current: str | None = None) -> list:
        """Give the paper to *editor* (a signed identity); *current*: who has it now."""
        return self._post("assign", {
            "editables": [int(editable_id)], "editor": signed(editor),
            "editor_assignments": self._now(editable_id, current)})

    def unassign(self, editable_id: int, *, current: str) -> list:
        """Take the paper from *current* (a signed identity), if they still have it."""
        return self._post("unassign", {
            "editables": [int(editable_id)],
            "editor_assignments": self._now(editable_id, signed(current))})
