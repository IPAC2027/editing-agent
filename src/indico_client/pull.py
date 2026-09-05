"""Pull a whole conference down to disk, read-only, for study.

The purpose is measurement, not editing. Every accepted JACoW paper carries two
things worth having side by side: what the author submitted, and what the
editors made of it — plus the codes the editors chose to describe the
difference. That is a labelled corpus of real editorial judgement, and it is
the evidence this project has never had for deciding which checks belong in the
automatic tier.

Three rules shape this module.

**It writes nothing to Indico.** The client is opened with ``read_only=True``,
which refuses any non-GET request before the socket opens. Indico does offer a
bulk-archive endpoint, but preparing that archive is a POST, so this module does
not use it — it fetches each revision's own ``files.zip`` with a GET instead.
Slower, and unambiguous.

**It says what it will cost before it costs it.** File sizes come back in the
metadata, so the whole download can be measured without downloading anything.
A conference of Word papers is tens of gigabytes; nobody should discover that
halfway through.

**It is resumable and it never re-downloads.** A pull that dies at paper 140 of
190 picks up where it stopped.

The layout is deliberately the one :func:`~src.workflow.prescreen.prescreen`
already understands, so a pulled paper can be screened where it lies::

    <dest>/index.json
    <dest>/MOX01/manifest.json
    <dest>/MOX01/original/Source_Files/MOX01.docx     <- earliest revision
    <dest>/MOX01/current/Source_Files/MOX01.docx      <- latest revision
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.indico_client.client import IndicoClient, IndicoError
from src.indico_client.models import ContributionRow, Revision

#: Which revisions to fetch.
WHICH = ("first-last", "latest", "all")


def _safe(name: str) -> str:
    """A folder name from a paper code, with no surprises in it."""
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in name.strip()]
    return "".join(keep).strip("-") or "paper"


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


@dataclass
class RevisionPlan:
    """One revision of one paper, and where its files will land."""

    revision: Revision
    role: str                     # "original" | "current" | "rev-<id>"

    @property
    def bytes(self) -> int:
        return sum(f.size for f in self.revision.files)


@dataclass
class PaperPlan:
    """One paper: which revisions to fetch, and what the editors said about it."""

    row: ContributionRow
    revisions: list[RevisionPlan] = field(default_factory=list)
    note: str = ""                # why nothing will be fetched, when nothing will

    @property
    def folder(self) -> str:
        return _safe(self.row.code or f"c{self.row.friendly_id}")

    @property
    def bytes(self) -> int:
        return sum(r.bytes for r in self.revisions)


@dataclass
class Plan:
    """The whole conference, costed."""

    papers: list[PaperPlan] = field(default_factory=list)

    @property
    def fetchable(self) -> list[PaperPlan]:
        return [p for p in self.papers if p.revisions]

    @property
    def bytes(self) -> int:
        return sum(p.bytes for p in self.papers)

    @property
    def files(self) -> int:
        return sum(len(r.revision.files) for p in self.papers for r in p.revisions)

    def summary(self) -> str:
        skipped = len(self.papers) - len(self.fetchable)
        return (f"{len(self.fetchable)} paper(s), {self.files} file(s), "
                f"{_human(self.bytes)}"
                + (f"; {skipped} with nothing to fetch" if skipped else ""))


def build_plan(client: IndicoClient, *, which: str = "first-last",
               only: set[str] | None = None) -> Plan:
    """Ask Indico what is there, and what fetching it would cost.

    One detail request per paper and not a single byte of content — sizes are in
    the metadata. This is what ``--dry-run`` runs, and it is also the first half
    of a real pull, so the two can never disagree about what will be fetched.
    """
    if which not in WHICH:
        raise IndicoError(f"which must be one of {', '.join(WHICH)}")

    plan = Plan()
    for row in client.list_editables():
        if only and (row.code not in only and str(row.friendly_id) not in only):
            continue
        paper = PaperPlan(row=row)
        plan.papers.append(paper)

        if not row.submitted:
            paper.note = "nothing submitted"
            continue

        detail = client.editable(row.id)
        ordered = sorted(detail.revisions, key=lambda r: (r.created_dt, r.id))
        if not ordered:
            paper.note = "no revisions"
            continue

        if which == "all":
            chosen = [(r, f"rev-{r.id}") for r in ordered]
        elif which == "latest":
            chosen = [(ordered[-1], "current")]
        else:
            chosen = [(ordered[0], "original")]
            if len(ordered) > 1:
                chosen.append((ordered[-1], "current"))
            else:
                paper.note = "only one revision: the author's, never edited"

        paper.revisions = [RevisionPlan(revision=r, role=role) for r, role in chosen
                           if r.files]
        if not paper.revisions:
            paper.note = paper.note or "revisions carry no files"
    return plan


def _manifest(paper: PaperPlan) -> dict:
    """What this paper is, and what the editors said was wrong with it.

    The tags are the point of the exercise: they are the editors' own labels for
    the difference between ``original`` and ``current``.
    """
    row = paper.row
    editable = row.editable
    return {
        "code": row.code,
        "friendly_id": row.friendly_id,
        "contribution_id": row.id,
        "title": row.title,
        "persons": row.persons,
        "state": row.state,
        "editor": row.editor_name,
        "tags": [{"code": t.code, "title": t.title} for t in
                 (editable.tags if editable else [])],
        "revision_count": editable.revision_count if editable else 0,
        "revisions": [
            {
                "role": rp.role,
                "id": rp.revision.id,
                "created_dt": rp.revision.created_dt,
                "comment": rp.revision.comment,
                "files": [
                    {"filename": f.filename, "size": f.size,
                     "file_type": f.file_type, "content_type": f.content_type}
                    for f in rp.revision.files
                ],
            }
            for rp in paper.revisions
        ],
        "note": paper.note,
    }


def pull(client: IndicoClient, destination: Path, *, which: str = "first-last",
         only: set[str] | None = None, plan: Plan | None = None,
         on_paper=None) -> Plan:
    """Fetch the planned files. Skips anything already on disk at the right size.

    *on_paper* is called with ``(index, total, PaperPlan)`` before each paper, so
    a caller can show progress without this module knowing about a console.
    """
    plan = plan or build_plan(client, which=which, only=only)
    destination.mkdir(parents=True, exist_ok=True)

    fetchable = plan.fetchable
    for index, paper in enumerate(fetchable, start=1):
        if on_paper:
            on_paper(index, len(fetchable), paper)
        root = destination / paper.folder
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(
            json.dumps(_manifest(paper), indent=2, ensure_ascii=False),
            encoding="utf-8")

        for revision_plan in paper.revisions:
            # Source_Files/ is the layout `prescreen` expects, so a pulled paper
            # can be screened where it lies rather than moved first.
            target_dir = root / revision_plan.role / "Source_Files"
            for file in revision_plan.revision.files:
                target = target_dir / file.filename
                if target.exists() and file.size and target.stat().st_size == file.size:
                    continue        # already have it: a pull is resumable
                client.download_file(file, target)

    index_path = destination / "index.json"
    index_path.write_text(json.dumps({
        "event_id": client.event_id,
        "base_url": client.base_url,
        "editable_type": client.editable_type,
        "which": which,
        "papers": [_manifest(p) for p in plan.papers],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan
