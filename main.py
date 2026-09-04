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


@app.command("rules")
def rules(
    query: str = typer.Option("", "--query", "-q", help="Text to search across the rule pack."),
    category: str = typer.Option(None, "--category", "-c", help="Filter by rule category."),
    source_format: str = typer.Option(None, "--format", help="Filter by source format: latex or word."),
    version: str = typer.Option(None, "--version", help="Rule-pack version; defaults to latest."),
    as_json: bool = typer.Option(False, "--json", help="Print matching rules as JSON."),
) -> None:
    """Inspect versioned JACoW editorial rules used by the agent."""
    from src.knowledge import agent_context, search_rules

    categories = [category] if category else None
    if as_json:
        import json

        console.print_json(json.dumps(search_rules(
            query,
            categories=categories,
            applies_to=source_format,
            version=version,
        )))
        return
    console.print(agent_context(
        query,
        categories=categories,
        applies_to=source_format,
        version=version,
    ))


@app.command()
def prescreen(
    paper_folder: Path = typer.Argument(..., help="Path to one submission folder."),
    llm: bool = typer.Option(False, "--llm/--no-llm", help="Run local/OpenAI-compatible LLM review."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile", help="Compile edited .tex to PDF."),
    model: str = typer.Option(None, envvar="LLM_MODEL", help="LLM model name."),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL", help="LLM base URL."),
    open_browser: bool = typer.Option(False, "--open", help="Open index.html in browser after run."),
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

    from src.workflow.prescreen import prescreen as _prescreen, WordSubmissionError

    try:
        paper = _prescreen(paper_folder, llm=llm, compile=compile_pdf)
    except WordSubmissionError as exc:
        console.print(f"[yellow]⏭  Skipped (Word):[/yellow] {exc}")
        raise typer.Exit(0)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    is_word_result = hasattr(paper, "total_refs") and not hasattr(paper, "source_path")

    if hasattr(paper, "findings"):
        errors    = sum(1 for f in paper.findings if f.severity.value == "error"   and not f.auto_fixed)
        warnings  = sum(1 for f in paper.findings if f.severity.value == "warning" and not f.auto_fixed)
        auto_fixed = sum(1 for f in paper.findings if f.auto_fixed)
    else:
        errors = 0
        warnings = 0
        auto_fixed = 0

    traffic = "[red]🔴 Needs fixes[/red]" if errors else (
              "[yellow]🟡 Review suggested[/yellow]" if (warnings or auto_fixed) else
              "[green]🟢 Pass[/green]")

    t = Table(title=f"Results — {paper.paper_id}  {traffic}")
    if hasattr(paper, "findings") and not is_word_result:
        t.add_column("Errors",     style="red")
        t.add_column("Warnings",   style="yellow")
        t.add_column("Auto-fixed", style="green")
        t.add_row(str(errors), str(warnings), str(auto_fixed))
        console.print(t)
    else:
        t.add_column("References", style="cyan")
        t.add_column("Output", style="green")
        t.add_row(str(getattr(paper, "total_refs", 0)), "word_references.html")
        console.print(t)

    out_dir = paper_folder / "aiagent_prescreen"
    index   = out_dir / "index.html"
    console.print(f"\nOutputs written to [cyan]{out_dir}[/cyan]")
    if hasattr(paper, "findings") and not is_word_result:
        console.print(f"  [bold]index.html[/bold]   — open in browser for full review")
        console.print(f"  [bold]changes.html[/bold] — side-by-side diff of auto-fixes")
        console.print(f"  [bold]report.md[/bold]    — editor-friendly findings")
        console.print(f"  [bold]repair_plan.json[/bold] — structured repairs and build validation")
        pdf = out_dir / f"{paper.paper_id}_edited.pdf"
        if pdf.exists():
            console.print(f"  [bold green]{pdf.name}[/bold green] — compiled PDF")
        elif compile_pdf:
            console.print(f"  [bold red]PDF compilation failed[/bold red] — see BUILD-FAIL finding")
    else:
        console.print(f"  [bold]word_references.html[/bold] — reference extraction, checks, and before/after corrections")

    if open_browser and index.exists() and not is_word_result:
        import webbrowser
        webbrowser.open(index.as_uri())
    elif open_browser and is_word_result:
        import webbrowser
        webbrowser.open((out_dir / "word_references.html").as_uri())


@app.command("prescreen-all")
def prescreen_all(
    submissions_dir: Path = typer.Argument(..., help="Directory containing all submission folders."),
    llm: bool = typer.Option(False, "--llm/--no-llm", help="Run local/OpenAI-compatible LLM review."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile", help="Compile edited .tex to PDF."),
    workers: int = typer.Option(1, "--workers", "-j", help="Parallel workers."),
    model: str = typer.Option(None, envvar="LLM_MODEL", help="LLM model name."),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL", help="LLM base URL."),
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

    import os

    if model:
        os.environ["LLM_MODEL"] = model
    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    if llm:
        os.environ["LLM_ENABLED"] = "true"

    from src.workflow.prescreen import prescreen as _prescreen, WordSubmissionError

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_prescreen, f, llm=llm, compile=compile_pdf): f for f in folders}
            for future, folder in futures.items():
                try:
                    paper = future.result()
                    _print_one_line(paper)
                except WordSubmissionError as exc:
                    console.print(f"[yellow]⏭  {folder.name}[/yellow]: {exc}")
                except Exception as exc:
                    console.print(f"[red]{folder.name}[/red]: {exc}")
    else:
        for folder in folders:
            try:
                paper = _prescreen(folder, llm=llm, compile=compile_pdf)
                _print_one_line(paper)
            except WordSubmissionError as exc:
                console.print(f"[yellow]⏭  {folder.name}[/yellow]: {exc}")
            except Exception as exc:
                console.print(f"[red]{folder.name}[/red]: {exc}")


def _print_one_line(paper) -> None:
    is_word_result = hasattr(paper, "total_refs") and not hasattr(paper, "source_path")

    if hasattr(paper, "findings") and not is_word_result:
        errors = sum(1 for f in paper.findings if f.severity.value == "error")
        warnings = sum(1 for f in paper.findings if f.severity.value == "warning")
        icon = "🔴" if errors else ("🟡" if warnings else "🟢")
        console.print(
            f"{icon}  [bold]{paper.paper_id}[/bold]  "
            f"errors={errors}  warnings={warnings}"
        )
        return

    if hasattr(paper, "findings") and is_word_result:
        errors = sum(1 for f in paper.findings if f.severity.value == "error" and not f.auto_fixed)
        warnings = sum(1 for f in paper.findings if f.severity.value == "warning" and not f.auto_fixed)
        auto_fixed = sum(1 for f in paper.findings if f.auto_fixed)
        icon = "🔴" if errors else ("🟡" if warnings or auto_fixed else "🟢")
        console.print(
            f"{icon}  [bold]{paper.paper_id}[/bold]  "
            f"errors={errors}  warnings={warnings}  auto_fixed={auto_fixed}  output=word_references.html"
        )
        return

    console.print(
        f"🟦  [bold]{paper.paper_id}[/bold]  "
        f"references={getattr(paper, 'total_refs', 0)}  output=word_references.html"
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
