"""JACoW Conference Paper AI Agent — CLI entry point.

Usage examples
--------------
  uv run python main.py prescreen paper_examples/MOP019-revision-27544_author
  uv run python main.py prescreen-all paper_examples/ --workers 4
  uv run python main.py prescreen paper_examples/MOP019-revision-27544_author --llm
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(
    name="aiagent",
    help="Agentic pre-screening tool for JACoW/IPAC conference paper submissions.",
    add_completion=False,
)
console = Console()


@app.command()
def prescreen(
    paper_folder: Path = typer.Argument(..., help="Path to one submission folder."),
    llm: bool = typer.Option(False, "--llm/--no-llm", help="Enable LLM suggestions."),
    model: str = typer.Option(None, envvar="LLM_MODEL", help="LLM model name."),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL", help="LLM base URL."),
) -> None:
    """Pre-screen a single submission folder."""
    import os

    if model:
        os.environ["LLM_MODEL"] = model
    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    if llm:
        os.environ["LLM_ENABLED"] = "true"

    if not paper_folder.is_dir():
        console.print(f"[red]Error:[/red] {paper_folder} is not a directory.")
        raise typer.Exit(1)

    console.print(f"[bold]Pre-screening:[/bold] {paper_folder.name}")

    from src.workflow.prescreen import prescreen as _prescreen

    paper = _prescreen(paper_folder, llm=llm)

    errors = sum(1 for f in paper.findings if f.severity.value == "error")
    warnings = sum(1 for f in paper.findings if f.severity.value == "warning")
    auto_fixed = sum(1 for f in paper.findings if f.auto_fixed)

    t = Table(title=f"Results — {paper.paper_id}")
    t.add_column("Errors", style="red")
    t.add_column("Warnings", style="yellow")
    t.add_column("Auto-fixed", style="green")
    t.add_row(str(errors), str(warnings), str(auto_fixed))
    console.print(t)

    out_dir = paper_folder / "aiagent_prescreen"
    console.print(f"Report written to [cyan]{out_dir}[/cyan]")


@app.command("prescreen-all")
def prescreen_all(
    submissions_dir: Path = typer.Argument(..., help="Directory containing all submission folders."),
    llm: bool = typer.Option(False, "--llm/--no-llm", help="Enable LLM suggestions."),
    workers: int = typer.Option(1, "--workers", "-j", help="Parallel workers."),
) -> None:
    """Batch pre-screen all submission folders under a directory."""
    folders = sorted(
        p for p in submissions_dir.iterdir()
        if p.is_dir() and (p / "Source_Files").is_dir()
    )
    if not folders:
        console.print(f"[red]No submission folders found under {submissions_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"Found [bold]{len(folders)}[/bold] submission(s).")

    from src.workflow.prescreen import prescreen as _prescreen

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_prescreen, f, llm=llm): f for f in folders}
            for future, folder in futures.items():
                try:
                    paper = future.result()
                    _print_one_line(paper)
                except Exception as exc:
                    console.print(f"[red]{folder.name}[/red]: {exc}")
    else:
        for folder in folders:
            try:
                paper = _prescreen(folder, llm=llm)
                _print_one_line(paper)
            except Exception as exc:
                console.print(f"[red]{folder.name}[/red]: {exc}")


def _print_one_line(paper) -> None:
    errors = sum(1 for f in paper.findings if f.severity.value == "error")
    warnings = sum(1 for f in paper.findings if f.severity.value == "warning")
    icon = "🔴" if errors else ("🟡" if warnings else "🟢")
    console.print(
        f"{icon}  [bold]{paper.paper_id}[/bold]  "
        f"errors={errors}  warnings={warnings}"
    )


@app.command()
def report(
    paper_folder: Path = typer.Argument(..., help="Submission folder with an existing prescreen run."),
) -> None:
    """Re-render the report from an existing prescreen run."""
    out_dir = paper_folder / "aiagent_prescreen"
    report_path = out_dir / "report.md"
    if not report_path.exists():
        console.print(f"[red]No report found at {report_path}. Run 'prescreen' first.[/red]")
        raise typer.Exit(1)
    console.print(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    app()
