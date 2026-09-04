import json
from pathlib import Path

from src.models import Finding, Paper, Severity
from src.output.repair_plan import write_repair_plan


def test_repair_plan_records_evidence_and_successful_validation(tmp_path: Path):
    paper = Paper(paper_id="TEST", source_path=Path("/tmp/TEST.tex"))
    paper.findings.append(Finding(
        check_id="BUILD-OK",
        severity=Severity.INFO,
        message="LaTeX compilation succeeded → TEST_edited.pdf",
    ))
    fixes = [Finding(
        check_id="DOI-FMT-01",
        severity=Severity.INFO,
        line=3,
        original="DOI: 10.1000/example",
        suggested="doi:10.1000/example",
        message="Normalised DOI prefix to 'doi:'.",
        auto_fixed=True,
    )]

    path = write_repair_plan(
        paper,
        tmp_path,
        fixes,
        original_source="DOI: 10.1000/example\n",
        edited_source="doi:10.1000/example\n",
    )

    plan = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "repair_plan.json"
    assert plan["validation"]["status"] == "passed"
    assert plan["repairs"] == [{
        "id": "repair-001",
        "check_id": "DOI-FMT-01",
        "line": 3,
        "reason": "Normalised DOI prefix to 'doi:'.",
        "original": "DOI: 10.1000/example",
        "suggested": "doi:10.1000/example",
        "status": "pending_editor_review",
    }]
    assert plan["source_sha256"] != plan["edited_source_sha256"]


def test_repair_plan_records_when_compilation_was_not_run(tmp_path: Path):
    paper = Paper(paper_id="TEST", source_path=Path("/tmp/TEST.tex"))

    path = write_repair_plan(
        paper,
        tmp_path,
        [],
        original_source="original",
        edited_source="edited",
    )

    plan = json.loads(path.read_text(encoding="utf-8"))
    assert plan["validation"]["status"] == "not_run"
