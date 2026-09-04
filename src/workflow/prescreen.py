"""End-to-end prescreen workflow for a single submission folder.

The shape of a run
------------------
1. Parse the source (``.tex`` plus any ``.bib``).
2. Run the deterministic checks, which produce **findings** — things a human
   must decide or chase.
3. Compute **edits** — byte-exact, individually reversible span replacements.
4. Apply the AUTO tier and nothing else.  Recompile to prove the result builds.
5. Write the review surface: ``review.html`` (one decision per SUGGEST edit),
   per-edit patches, a git history, and ``edits.json`` for ``aiagent apply``.

Two invariants hold by construction, and are asserted by the test suite:

* **An edit that changes nothing cannot be reported.**  :class:`~src.edits.Edit`
  refuses ``before == after``, so the count in ``report.md``, the contents of
  ``edits.json``, the diff and the file on disk can never disagree — which they
  did in every previous run (nine of ten sample papers came out byte-identical
  while the report announced auto-fixes).
* **A check that could not reach its authority reports NOT CHECKED**, never a
  problem with the paper.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src.checks import formatting_checks, reference_checks, template_checks
from src.edits import Decisions, EditSet, Tier, sha256
from src.lookup_status import STATUS
from src.models import Finding, Paper, Severity
from src.parser import bib_parser, latex_parser


class WordSubmissionError(Exception):
    """Raised when the submission appears to be a Word document, not LaTeX."""


_WORD_EXTS = {".docx", ".doc", ".odt", ".rtf"}

# How many items an editor should have to look at per paper.  Not a hard cap —
# a genuinely broken paper has more — but exceeding it is a signal that the
# report is padded rather than informative, and the collapse rules below exist
# to keep it honest.
NOISE_BUDGET = 5


def detect_source_format(folder: Path) -> str:
    """Return ``'latex'``, ``'word'``, or ``'unknown'`` for *folder*."""
    for directory in (folder / "Source_Files", folder):
        if not directory.is_dir():
            continue
        extensions = {f.suffix.lower() for f in directory.iterdir() if f.is_file()}
        if ".tex" in extensions:
            return "latex"
        if extensions & _WORD_EXTS:
            return "word"
    return "unknown"


def _find_tex(folder: Path) -> Path:
    candidates = list((folder / "Source_Files").glob("*.tex"))
    if not candidates:
        raise FileNotFoundError(f"No .tex file found under {folder / 'Source_Files'}")
    return candidates[0]


def _find_bibs(folder: Path) -> list[Path]:
    """Every ``.bib`` file in the submission, most authoritative first.

    Only the *first* file in one directory used to be read, so a submission
    that splits its bibliography across two resources (as the JACoW template
    invites, with one file for unpublished work) had every key from the second
    file reported as an unresolved citation.
    """
    found: list[Path] = []
    for directory in (
        folder / "BibTeX_file_only_for_LaTeX_papers",
        folder / "Source_Files",
        folder / "Supporting_files_for_papers",
        folder,
    ):
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.bib")))
    # Ignore anything we previously generated.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved in seen or "aiagent_prescreen" in path.parts:
            continue
        seen.add(resolved)
        ordered.append(path)
    return ordered


def _find_bib(folder: Path) -> Path | None:
    """The primary ``.bib`` file, for backwards compatibility."""
    bibs = _find_bibs(folder)
    return bibs[0] if bibs else None


# ---------------------------------------------------------------------------
# Findings hygiene
# ---------------------------------------------------------------------------

def suppress_resolved_findings(
    findings: list[Finding],
    editset: EditSet,
    structural=None,
    extra: list[EditSet] | None = None,
) -> list[Finding]:
    """Drop findings that a proposed edit already resolves.

    A check and the edit that fixes it are two views of one problem.  Reporting
    both is how ``DOI-FMT-02`` came to appear twice per occurrence at two
    different severities — 39 warnings on the sample corpus, every one of them
    duplicating an edit the tool had already made.

    A finding survives only if no edit with the same ``check_id`` covers the
    same text or line.
    """
    by_check: dict[str, list] = {}
    for edit in editset.edits:
        by_check.setdefault(edit.check_id, []).append(edit)
    # Edits to the .bib file resolve reference-level findings too, even though
    # they live in a different file and so have different line numbers.
    bib_checks: set[str] = set()
    for other in (extra or []):
        bib_checks |= {edit.check_id for edit in other.edits}

    # A structural decision resolves its whole check for this paper: the
    # reference list either gets reordered or it does not, and telling the
    # editor about each misplaced entry as well as offering the reorder is the
    # same problem described twice.
    structural_checks = {
        decision.check_id for decision in (structural.decisions if structural else [])
    }
    if not by_check and not structural_checks and not bib_checks:
        return findings

    kept: list[Finding] = []
    for finding in findings:
        if finding.check_id in structural_checks or finding.check_id in bib_checks:
            continue
        edits = by_check.get(finding.check_id)
        if not edits:
            kept.append(finding)
            continue
        original = (finding.original or "").strip()
        resolved = False
        for edit in edits:
            if original and (original in edit.before or edit.before.strip() in original):
                resolved = True
                break
            if finding.line is not None and finding.line == edit.line:
                resolved = True
                break
            if not original and finding.line is None:
                resolved = True
                break
        if not resolved:
            kept.append(finding)
    return kept


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Collapse duplicate and redundant findings.

    Two rules, both learned from the sample corpus:

    * The same ``(check_id, line, original)`` reported twice — once by a check
      and once by the fix that handled it — becomes one.  ``DOI-FMT-02`` was
      reported twice per occurrence at two different severities.
    * More than three findings sharing a ``check_id`` with no line number
      collapse into a count, because a wall of identical messages is not
      information.
    """
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.check_id, finding.line, (finding.original or "")[:120])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)

    by_check: dict[str, list[Finding]] = {}
    for finding in unique:
        by_check.setdefault(finding.check_id, []).append(finding)

    result: list[Finding] = []
    for check_id, group in by_check.items():
        unlocated = [f for f in group if f.line is None]
        located = [f for f in group if f.line is not None]
        result.extend(located)
        if len(unlocated) <= 3:
            result.extend(unlocated)
            continue
        worst = max(unlocated, key=lambda f: ["info", "warning", "error"].index(f.severity.value))
        result.append(Finding(
            check_id=check_id,
            severity=worst.severity,
            message=(
                f"{len(unlocated)} references have this issue: {worst.message} "
                f"(first of {len(unlocated)}; see report.json for the full list)"
            ),
            original=worst.original,
        ))
    result.sort(key=lambda f: (
        {"error": 0, "warning": 1, "info": 2}[f.severity.value],
        f.check_id,
        f.line or 0,
    ))
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def prescreen(
    folder: Path,
    *,
    llm: bool = False,
    compile: bool = True,
    git: bool = True,
) -> Paper:
    """Pre-screen a single submission *folder*.

    Writes into ``<folder>/aiagent_prescreen/``:

    ==========================  ===================================================
    ``review.html``             one accept/reject decision per SUGGEST edit
    ``<ID>_edited.tex``         source with the AUTO tier applied, nothing else
    ``edits.json``              the machine-readable EditSet, read by ``apply``
    ``edits/E0NN.patch``        every edit as a standalone, applicable diff
    ``history/``                a git repo with one commit per edit
    ``changes.patch``           AUTO + SUGGEST as one diff, for a diff tool
    ``report.md`` / ``.json``   findings, and which checks did not run
    ``<ID>_edited.pdf``         compiled proof that the edited source builds
    ==========================  ===================================================
    """
    STATUS.reset()

    fmt = detect_source_format(folder)
    if fmt == "word":
        from src.workflow.word_prescreen import prescreen_word

        return prescreen_word(folder)  # type: ignore[return-value]

    tex_path = _find_tex(folder)
    bib_paths = _find_bibs(folder)
    bib_path = bib_paths[0] if bib_paths else None
    source = tex_path.read_text(encoding="utf-8", errors="replace")

    # --- Parse -----------------------------------------------------------
    paper = latex_parser.parse_latex(tex_path)
    for path in bib_paths:
        existing = {ref.key for ref in paper.references}
        try:
            entries = bib_parser.parse_bib(path)
        except Exception as exc:  # noqa: BLE001 — a malformed .bib is a finding
            paper.findings.append(Finding(
                check_id="BIB-PARSE-01",
                severity=Severity.WARNING,
                message=f"{path.name} could not be parsed ({type(exc).__name__}); "
                        "its entries were not checked.",
            ))
            continue
        for ref in entries:
            if ref.key not in existing:
                paper.references.append(ref)

    # --- Checks (findings: things a human decides) ------------------------
    template_checks.run_all(paper)
    reference_checks.run_all(paper)
    formatting_checks.run_all(paper)

    # --- Edits (things the tool can do to the bytes) ---------------------
    from src.autofix.latex_edits import all_source_edits
    from src.autofix.reference_edits import bib_field_edits, bibitem_rewrite_edits
    from src.autofix.structural import StructuralPlan, plan_reorder
    from src.refs.text_utils import lowercase_evidence

    parsed = paper.__dict__.get("_pt")
    evidence_words = lowercase_evidence(source)

    candidates = all_source_edits(
        source,
        file=tex_path.name,
        # Deliberately the *narrow* spans: author names without affiliations or
        # emails, title text without its \thanks footnote.
        author_span=getattr(parsed, "author_names_span", None),
        title_span=getattr(parsed, "title_text_span", None),
    )
    rewrite_edits, rewrite_findings = bibitem_rewrite_edits(
        source, paper, file=tex_path.name, evidence_words=evidence_words,
    )
    candidates.extend(rewrite_edits)
    paper.findings.extend(rewrite_findings)

    # Stage two: structural changes, applied after the span edits.
    structural = StructuralPlan(file=tex_path.name, reorder=plan_reorder(source, paper))

    editset, dropped = EditSet.build(source, tex_path.name, candidates)
    if dropped:
        paper.findings.append(Finding(
            check_id="EDIT-OVERLAP-01",
            severity=Severity.INFO,
            message=(
                f"{len(dropped)} candidate edit(s) were discarded because a "
                "narrower or better-evidenced edit already covered the same text."
            ),
        ))

    # --- Output ----------------------------------------------------------
    out_dir = folder / "aiagent_prescreen"
    _reset_dir(out_dir)

    from src.output.review import (
        write_git_history,
        write_per_edit_patches,
        write_review_html,
    )

    editset.write(out_dir / "edits.json")
    structural.write(out_dir / "structural.json")
    if structural.reorder and structural.reorder.needed:
        from src.autofix.structural import diff_reorder

        (out_dir / "edits" ).mkdir(parents=True, exist_ok=True)
        try:
            (out_dir / "edits" / f"{structural.reorder.id}.patch").write_text(
                diff_reorder(
                    editset.apply(source, [e.id for e in editset.auto]),
                    structural.reorder,
                    tex_path.name,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — a patch we cannot render is not fatal
            pass
    write_per_edit_patches(editset, source, out_dir)
    (out_dir / "changes.patch").write_text(
        editset.unified_diff(source), encoding="utf-8",
    )

    # Only the AUTO tier lands in the edited source.  Everything else waits
    # for a decision — that is the whole point.
    auto_ids = [edit.id for edit in editset.auto]
    edited_source = editset.apply(source, auto_ids)
    edited_path = out_dir / f"{paper.paper_id}_edited.tex"
    edited_path.write_text(edited_source, encoding="utf-8")

    history = write_git_history(editset, source, out_dir, paper_id=paper.paper_id)

    # --- Separately, the .bib file (biblatex submissions) ----------------
    bib_editset = None
    if bib_path:
        bib_source = bib_path.read_text(encoding="utf-8", errors="replace")
        bib_editset, _ = EditSet.build(
            bib_source, bib_path.name, bib_field_edits(bib_source, file=bib_path.name),
        )
        if bib_editset.edits:
            bib_editset.write(out_dir / "edits_bib.json")
            (out_dir / f"{bib_path.stem}_edited.bib").write_text(
                bib_editset.apply(bib_source, [e.id for e in bib_editset.auto]),
                encoding="utf-8",
            )
            (out_dir / "changes_bib.patch").write_text(
                bib_editset.unified_diff(bib_source), encoding="utf-8",
            )
            paper.findings.append(Finding(
                check_id="BIB-EDIT-01",
                severity=Severity.INFO,
                message=(
                    f"{len(bib_editset.edits)} edit(s) proposed for {bib_path.name} "
                    f"({len(bib_editset.auto)} applied automatically). "
                    f"See changes_bib.patch and {bib_path.stem}_edited.bib."
                ),
            ))

    # --- Build validation ------------------------------------------------
    build_status = "not compiled"
    if compile:
        build_status = _compile(folder, edited_path, paper, out_dir)

    # --- Optional model assistance ---------------------------------------
    if llm:
        _suppress_with_model(paper, source)
        _run_llm_suggestions(paper, out_dir, source)

    # --- Reports ---------------------------------------------------------
    paper.findings = dedupe_findings(
        suppress_resolved_findings(
            paper.findings, editset, structural,
            extra=[bib_editset] if bib_editset else None,
        )
    )

    from src.output.report import write_report

    write_report(
        paper,
        out_dir,
        editset=editset,
        build_status=build_status,
        bib_editset=bib_editset,
    )
    write_review_html(
        editset,
        out_dir,
        paper_id=paper.paper_id,
        folder=str(folder),
        findings=paper.findings,
        auto_applied=len(auto_ids),
        build_status=build_status,
        has_history=history is not None,
        structural=structural,
    )

    paper.__dict__["editset"] = editset
    paper.__dict__["structural"] = structural
    paper.__dict__["auto_applied"] = len(auto_ids)
    paper.__dict__["decisions_pending"] = len(editset.suggested) + len(structural.decisions)
    paper.__dict__["source_sha256"] = sha256(source)
    return paper


#: Files in the output directory that belong to the editor, not to the agent.
#: A re-screen regenerates everything else, but wiping these would throw away
#: decisions, notes and hand edits — which is exactly what an editor does when
#: they press "Prepare this paper again" after the author resubmits.
EDITOR_OWNED = ("review_state.json", "review_decisions.json")


def _reset_dir(out_dir: Path) -> None:
    """Make *out_dir* exist and be empty, keeping anything the editor owns.

    ``shutil.rmtree`` used to be unconditional, which had two problems: a run
    failed outright on any filesystem that refuses deletion (a read-only mount,
    a synced folder, a locked PDF), and it deleted the editor's review state
    along with the agent's output.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    keep: dict[str, bytes] = {}
    for name in EDITOR_OWNED:
        path = out_dir / name
        if path.is_file():
            try:
                keep[name] = path.read_bytes()
            except OSError:
                pass

    try:
        shutil.rmtree(out_dir)
    except OSError:
        for child in sorted(out_dir.rglob("*"), reverse=True):
            if child.is_file() and child.name not in EDITOR_OWNED:
                try:
                    child.unlink()
                except OSError:
                    pass
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, data in keep.items():
        try:
            (out_dir / name).write_bytes(data)
        except OSError:
            pass


def apply_decisions(
    folder: Path,
    *,
    accept: list[str] | None = None,
    reject: list[str] | None = None,
    decisions_path: Path | None = None,
    write_to_source: bool = False,
    compile: bool = True,
) -> tuple[Path, list[str], list[str]]:
    """Apply a chosen subset of edits from a previous prescreen run.

    This is the command that was missing.  ``review.html`` recorded decisions
    into browser storage and downloaded a JSON file that nothing read, so the
    editor's only real choice was all-or-nothing.

    Returns ``(written_path, applied_ids, skipped_ids)``.  Every ``before`` is
    verified against the current source first, so a source the author has since
    revised produces a clear conflict instead of a scrambled file.
    """
    out_dir = folder / "aiagent_prescreen"
    editset_path = out_dir / "edits.json"
    if not editset_path.exists():
        raise FileNotFoundError(
            f"No edits.json in {out_dir}. Run 'prescreen' on this folder first."
        )
    editset = EditSet.read(editset_path)

    tex_path = _find_tex(folder)
    source = tex_path.read_text(encoding="utf-8", errors="replace")

    chosen = [edit.id for edit in editset.auto]
    if decisions_path is not None:
        path = decisions_path
        if not path.is_absolute():
            path = folder / path if (folder / path).exists() else out_dir / path
        decisions = Decisions.read(path)
        chosen = decisions.accepted(editset)
    if accept:
        chosen.extend(accept)
    if reject:
        rejected = set(reject)
        chosen = [edit_id for edit_id in chosen if edit_id not in rejected]

    # Preserve order and drop duplicates.
    seen: set[str] = set()
    ordered = [i for i in chosen if not (i in seen or seen.add(i))]

    # Stage two ids (structural changes) are applied separately, after the span
    # edits, so they must not be handed to EditSet.apply.
    from src.autofix.structural import StructuralPlan, apply_reorder

    structural_path = out_dir / "structural.json"
    plan = StructuralPlan.read(structural_path) if structural_path.exists() else None
    structural_ids = {decision.id for decision in plan.decisions} if plan else set()

    span_known = {edit.id for edit in editset.edits}
    unknown = [i for i in ordered if i not in span_known and i not in structural_ids]
    span_ids = [i for i in ordered if i in span_known]
    chosen_structural = [i for i in ordered if i in structural_ids]

    result = editset.apply(source, span_ids)

    # Re-derived against the text stage one produced, so the entry boundaries
    # are always current and a changed reference list is a clear conflict.
    applied_structural: list[str] = []
    if plan:
        for decision in plan.decisions:
            if decision.id in set(chosen_structural):
                result = apply_reorder(result, decision)
                applied_structural.append(decision.id)

    applied = span_ids + applied_structural
    target = tex_path if write_to_source else out_dir / f"{tex_path.stem}_edited.tex"
    target.write_text(result, encoding="utf-8")

    if compile and not write_to_source:
        from src.latex_build import compile_tex

        try:
            compile_tex(folder, target, tex_path.stem, out_dir)
        except Exception:  # noqa: BLE001 — a failed proof build is reported, not fatal
            pass

    return target, applied, unknown


def _compile(folder: Path, edited_tex: Path, paper: Paper, out_dir: Path) -> str:
    """Compile *edited_tex* and record the outcome as a finding."""
    from src.latex_build import compile_tex

    parsed = paper.__dict__.get("_pt")
    uses_biblatex = parsed.uses_biblatex if parsed else False
    try:
        result = compile_tex(
            folder, edited_tex, paper.paper_id, out_dir, use_biblatex=uses_biblatex,
        )
    except FileNotFoundError:
        paper.findings.append(Finding(
            check_id="BUILD-SKIP",
            severity=Severity.INFO,
            message=(
                "NOT CHECKED — no LaTeX toolchain found, so the edited source was "
                "not compiled. Install TeX Live to have every run verified by a build."
            ),
        ))
        return "build not run (no LaTeX)"

    if result.success:
        paper.findings.append(Finding(
            check_id="BUILD-OK",
            severity=Severity.INFO,
            message=(
                "The edited source compiles: "
                f"{result.pdf_path.name if result.pdf_path else 'PDF generated'}. "
                "Every automatic change is therefore known not to break the build."
            ),
        ))
        if result.pdf_path and result.pdf_path.exists():
            from src.checks import layout_checks

            layout_checks.run_all(paper, result.pdf_path)
        return "edited source compiles"

    detail = "; ".join(result.errors[:3]) if result.errors else result.log_excerpt[-200:]
    paper.findings.append(Finding(
        check_id="BUILD-FAIL",
        severity=Severity.ERROR,
        message=f"The edited source does not compile. Errors: {detail}",
    ))
    return "edited source FAILS to compile"


def _suppress_with_model(paper: Paper, source: str) -> None:
    """Let a model hide findings it judges to be false positives.

    Deliberately one-directional: the model may remove a finding, never add
    one.  A wrong suppression leaves the editor exactly where they would be
    without the tool; a wrong addition sends them looking for a problem that is
    not there.  Suppressed findings are reported as a note rather than deleted,
    so the editor can always see what was hidden.
    """
    from src.llm.classify import suppress_false_positives

    candidates = [f for f in paper.findings if f.severity is not Severity.INFO]
    if not candidates:
        return
    kept, suppressed = suppress_false_positives(candidates, source)
    if not suppressed:
        return
    notes = [f for f in paper.findings if f.severity is Severity.INFO]
    paper.findings = kept + notes
    paper.findings.append(Finding(
        check_id="LLM-SUPPRESS-01",
        severity=Severity.INFO,
        message=(
            f"A model judged {len(suppressed)} finding(s) to be false positives and "
            "they were hidden: "
            + "; ".join(f"{f.check_id} at line {f.line}" for f in suppressed[:6])
            + ". Re-run with --no-llm to see them."
        ),
    ))


def _run_llm_suggestions(paper: Paper, out_dir: Path, source_text: str) -> None:
    """Run the constrained model review, if one is configured.

    The model is never allowed to author a bibliographic fact; see
    :mod:`src.llm.classify` for what it may and may not be asked.
    """
    from src.llm import client, prompts

    lines: list[str] = [
        "# Model review\n",
        "Advisory only. The model never edits source files and never supplies a DOI, "
        "year, volume, page range or venue — see docs/editor_workflow.md.\n",
    ]
    successes = 0
    try:
        system, user = prompts.latex_source_review_prompt(source_text)
        lines.append(f"## Complete LaTeX source\n\n{client.chat(system, user)}\n")
        successes += 1
    except Exception as exc:  # noqa: BLE001
        lines.append(f"## Complete LaTeX source\n\nNot available: {exc}\n")

    for ref in paper.references:
        try:
            system, user = prompts.reference_review_prompt(ref)
            lines.append(f"## Reference [{ref.n}] `{ref.key}`\n\n{client.chat(system, user)}\n")
            successes += 1
        except Exception as exc:  # noqa: BLE001
            lines.append(f"## Reference [{ref.n}] `{ref.key}`\n\nNot available: {exc}\n")

    path = out_dir / "llm_suggestions.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    paper.__dict__["llm_review_path"] = path.name
    if successes:
        paper.findings.append(Finding(
            check_id="LLM-REVIEW-01",
            severity=Severity.INFO,
            message=(
                f"A model produced {successes} advisory review(s) in {path.name}. "
                "Nothing there has been applied; treat every suggestion as unverified."
            ),
        ))
    else:
        paper.findings.append(Finding(
            check_id="LLM-REVIEW-01",
            severity=Severity.INFO,
            message=(
                f"NOT CHECKED — the model review could not run. See {path.name} for the "
                "connection error. No findings were suppressed or added as a result."
            ),
        ))
