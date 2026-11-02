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

from pydantic import BaseModel, ConfigDict, Field


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


class RevisionFile(_Model):
    """One file on a revision.

    ``file_type`` is a numeric id, not a name: 192 and 193 on HIAT2025 are the
    main document and its images. Names come from
    ``GET /editing/api/<type>/file-types`` and differ per event, so nothing here
    hardcodes them.
    """

    id: int
    uuid: str = ""
    filename: str
    content_type: str = ""
    size: int = 0
    file_type: int = 0
    download_url: str = ""
    external_download_url: str = ""

    @property
    def is_word(self) -> bool:
        return self.filename.lower().endswith((".docx", ".doc"))

    @property
    def is_archive(self) -> bool:
        return self.filename.lower().endswith((".zip", ".tar.gz", ".tgz"))


class Revision(_Model):
    """One revision, with the urls Indico hands out for acting on it.

    The urls are used in preference to anything this client could build: they
    are correct by construction, and they change between Indico versions.
    """

    id: int
    created_dt: str = ""
    comment: str = ""
    files: list[RevisionFile] = []
    download_files_url: str = ""
    create_comment_url: str = ""
    custom_action_url: str = ""
    confirm_url: str | None = None
    custom_actions: list[dict] = []


class EditableDetail(_Model):
    """One editable in full — revisions, files, and what this editor may do.

    The permission block is the part worth reading before showing a button.
    ``can_perform_editor_actions`` is false on a paper assigned to someone else,
    so a tool that offers "accept" on every paper is offering something that
    will fail. Better to know before the editor spends the work.
    """

    id: int
    revisions: list[Revision] = []
    editor: IndicoUser | None = None
    editing_enabled: bool = True
    has_published_revision: bool = False
    review_conditions_valid: bool = True
    can_comment: bool = False
    can_create_internal_comments: bool = False
    can_perform_editor_actions: bool = False
    can_perform_submitter_actions: bool = False
    can_assign_self: bool = False
    can_unassign: bool = False

    @property
    def latest(self) -> Revision | None:
        """The newest revision, by creation time rather than by position."""
        if not self.revisions:
            return None
        return max(self.revisions, key=lambda r: (r.created_dt, r.id))

    @property
    def latest_id(self) -> int | None:
        newest = self.latest
        return newest.id if newest else None

    def why_not_editable(self) -> str:
        """Empty when this editor may act; otherwise the reason, in plain words."""
        if not self.editing_enabled:
            return "editing is switched off for this paper"
        if not self.revisions:
            return "the author has not submitted anything yet"
        if self.can_perform_editor_actions:
            return ""
        if self.editor is not None:
            return f"this paper is assigned to {self.editor.full_name}"
        return "you are not assigned to this paper — take it first"


class ContributionPerson(_Model):
    """One person on a contribution, as Indico's event export describes them."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    first_name: str | None = ""
    last_name: str | None = ""
    full_name: str | None = Field("", alias="fullName")
    affiliation: str | None = ""

    @property
    def name(self) -> str:
        return " ".join(f"{self.first_name or ''} {self.last_name or ''}".split()) or (
            self.full_name or "")


class ContributionAuthors(_Model):
    """A contribution's title and authors, with roles and affiliations.

    The editing list names the people on a paper but not which of them are
    authors (it includes speakers) nor where they work; the event export,
    ``/export/event/<id>.json?detail=contributions``, has both. ``db_id`` is the
    id the editing routes take, the same as :attr:`ContributionRow.id`.

    Unlike the editing payloads above, these field names come from Indico's
    export serializer and have not yet been checked against a payload from
    indico.jacow.org: every field is optional, so a difference shows up as
    missing authors, never as a crash.
    """

    db_id: int
    friendly_id: int | None = None
    title: str = ""
    primaryauthors: list[ContributionPerson] = []
    coauthors: list[ContributionPerson] = []
    speakers: list[ContributionPerson] = []

    def authors(self) -> list[tuple[ContributionPerson, str]]:
        """``(person, role)`` for every author, primary first; speakers who are
        not also authors are left out."""
        out: list[tuple[ContributionPerson, str]] = []
        seen: set[str] = set()
        for people, role in ((self.primaryauthors, "primary"), (self.coauthors, "coauthor")):
            for one in people:
                key = one.name.casefold()
                if key and key not in seen:
                    seen.add(key)
                    out.append((one, role))
        return out
