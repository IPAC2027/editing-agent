"""End-to-end reference extraction and checking workflow for Word submissions."""

from __future__ import annotations

from pathlib import Path

from src.autofix.word_fixes import fix_reference
from src.checks.word_reference_checks import run_all
from src.output.word_report import write_word_reference_report
from src.parser.word_parser import parse_word


class WordPrescreenResult:
    """Lightweight result object for Word reference checking."""

    def __init__(self, paper_id: str, out_dir: Path, report_path: Path,
                 total_refs: int, findings: list) -> None:
        self.paper_id = paper_id
        self.out_dir = out_dir
        self.report_path = report_path
        self.total_refs = total_refs
        self.findings = findings


def prescreen_word(folder: Path) -> WordPrescreenResult:
    """Extract references from a Word submission, check them, and emit HTML output.

    Writes ``word_references.html`` into ``<folder>/aiagent_prescreen/``.
    """
    doc_path = _find_word_doc(folder)
    parsed = parse_word(doc_path)

    findings = run_all(parsed)

    # Apply safe fixes reference-by-reference and collect per-ref findings
    refs_before: list[tuple[int, str]] = []
    refs_after: list[tuple[int, str]] = []
    findings_by_ref: dict[int, list] = {}

    for ref in parsed.references:
        refs_before.append((ref.n, ref.raw_text))
        ref_findings = [f for f in findings if f.line == ref.n]
        suggested_doi = next(
            (
                f.suggested for f in ref_findings
                if f.check_id == "DOI-REQ-01" and f.suggested
            ),
            None,
        )
        corrected, fix_findings = fix_reference(
            ref.n,
            ref.raw_text,
            suggested_doi=suggested_doi,
        )
        refs_after.append((ref.n, corrected))
        findings_by_ref.setdefault(ref.n, [])
        findings_by_ref[ref.n].extend(ref_findings)
        findings_by_ref[ref.n].extend(fix_findings)

    global_findings = [f for f in findings if f.line is None or f.line <= 0]
    all_findings = global_findings + [f for fl in findings_by_ref.values() for f in fl]

    out_dir = folder / "aiagent_prescreen"
    out_dir.mkdir(exist_ok=True)

    report_path = write_word_reference_report(
        parsed.paper_id,
        refs_before,
        refs_after,
        findings_by_ref,
        global_findings,
        out_dir,
    )

    return WordPrescreenResult(
        paper_id=parsed.paper_id,
        out_dir=out_dir,
        report_path=report_path,
        total_refs=len(parsed.references),
        findings=all_findings,
    )


def _find_word_doc(folder: Path) -> Path:
    """Find the primary Word document in a submission folder."""
    candidates: list[Path] = []
    for d in (folder / "Source_Files", folder):
        if not d.is_dir():
            continue
        for path in d.iterdir():
            if path.is_file() and path.suffix.lower() in {".docx", ".doc"}:
                candidates.append(path)
    if not candidates:
        raise FileNotFoundError(f"No Word document found under {folder}")

    # Prefer .docx in Source_Files, then any .docx, then .doc
    candidates.sort(key=lambda p: (
        p.suffix.lower() != ".docx",
        p.parent.name != "Source_Files",
        p.name.lower(),
    ))
    return candidates[0]
