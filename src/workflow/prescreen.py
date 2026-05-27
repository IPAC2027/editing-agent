"""End-to-end prescreen workflow for a single submission folder."""

from __future__ import annotations

from pathlib import Path

import shutil

from src.checks import formatting_checks, reference_checks, template_checks
from src.models import Paper, Severity
from src.parser import bib_parser, latex_parser


class WordSubmissionError(Exception):
    """Raised when the submission appears to be a Word document, not LaTeX."""


_WORD_EXTS = {".docx", ".doc", ".odt", ".rtf"}


def detect_source_format(folder: Path) -> str:
    """Return ``'latex'``, ``'word'``, or ``'unknown'`` for *folder*.

    Checks the contents of ``Source_Files/`` (and the folder root as a
    fallback) for recognisable source file extensions.
    """
    search_dirs = [folder / "Source_Files", folder]
    for d in search_dirs:
        if not d.is_dir():
            continue
        exts = {f.suffix.lower() for f in d.iterdir() if f.is_file()}
        if ".tex" in exts:
            return "latex"
        if exts & _WORD_EXTS:
            return "word"
    return "unknown"


def _find_tex(folder: Path) -> Path:
    candidates = list((folder / "Source_Files").glob("*.tex"))
    if not candidates:
        raise FileNotFoundError(f"No .tex file found under {folder / 'Source_Files'}")
    return candidates[0]


def _find_bib(folder: Path) -> Path | None:
    bib_dir = folder / "BibTeX_file_only_for_LaTeX_papers"
    if bib_dir.exists():
        bibs = list(bib_dir.glob("*.bib"))
        if bibs:
            return bibs[0]
    # Also accept a .bib alongside the .tex
    tex_dir = folder / "Source_Files"
    bibs = list(tex_dir.glob("*.bib"))
    return bibs[0] if bibs else None


def prescreen(folder: Path, *, llm: bool = False, compile: bool = False) -> Paper:
    """Pre-screen a single submission *folder*.

    Writes the following into ``<folder>/aiagent_prescreen/``:

    - ``index.html``          — summary dashboard (open in browser)
    - ``changes.html``        — side-by-side colour diff (open in browser)
    - ``changes.patch``       — unified diff (apply with ``patch``)
    - ``<ID>_edited.tex``     — source with all safe auto-fixes applied
    - ``<ID>_edited.pdf``     — compiled PDF of the fixed source (if ``compile``)
    - ``report.md``           — Markdown findings for the editor
    - ``report.json``         — machine-readable findings
    - ``llm_suggestions.md``  — LLM hints (only when ``--llm``)
    """
    fmt = detect_source_format(folder)
    if fmt == "word":
        src = next(
            (f for d in (folder / "Source_Files", folder)
             if d.is_dir()
             for f in d.iterdir()
             if f.suffix.lower() in _WORD_EXTS),
            None,
        )
        fname = src.name if src else "Word document"
        raise WordSubmissionError(
            f"{folder.name} is a Word submission ({fname}) — skipped. "
            "Convert to LaTeX with Pandoc to enable pre-screening."
        )

    tex_path = _find_tex(folder)
    bib_path = _find_bib(folder)

    # --- Parse ---
    paper = latex_parser.parse_latex(tex_path)

    if bib_path:
        extra_refs = bib_parser.parse_bib(bib_path)
        existing_keys = {r.key for r in paper.references}
        for ref in extra_refs:
            if ref.key not in existing_keys:
                paper.references.append(ref)

    # --- Checks ---
    template_checks.run_all(paper)
    reference_checks.run_all(paper)
    formatting_checks.run_all(paper)   # stubs — no-ops in Phase 1

    # --- Safe auto-fixes ---
    from src.autofix.safe_fixes import apply_safe_fixes, apply_paper_fixes
    source_text = tex_path.read_text(encoding="utf-8", errors="replace")
    fixed_text, fix_findings = apply_safe_fixes(source_text)
    fixed_text, paper_fix_findings = apply_paper_fixes(fixed_text, paper)
    paper.findings.extend(fix_findings)
    paper.findings.extend(paper_fix_findings)

    # If REF-NUM-02 was auto-fixed by bibitem reordering, downgrade the
    # pre-fix REF-NUM-02 findings from ERROR to WARNING for this run.
    ref_num_autofixed = any(
        f.check_id == "REF-NUM-02" and f.auto_fixed for f in paper_fix_findings
    )
    if ref_num_autofixed:
        for finding in paper.findings:
            if finding.check_id == "REF-NUM-02" and finding.severity == Severity.ERROR:
                finding.severity = Severity.WARNING

    # --- Output ---
    out_dir = folder / "aiagent_prescreen"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()

    from src.output.report import write_report
    from src.output.diff import write_diff

    write_diff(source_text, fixed_text, tex_path.name, out_dir)

    edited_path = out_dir / f"{paper.paper_id}_edited.tex"
    edited_path.write_text(fixed_text, encoding="utf-8")

    # --- LaTeX compilation (optional) ---
    if compile:
        _compile(folder, edited_path, paper, out_dir)

    # --- LLM suggestions (optional) ---
    if llm:
        _run_llm_suggestions(paper, out_dir)

    # Write report after ALL checks (including compile-time checks like PAGE-LIMIT-01)
    write_report(paper, out_dir)

    return paper


def _compile(folder: Path, edited_tex: Path, paper: Paper, out_dir: Path) -> None:
    """Compile *edited_tex* with the latest JACoW class and place PDF in *out_dir*."""
    from src.latex_build import compile_tex
    pt = paper.__dict__.get("_pt")
    uses_biblatex = pt.uses_biblatex if pt else False
    result = compile_tex(
        folder, edited_tex, paper.paper_id, out_dir,
        use_biblatex=uses_biblatex,
    )
    from src.models import Finding, Severity
    if result.success:
        paper.findings.append(Finding(
            check_id="BUILD-OK",
            severity=Severity.INFO,
            message=f"LaTeX compilation succeeded → {result.pdf_path.name if result.pdf_path else 'PDF generated'}",
        ))
        if result.pdf_path and result.pdf_path.exists():
            from src.checks import layout_checks
            layout_checks.run_all(paper, result.pdf_path)
    else:
        detail = "; ".join(result.errors[:3]) if result.errors else result.log_excerpt[-200:]
        paper.findings.append(Finding(
            check_id="BUILD-FAIL",
            severity=Severity.ERROR,
            message=f"LaTeX compilation failed. Errors: {detail}",
        ))


def _run_llm_suggestions(paper: Paper, out_dir: Path) -> None:
    from src.llm import client, prompts

    lines: list[str] = ["# LLM Suggestions\n",
                        "These suggestions require human review before applying.\n"]
    for ref in paper.references:
        if not ref.doi:
            try:
                system, user = prompts.doi_lookup_prompt(ref)
                suggestion = client.chat(system, user)
                lines.append(f"## [{ref.n}] DOI suggestion for `{ref.key}`\n\n{suggestion}\n")
            except Exception as exc:
                lines.append(f"## [{ref.n}] DOI suggestion for `{ref.key}`\n\nError: {exc}\n")

    (out_dir / "llm_suggestions.md").write_text("\n".join(lines), encoding="utf-8")
