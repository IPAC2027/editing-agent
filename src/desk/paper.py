"""Assembling one paper for the review desk, and closing it when done.

This is the layer that turns the agent's machine-readable output into
something an editor can work through in order, and turns their decisions back
into files. Two jobs:

:func:`view` — everything about one paper as a single JSON payload: the
suggestions with plain-English headings, the problems sorted by who has to act
on them, the editor's own notes and hand edits, and the source with line
numbers so they can change something the agent never mentioned.

:func:`compose` / :func:`close_paper` — the text that results from
*accepted automatic edits, then accepted suggestions, then the structural
change, then the editor's hand edits*, in that order, plus a letter back to the
author. Nothing is written until the editor asks for it, and the author's
original files are never touched.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.desk import files, plain, title_check
from src.desk.indico import Conference
from src.desk.state import (
    ManualEdit,
    ReviewState,
    _guess_paper_id,
    bib_id,
    finding_key,
    hold_view,
)
from src.edits import EditConflict, EditSet


class _WordChange:
    """A Word paragraph correction, wearing the same shape as an Edit."""

    def __init__(self, data: dict) -> None:
        self._d = data
        self.id = data.get("id", "")
        self.check_id = data.get("check_id", "FMT-REF-01")
        self.line = data.get("reference")
        self.before = data.get("shown_before") or data.get("before", "")
        self.after = data.get("shown_after") or data.get("after", "")
        self.message = data.get("message", "")
        self.rule = "JACoW Annex B: reference layout"
        self.context_before = ""
        self.context_after = ""

    @property
    def paragraph(self) -> dict:
        return self._d


class DeskError(RuntimeError):
    """Something the editor needs told about in plain words."""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _short(text: str, width: int = 110) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class Paper:
    """Everything on disk about one submission, loaded once."""

    def __init__(self, folder: Path) -> None:
        from src.workflow.prescreen import detect_source_format

        self.folder = folder
        self.out_dir = folder / "aiagent_prescreen"
        self.kind = detect_source_format(folder)
        self.report = _read_json(self.out_dir / "report.json")
        self.structural = _read_json(self.out_dir / "structural.json")
        self.state = ReviewState.load(folder)
        self.editset: EditSet | None = None
        self.word_corrections: list[dict] = _read_json(
            self.out_dir / "word_edits.json"
        ).get("corrections", [])

        editset_path = self.out_dir / "edits.json"
        if editset_path.exists():
            try:
                self.editset = EditSet.read(editset_path)
            except Exception:  # noqa: BLE001
                self.editset = None

        # The .bib file's own edits (biblatex papers), with ids of their own.
        self.bib_editset: EditSet | None = None
        bib_edits_path = self.out_dir / "edits_bib.json"
        if bib_edits_path.exists():
            try:
                self.bib_editset = EditSet.read(bib_edits_path)
                for edit in self.bib_editset.edits:
                    edit.id = bib_id(edit.id)
            except Exception:  # noqa: BLE001
                self.bib_editset = None

        # One record per reference, written when the paper was prepared.
        refs = _read_json(self.out_dir / "references.json")
        self.has_reference_records = "references" in refs
        self.reference_records: list[dict] = refs.get("references", [])
        self.references_file: str = refs.get("file", "")
        self.bib_path = self._find_bib()
        self.bib_source = ""
        if self.bib_path is not None:
            self.bib_source = self.bib_path.read_text(encoding="utf-8", errors="replace")

        self.source_path = self._find_source()
        self.source = ""
        if self.source_path and self.source_path.suffix.lower() == ".tex":
            self.source = self.source_path.read_text(encoding="utf-8", errors="replace")

        if not self.state.paper_id:
            # As the worklist names it, so a pulled paper is not called "original".
            self.state.paper_id = self.report.get("paper_id") or _guess_paper_id(folder)

    @property
    def screened(self) -> bool:
        return bool(self.report)

    @property
    def paper_id(self) -> str:
        return self.state.paper_id or self.report.get("paper_id", self.folder.name)

    def _find_bib(self) -> Path | None:
        """The .bib file the .bib edits and records were made against, if any."""
        if self.kind != "latex" or not (self.bib_editset or any(
                r.get("origin") == "bib" for r in self.reference_records)):
            return None
        from src.workflow.prescreen import _find_bibs

        try:
            bibs = _find_bibs(self.folder)
        except Exception:  # noqa: BLE001
            return None
        wanted = self.bib_editset.file if self.bib_editset else self.references_file
        for bib in bibs:
            if bib.name == wanted:
                return bib
        return bibs[0] if bibs else None

    def _find_source(self) -> Path | None:
        from src.workflow.prescreen import _find_tex

        if self.kind == "latex":
            try:
                return _find_tex(self.folder)
            except FileNotFoundError:
                return None
        if self.kind == "word":
            from src.workflow.word_prescreen import _find_word_doc

            try:
                return _find_word_doc(self.folder)
            except FileNotFoundError:
                return None
        return None

    # -- selections -----------------------------------------------------
    @property
    def auto_edits(self) -> list:
        """Automatic changes, whatever the source format.

        Word corrections are modelled the same way as LaTeX span edits so the
        desk has one notion of "a change" and the editor has one place to
        decide.  They are returned as light objects with the same attribute
        names rather than as real :class:`~src.edits.Edit` instances, because a
        Word revision is a paragraph replacement and has no character span in
        a source file.
        """
        if self.editset:
            return self.editset.auto
        return [_WordChange(c) for c in self.word_corrections
                if c.get("tier") == "auto"]

    @property
    def suggested_edits(self) -> list:
        if self.editset:
            return self.editset.suggested
        return [_WordChange(c) for c in self.word_corrections
                if c.get("tier") != "auto"]

    @property
    def reorder(self):
        reorder = self.structural.get("reorder")
        if not reorder:
            return None
        if reorder.get("desired_order") == reorder.get("current_order"):
            return None
        return reorder

    @property
    def bib_auto(self) -> list:
        return self.bib_editset.auto if self.bib_editset else []

    @property
    def bib_suggested(self) -> list:
        return self.bib_editset.suggested if self.bib_editset else []

    def suggested_ids(self) -> list[str]:
        ids = [edit.id for edit in self.suggested_edits]
        ids += [edit.id for edit in self.bib_suggested]
        if self.reorder:
            ids.append(self.reorder.get("id", "R1"))
        return ids

    def find_edit(self, edit_id: str):
        """An edit (or Word correction) by id, wherever it lives; None if unknown."""
        for edit in [*self.auto_edits, *self.suggested_edits, *self.bib_auto,
                     *self.bib_suggested]:
            if edit.id == edit_id:
                return edit
        return None


# ---------------------------------------------------------------------------
# The view an editor sees
# ---------------------------------------------------------------------------

def view(folder: Path, *, default_editor: str = "") -> dict:
    """One paper, as the desk renders it.

    *default_editor* is the name typed at the top of the desk. It signs the
    drafted letter for a paper the editor has not touched yet, so the draft
    never arrives addressed from "the editorial team" when they have told the
    desk who they are.
    """
    paper = Paper(folder)
    state = paper.state
    if default_editor and not state.editor:
        state.editor = default_editor
    conference = Conference.open(folder.parent.parent)
    held = conference.assignment(folder, me=default_editor) if conference else None
    indico = held.model_dump() if held else None
    title_authors = _title_authors(paper, conference, indico_url=held.url if held else "")

    if not paper.screened:
        return {
            "folder": str(folder),
            "name": folder.name,
            "paper_id": paper.paper_id,
            "kind": paper.kind,
            "screened": False,
            "indico": indico,
            "title_authors": title_authors,
            "message": (
                "This paper has not been prepared yet. Press “Prepare this paper” "
                "and the agent will read it, apply the safe corrections and list "
                "anything that needs you."
            ),
        }

    scopes = _Scopes(paper)
    decisions = [_decision_card(edit, state) for edit in paper.suggested_edits]
    decisions += [_decision_card(edit, state) for edit in paper.bib_suggested]
    if paper.reorder:
        decisions.insert(0, _reorder_card(paper.reorder, state))

    applied = [_applied_card(edit, state) for edit in paper.auto_edits]
    applied += [_applied_card(edit, state) for edit in paper.bib_auto]
    bib_ids = {edit.id for edit in [*paper.bib_auto, *paper.bib_suggested]}
    for card in decisions + applied:
        if card["kind"] == "reorder":
            card["scope"], card["ref"] = "reference", ""
            continue
        edit = paper.find_edit(card["id"])
        card["scope"], card["ref"] = scopes.of_edit(edit, bib=card["id"] in bib_ids)
        if card["id"] in bib_ids:
            card["line_label"] = f"line {edit.line} of {paper.bib_editset.file}"
        card["edited_text"] = state.edit_texts.get(card["id"])

    findings = _finding_cards(
        paper.report.get("findings", []), state,
        covered=_covered_by_corrections(paper),
    )
    for card in findings:
        card["scope"], card["ref"] = scopes.of_finding(card)
    references = _references_view(paper, findings)

    return {
        "folder": str(folder),
        "name": folder.name,
        "paper_id": paper.paper_id,
        "title": plain.readable_title(paper.report.get("title", "")),
        "authors": paper.report.get("authors", []),
        "kind": paper.kind,
        "screened": True,
        "status": state.status,
        "status_word": state.status_word,
        "editor": state.editor,
        "indico": indico,
        "title_authors": title_authors,
        "build": paper.report.get("build", ""),
        "generated_at": paper.report.get("generated_at", ""),
        "paper_note": state.paper_note,
        "counts": {
            "applied": sum(1 for a in applied if a["decision"] == "applied"),
            "reverted": sum(1 for a in applied if a["decision"] == "reverted"),
            "to_decide": sum(1 for d in decisions if d["decision"] == "undecided"),
            "accepted": sum(1 for d in decisions if d["decision"] == "accepted"),
            "rejected": sum(1 for d in decisions if d["decision"] == "rejected"),
            "must_fix": sum(1 for f in findings if f["severity"] == "error"),
            "worth_a_look": sum(1 for f in findings if f["severity"] == "warning"),
            "my_notes": len(state.editor_notes),
            "my_edits": len(state.manual_edits),
        },
        "decisions": decisions,
        "applied": applied,
        "findings": findings,
        "my_notes": [note.model_dump() for note in state.editor_notes],
        "my_edits": [
            {**edit.model_dump(), "summary": edit.summary}
            for edit in state.manual_edits
        ],
        "letter": letter_text(paper),
        "letter_override": state.letter_override,
        "files": _files(paper),
        "source": _source_view(paper),
        "lookups": paper.report.get("lookups", []),
        "references": references,
        "body": _body_view(paper),
        "tags": _tags_view(paper, decisions, applied, findings, references),
        "hold": hold_view(state),
        "pdf": _pdf_view(paper),
        "reprepared": state.reprepared[-1] if state.reprepared else None,
    }


def _title_authors(paper: Paper, conference: Conference | None, *,
                   indico_url: str = "") -> dict | None:
    """The title and author check's panel, for a paper Indico knows."""
    record = conference.record(paper.folder) if conference else None
    return title_check.view(
        front=title_check.front_for(paper.folder, paper.report) if record else None,
        prepared=paper.screened, state=paper.state, record=record,
        paper_id=paper.paper_id, event=paper.folder.parent.parent.name,
        indico_url=indico_url,
    )


def _applied_card(edit, state: ReviewState) -> dict:
    """One correction the agent made without asking — and how to undo it.

    Carries the same fields as a decision card, because an editor looking at
    an automatic correction wants exactly what they want for a suggestion:
    what changed, why, where, and a way to put it back.
    """
    explanation = plain.explain(edit.check_id)
    return {
        "id": edit.id,
        "kind": "applied",
        "check_id": edit.check_id,
        "heading": explanation.label,
        "why": explanation.why,
        "detail": edit.message,
        "rule": edit.rule or "",
        "line": edit.line,
        "line_label": ("reference " + str(edit.line)) if isinstance(edit, _WordChange)
                      else ("line " + str(edit.line) if edit.line else ""),
        "before": edit.before,
        "after": edit.after,
        "context_before": edit.context_before,
        "context_after": edit.context_after,
        "decision": state.auto_decision(edit.id),
        "note": state.edit_notes.get(edit.id, ""),
    }


def _decision_card(edit, state: ReviewState) -> dict:
    explanation = plain.explain(edit.check_id)
    return {
        "id": edit.id,
        "kind": "edit",
        "check_id": edit.check_id,
        "heading": explanation.label,
        "why": explanation.why,
        "detail": edit.message,
        "rule": edit.rule or "",
        "line": edit.line,
        "line_label": ("reference " + str(edit.line)) if isinstance(edit, _WordChange)
                      else ("line " + str(edit.line) if edit.line else ""),
        "before": edit.before,
        "after": edit.after,
        "context_before": edit.context_before,
        "context_after": edit.context_after,
        "decision": state.decision_for(edit.id),
        "note": state.edit_notes.get(edit.id, ""),
        "evidence": (
            f"{plain.EXPLANATIONS.get(edit.check_id, plain._FALLBACK).owner_label}"
            if False else ""
        ),
    }


def _reorder_card(reorder: dict, state: ReviewState) -> dict:
    explanation = plain.explain("REF-NUM-02")
    current = reorder.get("current_order", [])
    desired = reorder.get("desired_order", [])

    def _order(keys: list[str]) -> str:
        shown = "  ".join(f"[{i}] {k}" for i, k in enumerate(keys[:8], start=1))
        return shown + (f"   (+{len(keys) - 8} more)" if len(keys) > 8 else "")

    edit_id = reorder.get("id", "R1")
    return {
        "id": edit_id,
        "kind": "reorder",
        "check_id": "REF-NUM-02",
        "heading": explanation.label,
        "why": explanation.why,
        "detail": reorder.get("message", ""),
        "rule": reorder.get("rule", ""),
        "line": None,
        "before": _order(current),
        "after": _order(desired),
        "context_before": "",
        "context_after": "",
        "decision": state.decision_for(edit_id),
        "note": state.edit_notes.get(edit_id, ""),
        "evidence": "",
    }


def _covered_by_corrections(paper: Paper) -> set[tuple[str, object]]:
    """``(check_id, reference)`` pairs that a Word correction already handles.

    The Word path emits both a finding ("reference 1 was reformatted") and a
    correction the editor decides on. Showing both means the same reference
    appears under *Your decisions* and again under *Problems*, which is the
    double-reporting the LaTeX side already suppresses.
    """
    covered: set[tuple[str, object]] = set()
    for correction in paper.word_corrections:
        # A correction the editor put back no longer handles anything, so the
        # finding it was hiding has to come back with it.
        if (correction.get("tier") == "auto"
                and paper.state.auto_decision(correction.get("id", "")) != "applied"):
            continue
        reference = correction.get("reference")
        for check_id in correction.get("checks") or [correction.get("check_id")]:
            covered.add((check_id, reference))
    return covered


def _finding_cards(
    findings: list[dict],
    state: ReviewState,
    covered: set[tuple[str, object]] | None = None,
) -> list[dict]:
    cards = []
    for finding in findings:
        check_id = finding.get("check_id", "")
        if covered and (check_id, finding.get("line")) in covered:
            continue
        explanation = plain.explain(check_id)
        severity = finding.get("severity", "info")
        owner = plain.owner(check_id, severity)
        key = finding_key(check_id, finding.get("line"), finding.get("original"))
        cards.append({
            "key": key,
            "check_id": check_id,
            "heading": explanation.label,
            "why": explanation.why,
            "detail": finding.get("message", ""),
            "owner": owner,
            "owner_label": plain._OWNER_LABELS.get(owner, owner),
            "severity": severity,
            "severity_word": plain.severity_word(severity),
            "ask": explanation.ask_phrase(),
            "line": finding.get("line"),
            "original": _short(finding.get("original") or "", 240),
            "suggested": _short(finding.get("suggested") or "", 240),
            "handled": bool(state.handled.get(key)),
            "note": state.finding_notes.get(key, ""),
        })
    order = {"error": 0, "warning": 1, "info": 2}
    cards.sort(key=lambda c: (order.get(c["severity"], 3), c["heading"]))
    return cards


def _files(paper: Paper) -> list[dict]:
    """Files worth offering the editor, with plain names."""
    wanted = [
        (f"{paper.paper_id}_edited.pdf", "The corrected paper (PDF)"),
        (f"{paper.paper_id}_final.pdf", "Your reviewed paper (PDF)"),
        (f"{paper.paper_id}_edited.tex", "The corrected source"),
        (f"{paper.paper_id}_final.tex", "Your reviewed source"),
        ("author_letter.txt", "Letter to the author"),
        ("report.md", "Full technical report"),
    ]
    files = []
    for name, label in wanted:
        path = paper.out_dir / name
        if path.exists():
            files.append({"name": name, "label": label,
                          "size": path.stat().st_size})
    for tracked in sorted(paper.out_dir.glob("*_tracked.docx")):
        files.append({"name": tracked.name,
                      "label": "Word file with tracked changes",
                      "size": tracked.stat().st_size})
    for tracked in sorted(paper.out_dir.glob("*_reviewed.docx")):
        files.append({"name": tracked.name,
                      "label": "Your reviewed Word file",
                      "size": tracked.stat().st_size})
    original_pdf = sorted((paper.folder / "PDF").glob("*.pdf")) if (
        paper.folder / "PDF").is_dir() else []
    for pdf in original_pdf[:1]:
        files.append({"name": f"../PDF/{pdf.name}",
                      "label": "The author's original PDF",
                      "size": pdf.stat().st_size})
    return files


def _source_view(paper: Paper) -> dict:
    """The source with line numbers, so the editor can change anything.

    Only LaTeX sources are editable line by line here. A Word submission is
    edited in Word — that is what the tracked-changes file is for — so the desk
    offers its reference list instead.
    """
    if paper.kind != "latex" or not paper.source:
        return {"editable": False, "lines": [], "note": (
            "This is a Word submission, so the text itself is edited in Word. "
            "Decide on the corrections here and press Finish; you will get a Word "
            "file containing only the ones you accepted, as tracked changes. "
            "Anything else you spot goes under “Your notes” and into the letter."
        )}

    working = compose(paper, include_undecided=False)
    touched = {
        edit.line for edit in paper.auto_edits
        if paper.state.auto_decision(edit.id) == "applied"
    } | {
        edit.line for edit in paper.suggested_edits
        if paper.state.decision_for(edit.id) == "accepted"
    }
    manual = {edit.line for edit in paper.state.manual_edits}
    return {
        "editable": True,
        "note": (
            "This is the paper as it stands now, with the corrections you have "
            "accepted already in place. Click any line to change it yourself."
        ),
        "lines": [
            {
                "n": number,
                "text": text,
                "changed": number in touched,
                "mine": number in manual,
            }
            for number, text in enumerate(working.splitlines(), start=1)
        ],
    }


# ---------------------------------------------------------------------------
# Where each change and finding belongs: the title and authors, the reference
# list, or the body of the paper
# ---------------------------------------------------------------------------

_TITLE_CHECKS = frozenset({"FMT-TITLE-02", "FMT-AUTH-01", "WORD-TITLE-01", "WORD-AUTH-02",
                           "WORD-TITLE-03"})
_REFERENCE_PREFIXES = ("REF-", "DOI-", "CITE-", "BIB-", "PROC-REQ-", "FMT-REF-")
_REFERENCE_CHECKS = frozenset({"URL-AS-DOI-01", "TITLE-01", "AUTH-01", "AUTH-02",
                               "JACOW-CLS-02", "JACOW-CLS-03", "FMT-TITLE-03",
                               "WORD-REFSPACE-01"})
_LABEL = re.compile(r"^Reference (\{[^}]*\}|\[\d+\])")


class _Scopes:
    """Sorts changes and findings into the desk's tabs."""

    def __init__(self, paper: Paper) -> None:
        self.paper = paper
        records = paper.reference_records
        self.ids = {ref_id(r) for r in records}
        self.by_edit = {eid: ref_id(r) for r in records for eid in r.get("edit_ids") or []}
        self.spans = [(r["start"], r["end"], ref_id(r)) for r in records
                      if r.get("origin") == "bibitem" and r.get("start") is not None]
        self.lines = [(r.get("line") or 0, r.get("end_line") or r.get("line") or 0, ref_id(r))
                      for r in records if r.get("origin") == "bibitem"]
        block = (re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
                           paper.source, re.DOTALL) if paper.source else None)
        self.block = block.span() if block else None

    def _by_key(self, key: str) -> str:
        for origin in ("bibitem", "bib", "word"):
            if f"{origin}:{key}" in self.ids:
                return f"{origin}:{key}"
        return ""

    def of_edit(self, edit, *, bib: bool = False) -> tuple[str, str]:
        if edit is None:
            return "body", ""
        if bib:
            return "reference", self.by_edit.get(edit.id, "")
        if isinstance(edit, _WordChange):
            number = edit.paragraph.get("reference")
            if number is not None:
                return "reference", (f"word:{number}" if f"word:{number}" in self.ids else "")
            return ("title" if edit.check_id in _TITLE_CHECKS else "body"), ""
        ref = self.by_edit.get(edit.id) or next(
            (rid for a, b, rid in self.spans if a <= edit.start and edit.end <= b), "")
        if ref:
            return "reference", ref
        if self.block and self.block[0] <= edit.start < self.block[1]:
            return "reference", ""
        return ("title" if edit.check_id in _TITLE_CHECKS else "body"), ""

    def of_finding(self, card: dict) -> tuple[str, str]:
        check_id = card.get("check_id", "")
        match = _LABEL.match(card.get("detail") or "")
        ref = self._by_key(match.group(1)[1:-1]) if match else ""
        line = card.get("line")
        if not ref and isinstance(line, int) and self.paper.kind == "latex":
            ref = next((rid for a, b, rid in self.lines if a <= line <= b), "")
        if ref:
            return "reference", ref
        if check_id in _TITLE_CHECKS:
            return "title", ""
        if check_id.startswith(_REFERENCE_PREFIXES) or check_id in _REFERENCE_CHECKS:
            return "reference", ""
        return "body", ""


# ---------------------------------------------------------------------------
# The References tab: each reference as written, beside what it becomes
# ---------------------------------------------------------------------------

#: Findings that ask for a DOI: answered when the rewrite carries one.
_DOI_WANTED = frozenset({"URL-AS-DOI-01", "DOI-REQ-01", "DOI-MISSING-01",
                         "DOI-FMT-02", "DOI-FMT-01", "DOI-FMT-03"})

#: Problems the desk cannot fix by itself: the reference is shown red.
_BLOCKING = frozenset({"REF-KIND", "REF-DOI-WRONG", "REF-MISSING", "FMT-REF-03",
                       "REF-INT-01", "REF-INT-02", "WORD-TRACK-01"})


def _is_auto(edit) -> bool:
    if isinstance(edit, _WordChange):
        return edit.paragraph.get("tier") == "auto"
    return getattr(edit, "tier", None) is not None and edit.tier.value == "auto"


def _ref_with(text: str, record: dict, edits: list, keep) -> str:
    """The reference with the edits *keep* chooses applied, as the author's layout has it."""
    start, end = record["start"], record["end"]
    body = text[start:end]
    for edit in sorted((e for e in edits if keep(e)), key=lambda e: e.start, reverse=True):
        if start <= edit.start and edit.end <= end:
            body = body[:edit.start - start] + edit.after + body[edit.end - start:]
    return body.strip()


def _references_view(paper: Paper, findings: list[dict]) -> dict:
    """One row per reference: the source, the result, and how sure the desk is.

    ``status`` is ``fixed`` (rewritten, nothing missing: green), ``problem``
    (something the desk cannot put right by itself: red) or ``ok`` (already in
    Appendix B's layout, or nothing to change).
    """
    state = paper.state
    by_ref: dict[str, list[dict]] = {}
    for card in findings:
        if card.get("ref"):
            by_ref.setdefault(card["ref"], []).append(card)
    rows = []
    for record in paper.reference_records:
        rid = ref_id(record)
        origin = record.get("origin", "")
        # Every edit inside the reference: the whole rewrite, or (when there is
        # none) the narrow fixes, decided together as one.
        edits = [e for e in (paper.find_edit(i) for i in (record.get("edit_ids") or [])) if e]
        whole = paper.find_edit(record.get("edit_id") or "") if record.get("edit_id") else None
        if whole is not None:
            edits = [whole]
        edit = edits[0] if edits else None
        auto_ids = [e.id for e in edits if _is_auto(e)]
        suggest_ids = [e.id for e in edits if not _is_auto(e)]
        auto = bool(edits) and not suggest_ids
        decision = ""
        if auto:
            decision = ("reverted" if all(state.auto_decision(i) == "reverted" for i in auto_ids)
                        else "applied")
        elif suggest_ids:
            said = {state.decision_for(i) for i in suggest_ids}
            decision = said.pop() if len(said) == 1 else "undecided"
        proposed, standing = "", ""
        if whole is not None:
            proposed = whole.after.strip() if origin == "bibitem" else whole.after
        elif edits and record.get("start") is not None:
            text = paper.bib_source if origin == "bib" else paper.source
            proposed = _ref_with(text, record, edits, lambda e: True)
            standing = _ref_with(text, record, edits, lambda e: (
                state.auto_decision(e.id) == "applied" if _is_auto(e)
                else state.decision_for(e.id) == "accepted"))
        problems = list(record.get("problems") or [])
        seen = {(p["code"], p["message"]) for p in problems}
        has_doi = bool(re.search(r"\\doi\{|\bdoi\s*[:=]|doi\.org/", proposed or ""))
        for card in by_ref.get(rid, []):
            if has_doi and card["check_id"] in _DOI_WANTED:
                continue        # the rewrite gives the DOI this finding asked for
            message = _LABEL.sub("", card.get("detail") or "").lstrip(": ").strip()
            if (card["check_id"], message) in seen:
                continue
            seen.add((card["check_id"], message))
            problems.append({"code": card["check_id"], "message": message or card["why"],
                             "field": "", "severity": card["severity"], "key": card["key"],
                             "handled": card["handled"]})
        blocking = [p for p in problems
                    if p["code"] in _BLOCKING or p.get("severity") == "error"]
        status = ("problem" if record.get("missing") or blocking
                  else "fixed" if edit is not None else "ok")
        own = state.ref_texts.get(rid)
        if own is not None:
            current = own
        elif standing:
            current = standing
        elif decision in ("accepted", "applied") and proposed:
            current = state.edit_texts.get(edit.id, proposed) if edit is not None else proposed
        else:
            current = record.get("source", "")
        rows.append({
            "id": rid, "n": record.get("n"), "key": record.get("key", ""), "origin": origin,
            "kind": record.get("kind", ""), "category": record.get("category", ""),
            "source": record.get("source", ""), "proposed": proposed,
            "text": record.get("text", ""), "status": status,
            "edit_id": edit.id if edit is not None else "", "auto": auto,
            "suggest_ids": suggest_ids, "auto_ids": auto_ids,
            "decision": decision, "own": own, "current": current,
            "missing": record.get("missing") or [], "dropped": record.get("dropped", ""),
            "changes": record.get("changes") or [], "sources": record.get("sources") or [],
            "parsed_by": record.get("parsed_by", ""),
            "problems": [p for p in problems if p.get("severity") != "info"],
            "info": [p for p in problems if p.get("severity") == "info"],
            "line": record.get("line"),
        })
    reorder = paper.reorder
    return {
        "recorded": paper.has_reference_records,
        "file": paper.references_file,
        "origin": rows[0]["origin"] if rows else "",
        "rows": rows,
        "counts": {
            "fixed": sum(1 for r in rows if r["status"] == "fixed"),
            "problem": sum(1 for r in rows if r["status"] == "problem"),
            "ok": sum(1 for r in rows if r["status"] == "ok"),
            "undecided": sum(1 for r in rows if r["suggest_ids"]
                             and r["decision"] == "undecided" and r["own"] is None),
        },
        "reorder": _reorder_card(reorder, state) if reorder else None,
        "list_findings": [card for card in findings
                          if card.get("scope") == "reference" and not card.get("ref")],
    }


# ---------------------------------------------------------------------------
# The paper tab: the source as it stands, with each suggestion in place
# ---------------------------------------------------------------------------

def _body_view(paper: Paper) -> dict:
    """The LaTeX source line by line, every change shown where it is.

    Each line is a list of pieces: plain text, or part of an edit with its state
    (``applied``/``reverted`` for automatic corrections, ``accepted``/
    ``rejected``/``undecided`` for suggestions). A line's ``text`` is what it
    says now (undecided suggestions not applied), which is what a hand edit of
    the line replaces. Hand edits are shown on top, as :func:`compose` applies
    them. Line numbers are those of the text as it stands.
    """
    if paper.kind != "latex" or not paper.source:
        return {"editable": False, "lines": []}
    source, state = paper.source, paper.state
    scopes = _Scopes(paper)

    overridden = []
    for record in paper.reference_records:
        text = state.ref_texts.get(ref_id(record))
        if record.get("origin") == "bibitem" and text is not None and record.get("start") is not None:
            overridden.append((record["start"], record["end"], ref_id(record), text))

    events = []
    for edit in (paper.editset.edits if paper.editset else []):
        if any(a <= edit.start and edit.end <= b for a, b, _r, _t in overridden):
            continue
        auto = edit.tier.value == "auto"
        decision = state.auto_decision(edit.id) if auto else state.decision_for(edit.id)
        after = state.edit_texts.get(edit.id, edit.after)
        stands = decision in ("applied", "accepted")
        scope, ref = scopes.of_edit(edit)
        events.append((edit.start, edit.end, {
            "id": edit.id, "state": decision, "auto": auto, "scope": scope, "ref": ref,
            "before": edit.before, "after": after,
        }, after if stands else edit.before))
    for start, end, rid, text in overridden:
        before = source[start:end]
        lead = before[: len(before) - len(before.lstrip())]
        trail = before[len(before.rstrip()):]
        events.append((start, end, {"id": "", "state": "own", "auto": False,
                                    "scope": "reference", "ref": rid, "before": before,
                                    "after": text}, lead + text.strip() + trail))
    events.sort(key=lambda ev: ev[0])

    lines: list[dict] = []
    current = {"segs": [], "orig": 1}

    def new_line(orig: int) -> None:
        nonlocal current
        lines.append(current)
        current = {"segs": [], "orig": orig}

    def put_text(start: int, end: int) -> None:
        position = start
        while position < end:
            newline = source.find("\n", position, end)
            stop = end if newline < 0 else newline
            if stop > position:
                current["segs"].append({"t": source[position:stop]})
            if newline < 0:
                break
            new_line(source.count("\n", 0, newline + 1) + 1)
            position = newline + 1

    position = 0
    for start, end, meta, shown in events:
        if start < position:
            continue
        put_text(position, start)
        pieces = shown.split("\n")
        orig = source.count("\n", 0, start) + 1
        for index, piece in enumerate(pieces):
            if index:
                new_line(orig)
            seg = {"t": piece, **{k: v for k, v in meta.items() if k not in ("before", "after")}}
            if index == 0:
                seg["first"] = True
            if index == len(pieces) - 1:
                seg["last"] = True
                if meta["state"] == "undecided" or meta["state"] == "rejected" or (
                        meta["state"] == "reverted"):
                    seg["proposed"] = meta["after"]
                else:
                    seg["was"] = meta["before"]
            current["segs"].append(seg)
        position = end
    put_text(position, len(source))
    lines.append(current)
    if source.endswith("\n") and not lines[-1]["segs"]:
        lines.pop()

    for number, line in enumerate(lines, start=1):
        line["n"] = number
        line["text"] = "".join(seg["t"] for seg in line["segs"]).rstrip("\r")
        line["mine"] = ""

    texts = [line["text"] for line in lines]
    for manual in state.manual_edits:
        index = manual.line - 1
        if not (0 <= index < len(texts) and texts[index] == manual.before):
            index = next((i for i, t in enumerate(texts) if t == manual.before), -1)
        if index < 0:
            continue
        texts[index] = manual.after
        lines[index].update(text=manual.after, mine=manual.id,
                            was=manual.before, segs=[{"t": manual.after}])
    finding_lines: dict[int, list[str]] = {}
    for finding in paper.report.get("findings", []):
        if isinstance(finding.get("line"), int):
            finding_lines.setdefault(finding["line"], []).append(
                finding_key(finding.get("check_id", ""), finding.get("line"),
                            finding.get("original")))
    for line in lines:
        keys = finding_lines.pop(line["orig"], None)
        if keys:
            line["findings"] = keys

    jumps = []
    for label, pattern in (("Title", r"\\title\s*[\[{]"), ("Authors", r"\\author\s*[\[{]"),
                           ("Abstract", r"\\begin\s*\{abstract\}"),
                           ("Body", r"\\maketitle"),
                           ("References", r"\\begin\s*\{thebibliography\}|\\printbibliography")):
        hit = next((line["n"] for line in lines if re.search(pattern, line["text"])), None)
        if hit:
            jumps.append({"label": label, "line": hit})
    sections = [{"label": plain.readable_title(m.group(2)) or m.group(1), "line": line["n"]}
                for line in lines
                for m in [re.search(r"\\(section|subsection)\*?\s*\{(.*)\}", line["text"])] if m]
    return {"editable": True, "file": paper.source_path.name if paper.source_path else "",
            "lines": lines, "jumps": jumps, "sections": sections[:60]}


# ---------------------------------------------------------------------------
# The editor's panel: JACoW's editorial tags
# ---------------------------------------------------------------------------

def _tags_view(paper: Paper, decisions: list, applied: list, findings: list,
               references: dict) -> dict:
    """The JACoW tags this paper should carry, proposed from what was corrected.

    Only a tag the evidence really is (:data:`src.indico_client.tags.CHECK_TO_TAG`);
    the editor ticks or unticks any of them, and may tick any other code. The
    desk does not write tags to Indico: the editor copies them across.
    """
    from src.indico_client.tags import CHECK_TO_TAG, FAMILIES, SERVICE_OWNED, VOCABULARY

    state = paper.state
    reasons: dict[str, list[str]] = {}

    def add(code: str | None, why: str) -> None:
        if code and code in VOCABULARY and code not in SERVICE_OWNED:
            if why not in reasons.setdefault(code, []):
                reasons[code].append(why)

    for card in applied:
        if card["decision"] == "applied":
            add(CHECK_TO_TAG.get(card["check_id"]), card["heading"])
    for card in decisions:
        if card["decision"] == "accepted":
            add(CHECK_TO_TAG.get(card["check_id"]), card["heading"])
    for row in references["rows"]:
        changed = row["own"] is not None or row["decision"] in ("accepted", "applied")
        if not changed:
            continue
        add("FC03" if row["origin"] == "bib" else "TC06",
            "reference entries corrected" if row["origin"] == "bib" else "references reformatted")
        if row["sources"]:
            add("TC14", "reference details added from " + ", ".join(row["sources"][:2]))
    for card in findings:
        if card["owner"] == plain.AUTHOR and card["severity"] in ("error", "warning") \
                and not card["handled"]:
            add(CHECK_TO_TAG.get(card["check_id"]), card["heading"])
    ta = state.title_authors
    if ta.applied_at:
        add("TC01", "title or author list corrected against Indico")
    if any(note.for_author and not note.resolved for note in state.editor_notes):
        add("MP04", "your notes to the author")
    order = list(VOCABULARY)
    chosen = {code for code in reasons if state.tags.get(code, True)}
    chosen |= {code for code, on in state.tags.items() if on and code in VOCABULARY}
    return {
        "families": FAMILIES,
        "vocabulary": [{"code": t.code, "title": t.title, "colour": t.colour,
                        "family": t.family} for t in VOCABULARY.values()
                       if t.code not in SERVICE_OWNED],
        "proposed": reasons,
        "chosen": sorted(chosen, key=order.index),
        "explicit": dict(state.tags),
    }


# ---------------------------------------------------------------------------
# The PDF beside the source
# ---------------------------------------------------------------------------

def preview_name(paper: Paper) -> str:
    return f"{paper.paper_id}_preview.pdf"


def _pdf_view(paper: Paper) -> dict:
    """PDFs the paper tab can show, newest version of the paper first."""
    choices = []
    for name, label in ((preview_name(paper), "Your version, as it stands"),
                        (f"{paper.paper_id}_final.pdf", "Your reviewed paper"),
                        (f"{paper.paper_id}_edited.pdf", "With the automatic corrections")):
        path = paper.out_dir / name
        if path.exists():
            choices.append({"name": name, "label": label,
                            "at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ")})
    pdf_dir = paper.folder / "PDF"
    for pdf in (sorted(pdf_dir.glob("*.pdf"))[:1] if pdf_dir.is_dir() else []):
        choices.append({"name": f"../PDF/{pdf.name}", "label": "As the author submitted it",
                        "at": ""})
    return {"choices": choices, "can_compile": paper.kind == "latex" and bool(paper.source)}


# ---------------------------------------------------------------------------
# Composing the reviewed text
# ---------------------------------------------------------------------------

def compose(paper: Paper, *, include_undecided: bool = False) -> str:
    """The paper as it stands: automatic + accepted + structural + hand edits.

    Applied in that order, because each stage is expressed against the output
    of the previous one. ``include_undecided`` previews the suggestions the
    editor has not answered yet; the files written on close never do.
    """
    if paper.kind != "latex" or not paper.source:
        return ""

    text = paper.source
    spans = _chosen_spans(paper, paper.auto_edits, paper.suggested_edits,
                          include_undecided=include_undecided) if paper.editset else []
    spans = _with_ref_texts(paper, paper.source, spans, origin="bibitem")
    if spans:
        text = _apply_spans(paper.source, spans)

    reorder = paper.reorder
    if reorder:
        decision = paper.state.decision_for(reorder.get("id", "R1"))
        if decision == "accepted" or (include_undecided and decision == "undecided"):
            from src.autofix.structural import ReorderPlan, StructuralConflict, apply_reorder

            try:
                text = apply_reorder(text, ReorderPlan.model_validate(reorder))
            except StructuralConflict:
                pass  # reported by the checks; not worth blocking the view

    for edit in paper.state.manual_edits:
        text = _apply_manual(text, edit)
    return title_check.add_authors_latex(text, title_check.additions(paper.state))


CONFLICT = ("The author's file has changed since this paper was prepared, so the "
            "corrections no longer line up. Press “Prepare this paper” again — your "
            "decisions and notes are kept.")


def ref_id(record: dict) -> str:
    """A reference's id on the desk: ``bibitem:key``, ``word:3`` or ``bib:key``."""
    return f"{record.get('origin', '')}:{record.get('key', '')}"


def _chosen_spans(paper: Paper, auto: list, suggested: list, *,
                  include_undecided: bool = False) -> list[tuple[int, int, str, str]]:
    """``(start, end, before, after)`` for every edit that stands, in the editor's wording."""
    state = paper.state
    spans = [(e.start, e.end, e.before, e.after) for e in auto
             if state.auto_decision(e.id) == "applied"]
    for edit in suggested:
        decision = state.decision_for(edit.id)
        if decision == "accepted" or (include_undecided and decision == "undecided"):
            spans.append((edit.start, edit.end, edit.before,
                          state.edit_texts.get(edit.id, edit.after)))
    return spans


def _with_ref_texts(paper: Paper, source: str, spans: list, *, origin: str) -> list:
    """*spans* with each reference the editor rewrote replaced by their text.

    The editor's text replaces the whole reference, so any edit inside it gives way.
    The reference's own leading and trailing white space (a \\bibitem body's line
    break and indent) is kept.
    """
    for record in paper.reference_records:
        text = paper.state.ref_texts.get(ref_id(record))
        if record.get("origin") != origin or text is None or record.get("start") is None:
            continue
        start, end = record["start"], record["end"]
        before = source[start:end]
        lead = before[: len(before) - len(before.lstrip())]
        trail = before[len(before.rstrip()):]
        spans = [sp for sp in spans if sp[1] <= start or sp[0] >= end]
        spans.append((start, end, before, lead + text.strip() + trail))
    return spans


def _apply_spans(source: str, spans: list) -> str:
    for start, end, before, _after in spans:
        if source[start:end] != before:
            raise DeskError(CONFLICT)
    text = source
    for start, end, _before, after in sorted(spans, key=lambda sp: sp[0], reverse=True):
        text = text[:start] + after + text[end:]
    return text


def compose_bib(paper: Paper) -> str:
    """The .bib as it stands: automatic + accepted edits + the editor's own entries.

    Empty when the paper has no .bib edits or records.
    """
    if not paper.bib_source:
        return ""
    spans = _chosen_spans(paper, paper.bib_auto, paper.bib_suggested)
    spans = _with_ref_texts(paper, paper.bib_source, spans, origin="bib")
    return _apply_spans(paper.bib_source, spans) if spans else paper.bib_source


def _apply_manual(text: str, edit: ManualEdit) -> str:
    """Replace the editor's line, locating it by content then by number."""
    lines = text.splitlines(keepends=True)
    index = edit.line - 1
    ending = ""

    def _split(line: str) -> tuple[str, str]:
        stripped = line.rstrip("\r\n")
        return stripped, line[len(stripped):]

    if 0 <= index < len(lines):
        body, ending = _split(lines[index])
        if body == edit.before:
            lines[index] = edit.after + (ending or "\n")
            return "".join(lines)

    for position, line in enumerate(lines):
        body, ending = _split(line)
        if body == edit.before:
            lines[position] = edit.after + (ending or "\n")
            return "".join(lines)
    return text  # the line is gone; the edit is kept in the record, not applied


def stale_manual_edits(paper: Paper) -> list[str]:
    """Ids of hand edits whose line can no longer be found."""
    text = compose(paper, include_undecided=False)
    missing = []
    for edit in paper.state.manual_edits:
        if edit.before not in text and edit.after not in text:
            missing.append(edit.id)
    return missing


# ---------------------------------------------------------------------------
# The letter back to the author
# ---------------------------------------------------------------------------

def letter_text(paper: Paper) -> str:
    """Compose a letter the editor can send, from the decisions and notes.

    Pre-screening usually ends in a note back to the author, so the desk writes
    the first draft. Two rules keep it sendable without editing:

    * it uses the author-facing phrasing from :mod:`src.desk.plain`, never the
      raw check message — "Please include the missing image file" rather than
      "\\includegraphics{f}: image file not found in the submission";
    * only errors and warnings reach it. An informational note is for the
      record, and putting one in front of an author asks them to act on
      something that does not need acting on.
    """
    state = paper.state
    lines: list[str] = ["Dear author,", ""]

    title = plain.readable_title(paper.report.get("title") or "")
    opening = f"Thank you for your submission {paper.paper_id}"
    if title and title != paper.paper_id:
        opening += f", \u201c{' '.join(title.split())}\u201d"
    lines.append(opening + ". It has been pre-screened for the proceedings.")
    lines.append("")

    # What was corrected for them, phrased as things rather than check names.
    corrected: list[str] = []
    seen: set[str] = set()

    def _note_fixed(check_id: str) -> None:
        phrase = plain.explain(check_id).fixed_phrase()
        if phrase and phrase not in seen:
            seen.add(phrase)
            corrected.append(phrase)

    for edit in paper.auto_edits:
        if state.auto_decision(edit.id) == "applied":
            _note_fixed(edit.check_id)
    for edit in paper.suggested_edits:
        if state.decision_for(edit.id) == "accepted":
            _note_fixed(edit.check_id)
    if paper.reorder and state.decision_for(paper.reorder.get("id", "R1")) == "accepted":
        _note_fixed("REF-NUM-02")
    ta = state.title_authors
    if ta.applied_at:
        sent = (ta.sent_at or "")[:10]
        if ta.plan.get("title"):
            # Indico is changed by hand: claim it only once the editor has ticked it off.
            done = ta.indico_done.get("title")
            corrected.append("the title in Indico, which "
                             + ("now matches" if done else "is being changed to match")
                             + " your paper's" + (f", as we wrote on {sent}" if sent else ""))
        if ta.plan.get("add_to_paper") or ta.plan.get("add_to_indico"):
            corrected.append("the author list, which is now the combined list from your "
                             "paper and Indico" + (f", as we wrote on {sent}" if sent else ""))

    if corrected:
        lines.append(
            "The following have been corrected for you, so there is nothing for "
            "you to do about them:"
        )
        lines.append("")
        for item in corrected:
            lines.append(f"  - {item}")
        lines.append("")

    # What only they can fix.
    author_items: list[str] = []
    for finding in paper.report.get("findings", []):
        check_id = finding.get("check_id", "")
        severity = finding.get("severity", "info")
        if plain.owner(check_id, severity) != plain.AUTHOR:
            continue
        if severity == "info":
            continue
        key = finding_key(check_id, finding.get("line"), finding.get("original"))
        if state.handled.get(key):
            continue

        explanation = plain.explain(check_id)
        item = f"  - {explanation.ask_phrase()}"
        where = []
        if finding.get("line"):
            where.append(f"line {finding['line']}")
        if finding.get("original"):
            where.append(_short(finding["original"], 90))
        if where:
            item += f"\n      ({'; '.join(where)})"
        note = state.finding_notes.get(key, "")
        if note:
            item += f"\n      Editor's note: {note}"
        author_items.append(item)

    for note in state.editor_notes:
        if not note.for_author or note.resolved:
            continue
        where = f" ({note.where})" if note.where else ""
        author_items.append(f"  - {note.text}{where}")

    if author_items:
        lines.append("Please attend to the following and resubmit:")
        lines.append("")
        lines.extend(author_items)
        lines.append("")
    else:
        lines.append("Nothing further is needed from you. Thank you.")
        lines.append("")

    if state.paper_note:
        lines.append(state.paper_note)
        lines.append("")

    lines.append("With thanks,")
    lines.append(state.editor or "The editorial team")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Closing a paper
# ---------------------------------------------------------------------------

def close_paper(folder: Path, *, status: str = "done", compile_pdf: bool = True) -> dict:
    """Write the reviewed files and mark the paper finished.

    The author's own files are never modified. Everything lands in
    ``aiagent_prescreen/`` next to them.
    """
    paper = Paper(folder)
    if not paper.screened:
        raise DeskError("This paper has not been prepared yet.")

    state = paper.state
    written: list[str] = []

    if paper.kind == "latex" and paper.source:
        final = compose(paper, include_undecided=False)
        final_path = paper.out_dir / f"{paper.paper_id}_final.tex"
        files.write_text(final_path, final)
        written.append(final_path.name)

        replace = {}
        bib_text = compose_bib(paper)
        if bib_text and paper.bib_path is not None:
            bib_final = paper.out_dir / f"{paper.bib_path.stem}_final.bib"
            files.write_text(bib_final, bib_text)
            written.append(bib_final.name)
            replace[paper.bib_path.name] = bib_text

        if compile_pdf:
            result = build_pdf(paper, final, f"{paper.paper_id}_final", replace)
            if result is not None and result.success and result.pdf_path \
                    and result.pdf_path.exists():
                written.append(result.pdf_path.name)

    if paper.kind == "word":
        written += _write_reviewed_docx(paper)

    letter = state.letter_override.strip() or letter_text(paper)
    letter_path = paper.out_dir / "author_letter.txt"
    files.write_text(letter_path, letter + "\n")
    written.append(letter_path.name)

    # Set the outcome before writing the summary, so the summary records the
    # state the paper is actually leaving in rather than the one it arrived in.
    state.status = status
    state.closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.save(folder)

    summary_path = paper.out_dir / "review_summary.md"
    try:
        tags = view(folder).get("tags", {}).get("chosen", [])
    except Exception:  # noqa: BLE001 — the summary is a record, not a gate
        tags = []
    files.write_text(summary_path, _summary_markdown(paper, letter, tags))
    written.append(summary_path.name)

    return {"written": written, "status": state.status,
            "status_word": state.status_word}


def uses_biblatex(text: str) -> bool:
    return bool(re.search(r"\\addbibresource|\\printbibliography|biblatex", text))


def build_pdf(paper: Paper, text: str, stem: str, replace: dict[str, str] | None = None):
    """Compile *text* (the paper as it stands) to ``<stem>.pdf`` beside the report.

    Returns the build result, or None when there is no LaTeX on this computer. A
    failed build never stops the editor: the result says what went wrong.
    """
    from src.latex_build import compile_tex

    tex_path = paper.out_dir / f"{stem}.tex"
    if not tex_path.exists() or tex_path.read_text(encoding="utf-8", errors="replace") != text:
        files.write_text(tex_path, text)
    if replace is None:
        bib_text = compose_bib(paper)
        replace = {paper.bib_path.name: bib_text} if bib_text and paper.bib_path else {}
    try:
        return compile_tex(paper.folder, tex_path, stem, paper.out_dir,
                           use_biblatex=uses_biblatex(text), pdf_name=f"{stem}.pdf",
                           replace_files=replace)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 — a failed proof build must not block the editor
        return None


def _write_reviewed_docx(paper: Paper) -> list[str]:
    """A Word file carrying only the corrections the editor accepted.

    The file the agent produced when preparing the paper contains every
    correction it proposed.  This one is rebuilt from the author's original
    document with the automatic corrections plus the suggestions the editor
    accepted — so the author never sees a change the editor rejected, and the
    ones they do see are still tracked changes they can accept or reject
    themselves.
    """
    if not paper.source_path or not paper.source_path.exists():
        return []
    # References the editor rewrote themselves: their text replaces the reference,
    # whatever was suggested for it.
    own = []
    for record in paper.reference_records:
        text = paper.state.ref_texts.get(ref_id(record))
        if record.get("origin") == "word" and text is not None:
            own.append((record, text))
    own_numbers = {record.get("n") for record, _text in own}
    accepted = [
        c for c in paper.word_corrections
        if ((c.get("tier") == "auto"
             and paper.state.auto_decision(c.get("id", "")) == "applied")
            or paper.state.decision_for(c.get("id", "")) == "accepted")
        and not (c.get("reference") is not None and c.get("reference") in own_numbers)
    ]
    target = paper.out_dir / f"{paper.source_path.stem}_reviewed.docx"
    added = title_check.word_author_addition(paper.source_path,
                                             title_check.additions(paper.state))
    if not accepted and not added and not own:
        # Nothing to change: hand over a clean copy so there is always one
        # file that is "the reviewed document".
        shutil.copy2(paper.source_path, target)
        return [target.name]

    from src.output.docx_tracked import ParagraphRewrite, write_tracked_docx

    rewrites = []
    # Main-text fixes are spans on a paragraph: every accepted span in one
    # paragraph goes into a single rewrite of it.
    spans_by_paragraph: dict[int, tuple[str, list[dict], list[str]]] = {}
    for c in accepted:
        if c.get("spans") and c.get("paragraph_index", -1) >= 0:
            before, spans, checks = spans_by_paragraph.setdefault(
                c["paragraph_index"], (c["before"], [], []))
            spans.extend(c["spans"])
            checks.extend(c.get("checks") or [c["check_id"]])
    for index, (before, spans, checks) in sorted(spans_by_paragraph.items()):
        after = before
        for span in sorted(spans, key=lambda x: x["start"], reverse=True):
            after = after[:span["start"]] + span["after"] + after[span["end"]:]
        if after != before:
            rewrites.append(ParagraphRewrite(
                paragraph_index=index, before=before, after=after,
                author=f"JACoW prescreen ({', '.join(sorted(set(checks)))})"))
    for c in accepted:
        if c.get("paragraph_index", -1) < 0 or c.get("spans") or c.get("format"):
            continue
        author = f"JACoW prescreen ({', '.join(c.get('checks') or [c['check_id']])})"
        if c["after"] != c["before"]:
            rewrites.append(ParagraphRewrite(paragraph_index=c["paragraph_index"],
                                             before=c["before"], after=c["after"],
                                             author=author))
        # A reference whose link is on its own line is one correction made
        # of two paragraph rewrites; both are accepted or rejected together.
        for extra in c.get("more") or []:
            rewrites.append(ParagraphRewrite(paragraph_index=extra["paragraph_index"],
                                             before=extra["before"], after=extra["after"],
                                             author=author))
    if own:
        from src.workflow.word_prescreen import _rebuild_paragraph

        for record, text in own:
            index = record.get("paragraph_index", -1)
            before = record.get("paragraph_text") or ""
            if index is None or index < 0 or not before or record.get("paragraph_count", 1) != 1:
                continue        # not one paragraph: listed in the summary, done by hand
            after = _rebuild_paragraph(before, record.get("source", ""), text)
            if after and after != before:
                rewrites.append(ParagraphRewrite(
                    paragraph_index=index, before=before, after=after,
                    author="JACoW prescreen (editor's reference)"))
    if added:
        index, before, after = added
        same = next((r for r in rewrites if r.paragraph_index == index), None)
        if same is not None:
            same.after += after[len(before):]
        else:
            rewrites.append(ParagraphRewrite(
                paragraph_index=index, before=before, after=after,
                author="JACoW prescreen (title and author check)"))
    formats = [(c["paragraph_index"], c["format"],
                f"JACoW prescreen ({', '.join(c.get('checks') or [c['check_id']])})")
               for c in accepted if c.get("format") and c.get("paragraph_index", -1) >= 0]
    try:
        _path, _revisions, _skipped = write_tracked_docx(
            paper.source_path, target, rewrites, formats,
        )
    except Exception as exc:  # noqa: BLE001
        raise DeskError(
            "The reviewed Word file could not be written "
            f"({type(exc).__name__}). Your decisions are saved; the tracked "
            "changes file from preparation is still there."
        ) from exc
    return [target.name]


def _summary_markdown(paper: Paper, letter: str, tags: list[str] | None = None) -> str:
    state = paper.state
    lines = [
        f"# Review summary — {paper.paper_id}",
        "",
        f"Editor: {state.editor or '(not named)'}",
        f"Status: {state.status_word}",
        f"Closed: {state.closed_at or '(open)'}",
    ]
    names = _title_authors(paper, Conference.open(paper.folder.parent.parent))
    if names:
        lines.append(f"Author/title check: {names['status_word']}")
        for task in names.get("indico_tasks", []):
            lines.append(f"  - [{'x' if task['done'] else ' '}] {task['text']}")
    lines += [
        "",
        "## Corrections applied automatically",
        "",
    ]
    reverted = []
    for edit in paper.auto_edits:
        entry = (f"- line {edit.line}: {plain.label(edit.check_id)} — "
                 f"`{_short(edit.before, 60)}` → `{_short(edit.after, 60)}`")
        note = state.edit_notes.get(edit.id, "")
        if state.auto_decision(edit.id) == "applied":
            lines.append(entry)
        else:
            reverted.append(entry + (f"\n  - your note: {note}" if note else ""))
    if not paper.auto_edits:
        lines.append("- none")
    elif len(reverted) == len(paper.auto_edits):
        lines.append("- none left standing; see below")

    if reverted:
        lines += ["", "## Automatic corrections you put back", ""]
        lines += reverted
        lines.append("")
        lines.append(
            "These were applied by the agent and undone by the editor. The "
            "author's own wording stands in the reviewed file, and the letter "
            "does not mention them."
        )

    lines += ["", "## Suggestions and what you decided", ""]
    any_decision = False
    for edit in paper.suggested_edits:
        decision = state.decision_for(edit.id)
        note = state.edit_notes.get(edit.id, "")
        lines.append(
            f"- **{decision}** — line {edit.line}: {plain.label(edit.check_id)} — "
            f"`{_short(edit.before, 60)}` → `{_short(edit.after, 60)}`"
            + (f"\n  - your note: {note}" if note else "")
        )
        any_decision = True
    if paper.reorder:
        edit_id = paper.reorder.get("id", "R1")
        lines.append(f"- **{state.decision_for(edit_id)}** — "
                     f"{plain.label('REF-NUM-02')}")
        any_decision = True
    if not any_decision:
        lines.append("- none offered")

    if state.manual_edits:
        lines += ["", "## Changes you made by hand", ""]
        for edit in state.manual_edits:
            lines.append(f"- line {edit.line}: {edit.summary}"
                         + (f"\n  - {edit.note}" if edit.note else ""))

    if state.ref_texts:
        lines += ["", "## References you wrote yourself", ""]
        for key, text in state.ref_texts.items():
            lines.append(f"- {key}: {_short(text, 160)}")

    if tags:
        lines += ["", "## JACoW tags", "", ", ".join(tags)]

    if state.editor_notes:
        lines += ["", "## Issues you found", ""]
        for note in state.editor_notes:
            where = f" ({note.where})" if note.where else ""
            audience = "to the author" if note.for_author else "internal"
            lines.append(f"- [{note.severity}] {note.text}{where} — {audience}")

    lines += ["", "## Letter sent to the author", "", "```", letter, "```", ""]
    return "\n".join(lines)
