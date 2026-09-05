"""What is in a pulled conference, and what can honestly be measured from it.

Reads the layout :mod:`~src.indico_client.pull` writes and answers three
questions, in this order:

1. **How many papers give a usable pair?** A paper the author submitted once and
   nobody edited teaches nothing. Neither does one whose ``current`` main file
   is byte-identical to its ``original`` — and there are more of those than one
   expects, because a revision can exist for reasons that never touched the
   text.
2. **In what format?** The LaTeX checks cannot be measured on a Word submission
   and vice versa, so the sample size for any given check is not the paper
   count. Saying so up front prevents a precision figure computed over four
   papers from being quoted as though it were computed over eighty.
3. **What did the editors say was wrong?** The tag histogram, joined with what
   the agent can and cannot propose. That join is the roadmap: a code that is
   frequent and uncovered is worth more than a code that is rare and covered.

Nothing here runs a check or scores anything. It describes the ground truth so
that the scoring, when it comes, is honest about its own sample.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

#: Extensions that identify a submission's format, most specific first.
SOURCE_KINDS = {
    ".tex": "latex",
    ".docx": "word",
    ".doc": "word",
    ".odt": "word",
}

#: Extensions that are never the paper itself.
_NOT_THE_PAPER = {".pdf", ".png", ".jpg", ".jpeg", ".eps", ".bmp", ".tif", ".tiff",
                  ".gif", ".zip", ".rar", ".tar", ".gz", ".pptx", ".bib", ".cls",
                  ".sty", ".bst", ".txt"}


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


@dataclass
class Side:
    """One side of a pair — the author's revision, or the editors'."""

    role: str
    folder: Path
    files: list[Path] = field(default_factory=list)

    @property
    def present(self) -> bool:
        return bool(self.files)

    def main_file(self) -> Path | None:
        """The paper itself, as opposed to its figures and its built PDF.

        Prefers a source file; a submission that is only a PDF has no source to
        compare and is reported as such rather than silently compared on its
        rendered output.
        """
        candidates = [f for f in self.files if f.suffix.lower() in SOURCE_KINDS]
        if not candidates:
            return None
        # A paper with several .tex files (chapters, or a stray template copy)
        # is resolved by size: the real one is the substantial one.
        return max(candidates, key=lambda f: f.stat().st_size)

    @property
    def kind(self) -> str:
        main = self.main_file()
        return SOURCE_KINDS.get(main.suffix.lower(), "other") if main else "no-source"


@dataclass
class PaperEntry:
    """One paper in the corpus, and what it can be used for."""

    code: str
    contribution_id: int
    friendly_id: int
    title: str
    state: str
    editor: str
    tags: list[str]
    folder: Path
    original: Side | None = None
    current: Side | None = None

    @property
    def kind(self) -> str:
        for side in (self.original, self.current):
            if side and side.kind not in ("no-source", "other"):
                return side.kind
        return (self.original or self.current).kind if (
            self.original or self.current) else "missing"

    @property
    def paired(self) -> bool:
        return bool(self.original and self.original.present
                    and self.current and self.current.present)

    def changed(self) -> bool | None:
        """Did the paper itself change between the two revisions?

        ``None`` when there is nothing to compare. A pair whose main file is
        byte-identical carries no editorial edit, whatever else the revision
        did — and counting it as a usable example would quietly inflate every
        recall figure computed later.
        """
        if not self.paired:
            return None
        before, after = self.original.main_file(), self.current.main_file()
        if not before or not after:
            return None
        if before.stat().st_size != after.stat().st_size:
            return True
        return _digest(before) != _digest(after)

    def usability(self) -> tuple[bool, str]:
        """``(usable, reason)`` — usable meaning "a real edit to learn from"."""
        if not self.original or not self.original.present:
            return False, "nothing submitted"
        if not self.current or not self.current.present:
            return False, "only one revision — never edited"
        if self.original.main_file() is None or self.current.main_file() is None:
            return False, "no source file, only a PDF"
        if self.original.kind != self.current.kind:
            return False, f"format changed: {self.original.kind} to {self.current.kind}"
        changed = self.changed()
        if changed is False:
            return False, "the paper file is unchanged between revisions"
        return True, ""


@dataclass
class Corpus:
    """A pulled conference, described."""

    root: Path
    event_id: int = 0
    papers: list[PaperEntry] = field(default_factory=list)

    @property
    def usable(self) -> list[PaperEntry]:
        return [p for p in self.papers if p.usability()[0]]

    def by_kind(self) -> Counter:
        return Counter(p.kind for p in self.usable)

    def reasons(self) -> Counter:
        return Counter(reason for p in self.papers
                       for usable, reason in [p.usability()] if not usable)

    def tag_counts(self, *, usable_only: bool = False) -> Counter:
        source = self.usable if usable_only else self.papers
        return Counter(code for p in source for code in p.tags)


def load(root: Path) -> Corpus:
    """Read a pulled conference from disk.

    Works on a partial download: a paper listed in ``index.json`` whose files
    have not arrived yet is reported as unpaired rather than crashing the run.
    """
    root = Path(root)
    index_path = root / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(
            f"No index.json in {root}. Run 'indico-pull' first, or point this at "
            "the folder it wrote."
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))

    corpus = Corpus(root=root, event_id=index.get("event_id", 0))
    for record in index.get("papers", []):
        code = record.get("code") or f"c{record.get('friendly_id')}"
        folder = root / code
        entry = PaperEntry(
            code=code,
            contribution_id=record.get("contribution_id", 0),
            friendly_id=record.get("friendly_id", 0),
            title=record.get("title", ""),
            state=record.get("state", ""),
            editor=record.get("editor", ""),
            tags=[t["code"] for t in record.get("tags", [])],
            folder=folder,
        )
        for role in ("original", "current"):
            source_dir = folder / role / "Source_Files"
            if source_dir.is_dir():
                files = sorted(f for f in source_dir.iterdir() if f.is_file())
                side = Side(role=role, folder=source_dir, files=files)
                setattr(entry, role, side)
        corpus.papers.append(entry)
    return corpus


def measurable_sample(corpus: Corpus) -> dict[str, int]:
    """How many pairs each check family could actually be scored on.

    The number that keeps a later precision figure honest. A LaTeX-only check
    has no evidence in a Word submission, so quoting one figure over the whole
    conference would overstate the sample for every check in the tool.
    """
    kinds = corpus.by_kind()
    return {
        "all pairs": len(corpus.usable),
        "LaTeX source checks": kinds.get("latex", 0),
        "Word checks": kinds.get("word", 0),
        "reference and DOI checks": len(corpus.usable),   # both formats carry these
    }


# ---------------------------------------------------------------------------
# Joining what the editors did to what the agent can do
# ---------------------------------------------------------------------------

#: How a tag code relates to the agent's checks.
COVERED = "covered"                 # a check proposes this code today
PARTIAL = "partly covered"          # some of what the code means, not all
BUILDABLE = "buildable"             # deterministic, not implemented yet
NEEDS_PDF = "needs the PDF"         # out of reach without the rendered page
OUT_OF_SCOPE = "out of scope"       # deliberately not ours
JUDGEMENT = "editor's judgement"    # a catch-all or a message, not a check
SERVICE = "the editing service"     # QA gate's own tags


@dataclass
class TagRow:
    """One tag code, how often editors used it, and whether the agent can help."""

    code: str
    title: str
    papers: int
    status: str
    detail: str = ""

    @property
    def priority(self) -> int:
        """Frequent and buildable ranks above frequent and impossible."""
        weight = {BUILDABLE: 0, PARTIAL: 1, COVERED: 2, NEEDS_PDF: 3,
                  OUT_OF_SCOPE: 4, JUDGEMENT: 5, SERVICE: 6}[self.status]
        return weight * 10_000 - self.papers


def tag_report(corpus: Corpus, *, usable_only: bool = False) -> list[TagRow]:
    """The tag histogram, joined with the agent's coverage.

    This is the roadmap the editors wrote without meaning to: a code applied to
    a quarter of the conference that no check proposes is worth more than a
    perfect score on one that appears twice.
    """
    from src.indico_client import tags as vocabulary

    covered_codes = set(vocabulary.CHECK_TO_TAG.values())
    counts = corpus.tag_counts(usable_only=usable_only)

    rows: list[TagRow] = []
    for code, papers in counts.items():
        spec = vocabulary.VOCABULARY.get(code)
        title = spec.title if spec else "(not in this event's vocabulary)"
        gap = vocabulary.OUT_OF_REACH.get(code, "")
        if code in vocabulary.SERVICE_OWNED:
            status, detail = SERVICE, "set by OpenReferee JACoW, never by us"
        elif code in covered_codes:
            checks = sorted(c for c, t in vocabulary.CHECK_TO_TAG.items() if t == code)
            names = ", ".join(checks[:4]) + (
                f" (+{len(checks) - 4})" if len(checks) > 4 else "")
            # A code can be both covered and short: TC08 finds an unresolved
            # citation but not a figure nobody referenced. Saying "covered"
            # there would hide exactly the gap this report exists to show.
            if gap:
                status, detail = PARTIAL, f"{names} — {gap}"
            else:
                status, detail = COVERED, names
        elif code in vocabulary.BUILDABLE_NEXT:
            status, detail = BUILDABLE, vocabulary.OUT_OF_REACH[code].split(":", 1)[-1].strip()
        elif gap:
            if "out of scope" in gap:
                status = OUT_OF_SCOPE
            elif "catch-all" in gap or "editor" in gap or "workflow action" in gap:
                status = JUDGEMENT
            else:
                status = NEEDS_PDF
            detail = gap
        else:
            status, detail = JUDGEMENT, "not in the mapping — a local code"
        rows.append(TagRow(code=code, title=title, papers=papers,
                           status=status, detail=detail))
    return sorted(rows, key=lambda r: r.priority)


def summary(corpus: Corpus) -> str:
    """One line an operator can paste into a message."""
    kinds = corpus.by_kind()
    return (f"{len(corpus.usable)} usable pair(s) of {len(corpus.papers)} "
            f"contribution(s): {kinds.get('latex', 0)} LaTeX, "
            f"{kinds.get('word', 0)} Word")
