"""The shapes Indico's editing API actually returns.

Pinned against real payloads from indico.jacow.org, event 82 (HIAT2025), rather
than against the source of a version we do not run. Every model ignores unknown
fields, because Indico adds them between releases and a new key must never stop
an editor working.

One field is load-bearing and easy to get wrong: a contribution has both
``friendly_id`` (the number an editor sees, 4) and ``id`` (6680). **The editing
routes take ``id``** — Indico's own ``timeline_url`` in the same payload reads
``/event/82/contributions/6680/editing/paper``. Using the friendly id gives a
404 on some papers and, worse, the wrong paper on others.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IndicoUser(_Model):
    id: int
    full_name: str = ""
    identifier: str = ""


class IndicoTag(_Model):
    id: int
    code: str
    title: str = ""
    color: str = ""
    system: bool = False
    is_used_in_revision: bool = False

    @property
    def verbose(self) -> str:
        return f"{self.code}: {self.title}"


class EditableSummary(_Model):
    """The editable as the list endpoint describes it — no revisions, a count."""

    id: int
    type: str = "paper"
    state: str = ""
    revision_count: int = 0
    last_update_dt: str = ""
    editor: IndicoUser | None = None
    tags: list[IndicoTag] = []
    timeline_url: str = ""


class ContributionRow(_Model):
    """One row of the editable list — the table an editor sees in Indico."""

    id: int                      # the id the editing routes take
    friendly_id: int             # the id an editor recognises
    code: str = ""
    title: str = ""
    persons: list[str] = []
    keywords: list[str] = []
    editable: EditableSummary | None = None

    @property
    def submitted(self) -> bool:
        """False for the rows Indico shows as 'Unknown': nothing sent yet."""
        return self.editable is not None

    @property
    def state(self) -> str:
        return self.editable.state if self.editable else "not_submitted"

    @property
    def editor_name(self) -> str:
        return self.editable.editor.full_name if (
            self.editable and self.editable.editor) else ""

    @property
    def tag_codes(self) -> list[str]:
        return [t.code for t in self.editable.tags] if self.editable else []

    @property
    def label(self) -> str:
        return f"{self.code or self.friendly_id}"
