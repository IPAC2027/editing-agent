from pathlib import Path

from src.llm import client
from src.models import Paper, Reference, Severity
from src.workflow.prescreen import _run_llm_suggestions


def test_local_llm_review_checks_source_and_every_reference(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_chat(_system: str, user: str, *, model: str | None = None) -> str:
        calls.append(user)
        return "PASS"

    monkeypatch.setattr(client, "chat", fake_chat)
    paper = Paper(
        paper_id="TEST",
        source_path=Path("/tmp/TEST.tex"),
        references=[
            Reference(n=1, key="first", raw_text="A. Author, First reference."),
            Reference(n=2, key="second", raw_text="B. Author, Second reference."),
        ],
    )

    _run_llm_suggestions(paper, tmp_path, r"\title{TEST}")

    review = (tmp_path / "llm_suggestions.md").read_text(encoding="utf-8")
    assert len(calls) == 3
    assert "Review this complete JACoW LaTeX source" in calls[0]
    assert "Citation key: first" in calls[1]
    assert "Citation key: second" in calls[2]
    assert "## Complete LaTeX source" in review
    assert "## Reference [1] `first`" in review
    assert "## Reference [2] `second`" in review
    assert paper.findings[-1].check_id == "LLM-REVIEW-01"
    assert paper.findings[-1].severity == Severity.INFO
