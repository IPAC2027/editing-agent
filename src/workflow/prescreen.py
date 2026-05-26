"""End-to-end prescreen workflow for a single submission folder.

Folder layout expected
----------------------
<paper_folder>/
    Source_Files/          *.tex
    Supporting_files_for_papers/   images
    PDF/                   *.pdf
    BibTeX_file_only_for_LaTeX_papers/   *.bib  (optional)

Output written to
-----------------
<paper_folder>/aiagent_prescreen/
    report.json
    report.md
    <PaperID>_edited.tex
    changes.patch
    llm_suggestions.md     (only when LLM is enabled)
"""

from __future__ import annotations

from pathlib import Path

from src import checks, output
from src.checks import formatting_checks, reference_checks
from src.models import Paper
from src.parser import bib_parser, latex_parser


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


def prescreen(folder: Path, *, llm: bool = False) -> Paper:
    """Pre-screen a single submission *folder*.

    Parameters
    ----------
    folder:
        Path to the paper's top-level submission folder.
    llm:
        When ``True``, run LLM-assisted suggestions after deterministic checks.

    Returns
    -------
    Paper
        Fully populated model with all findings attached.
    """
    tex_path = _find_tex(folder)
    bib_path = _find_bib(folder)

    paper = latex_parser.parse_latex(tex_path)

    if bib_path:
        extra_refs = bib_parser.parse_bib(bib_path)
        # Merge bib entries into paper.references (by key)
        existing_keys = {r.key for r in paper.references}
        for ref in extra_refs:
            if ref.key not in existing_keys:
                paper.references.append(ref)

    # --- Priority 1: reference checks ---
    reference_checks.run_all(paper)

    # --- Priority 2: formatting checks ---
    formatting_checks.run_all(paper)

    # --- Safe auto-fixes ---
    from src.autofix.safe_fixes import apply_safe_fixes
    source_text = tex_path.read_text(encoding="utf-8")
    fixed_text, fix_findings = apply_safe_fixes(source_text)
    paper.findings.extend(fix_findings)

    # --- Output ---
    out_dir = folder / "aiagent_prescreen"
    out_dir.mkdir(exist_ok=True)

    from src.output.report import write_report
    from src.output.diff import write_diff

    write_report(paper, out_dir)
    write_diff(source_text, fixed_text, tex_path.name, out_dir)

    edited_path = out_dir / f"{paper.paper_id}_edited.tex"
    edited_path.write_text(fixed_text, encoding="utf-8")

    # --- LLM suggestions (optional) ---
    if llm:
        _run_llm_suggestions(paper, out_dir)

    return paper


def _run_llm_suggestions(paper: Paper, out_dir: Path) -> None:
    """Run LLM prompts for human-required items and write llm_suggestions.md."""
    from src.llm import client, prompts

    lines: list[str] = ["# LLM Suggestions\n"]

    for ref in paper.references:
        if not ref.doi:
            try:
                system, user = prompts.doi_lookup_prompt(ref)
                suggestion = client.chat(system, user)
                lines.append(f"## [{ref.n}] DOI suggestion\n\n{suggestion}\n")
            except Exception as exc:
                lines.append(f"## [{ref.n}] DOI suggestion\n\nError: {exc}\n")

    (out_dir / "llm_suggestions.md").write_text("\n".join(lines), encoding="utf-8")
