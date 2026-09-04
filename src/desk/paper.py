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
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.desk import plain
from src.desk.state import ManualEdit, ReviewState, finding_key
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

        self.source_path = self._find_source()
        self.source = ""
        if self.source_path and self.source_path.suffix.lower() == ".tex":
            self.source = self.source_path.read_text(encoding="utf-8", errors="replace")

        if not self.state.paper_id:
            self.state.paper_id = self.report.get("paper_id", folder.name)

    @property
    def screened(self) -> bool:
        return bool(self.report)

    @property
    def paper_id(self) -> str:
        return self.state.paper_id or self.report.get("paper_id", self.folder.name)

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

    def suggested_ids(self) -> list[str]:
        ids = [edit.id for edit in self.suggested_edits]
        if self.reorder:
            ids.append(self.reorder.get("id", "R1"))
        return ids


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

    if not paper.screened:
        return {
            "folder": str(folder),
            "name": folder.name,
            "paper_id": paper.paper_id,
            "kind": paper.kind,
            "screened": False,
            "message": (
                "This paper has not been prepared yet. Press “Prepare this paper” "
                "and the agent will read it, apply the safe corrections and list "
                "anything that needs you."
            ),
        }

    decisions = [_decision_card(edit, state) for edit in paper.suggested_edits]
    if paper.reorder:
        decisions.insert(0, _reorder_card(paper.reorder, state))

    applied = [_applied_card(edit, state) for edit in paper.auto_edits]

    findings = _finding_cards(
        paper.report.get("findings", []), state,
        covered=_covered_by_corrections(paper),
    )

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
    }


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
    if paper.editset:
        chosen = [edit.id for edit in paper.auto_edits
                  if paper.state.auto_decision(edit.id) == "applied"]
        for edit in paper.suggested_edits:
            decision = paper.state.decision_for(edit.id)
            if decision == "accepted" or (include_undecided and decision == "undecided"):
                chosen.append(edit.id)
        try:
            text = paper.editset.apply(paper.source, chosen)
        except EditConflict as exc:
            raise DeskError(
                "The author's file has changed since this paper was prepared, so "
                "the corrections no longer line up. Press “Prepare this paper” "
                "again — your decisions and notes are kept."
            ) from exc

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
    return text


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
        final_path.write_text(final, encoding="utf-8")
        written.append(final_path.name)

        if compile_pdf:
            from src.latex_build import compile_tex

            try:
                result = compile_tex(folder, final_path, f"{paper.paper_id}_final",
                                     paper.out_dir)
                if result.success and result.pdf_path and result.pdf_path.exists():
                    written.append(result.pdf_path.name)
            except Exception:  # noqa: BLE001 — a failed proof build must not block closing
                pass

    if paper.kind == "word":
        written += _write_reviewed_docx(paper)

    letter = state.letter_override.strip() or letter_text(paper)
    letter_path = paper.out_dir / "author_letter.txt"
    letter_path.write_text(letter + "\n", encoding="utf-8")
    written.append(letter_path.name)

    # Set the outcome before writing the summary, so the summary records the
    # state the paper is actually leaving in rather than the one it arrived in.
    state.status = status
    state.closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.save(folder)

    summary_path = paper.out_dir / "review_summary.md"
    summary_path.write_text(_summary_markdown(paper, letter), encoding="utf-8")
    written.append(summary_path.name)

    return {"written": written, "status": state.status,
            "status_word": state.status_word}


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
    accepted = [
        c for c in paper.word_corrections
        if (c.get("tier") == "auto"
            and paper.state.auto_decision(c.get("id", "")) == "applied")
        or paper.state.decision_for(c.get("id", "")) == "accepted"
    ]
    target = paper.out_dir / f"{paper.source_path.stem}_reviewed.docx"
    if not accepted:
        # Nothing to change: hand over a clean copy so there is always one
        # file that is "the reviewed document".
        shutil.copy2(paper.source_path, target)
        return [target.name]

    from src.output.docx_tracked import ParagraphRewrite, write_tracked_docx

    rewrites = [
        ParagraphRewrite(
            paragraph_index=c["paragraph_index"],
            before=c["before"],
            after=c["after"],
            author=f"JACoW prescreen ({', '.join(c.get('checks') or [c['check_id']])})",
        )
        for c in accepted
        if c.get("paragraph_index", -1) >= 0
    ]
    try:
        _path, _revisions, _skipped = write_tracked_docx(
            paper.source_path, target, rewrites,
        )
    except Exception as exc:  # noqa: BLE001
        raise DeskError(
            "The reviewed Word file could not be written "
            f"({type(exc).__name__}). Your decisions are saved; the tracked "
            "changes file from preparation is still there."
        ) from exc
    return [target.name]


def _summary_markdown(paper: Paper, letter: str) -> str:
    state = paper.state
    lines = [
        f"# Review summary — {paper.paper_id}",
        "",
        f"Editor: {state.editor or '(not named)'}",
        f"Status: {state.status_word}",
        f"Closed: {state.closed_at or '(open)'}",
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

    if state.editor_notes:
        lines += ["", "## Issues you found", ""]
        for note in state.editor_notes:
            where = f" ({note.where})" if note.where else ""
            audience = "to the author" if note.for_author else "internal"
            lines.append(f"- [{note.severity}] {note.text}{where} — {audience}")

    lines += ["", "## Letter sent to the author", "", "```", letter, "```", ""]
    return "\n".join(lines)
