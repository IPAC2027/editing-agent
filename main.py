"""JACoW conference-paper pre-screening agent — command line.

    desk           open the review desk in a browser (for editors)
    prescreen      screen one submission folder
    prescreen-all  screen every submission under a directory
    apply          apply the edits an editor accepted
    review         open review.html for a screened folder
    rules          inspect the versioned JACoW rule pack

Two audiences, two front doors.

Editors use one command and never see another:

    aiagent desk <folder-of-submissions>

which prepares each paper on demand and opens a browser page where they accept
or reject each change, add problems the agent missed, note why, and close the
paper.  Everything else here is for the people maintaining the tool:

    aiagent prescreen <folder>     # safe changes applied, decisions prepared
    aiagent review <folder>        # list the decisions on the terminal
    aiagent apply <folder> --decisions review_decisions.json
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

app = typer.Typer(
    name="aiagent",
    help="Pre-screening agent for JACoW/IPAC conference paper submissions.",
    add_completion=False,
)
console = Console()


# ---------------------------------------------------------------------------
# Shared presentation
# ---------------------------------------------------------------------------

def _configure_llm(llm: bool | None, model: str | None,
                   base_url: str | None) -> bool:
    """Settle whether a model is in play, and return the answer.

    ``--llm`` / ``--no-llm`` wins; with neither, ``LLM_ENABLED`` from the
    environment or ``.env`` decides.  There is one answer, and every part of a
    run reads it from here: the alternative was a half-on state where the flag
    governed some uses of a model and the environment governed others, so a
    ``.env`` saying ``LLM_ENABLED=true`` bought an editor part of a model
    without saying which part.
    """
    if model:
        os.environ["LLM_MODEL"] = model
    if base_url:
        os.environ["LLM_BASE_URL"] = base_url
    if llm is None:
        from src.llm.client import is_enabled

        return is_enabled()
    os.environ["LLM_ENABLED"] = "true" if llm else "false"
    return llm


def _counts(paper) -> tuple[int, int, int, int]:
    """``(errors, warnings, auto_applied, decisions_pending)``.

    Read from the EditSet, never from a per-finding flag: that is what keeps
    the console, the report and the file on disk in agreement.
    """
    findings = getattr(paper, "findings", [])
    errors = sum(1 for f in findings if f.severity.value == "error")
    warnings = sum(1 for f in findings if f.severity.value == "warning")
    editset = paper.__dict__.get("editset")
    auto = len(editset.auto) if editset else paper.__dict__.get("auto_applied", 0)
    pending = len(editset.suggested) if editset else paper.__dict__.get(
        "decisions_pending", 0
    )
    structural = paper.__dict__.get("structural")
    if structural is not None:
        pending += len(structural.decisions)
    return errors, warnings, auto, pending


def _verdict(errors: int, warnings: int, pending: int) -> str:
    if errors:
        return "[red]needs work[/red]"
    if pending:
        return "[yellow]decisions waiting[/yellow]"
    if warnings:
        return "[yellow]review[/yellow]"
    return "[green]clean[/green]"


def _one_line(paper) -> None:
    errors, warnings, auto, pending = _counts(paper)
    icon = "🔴" if errors else ("🟡" if (pending or warnings) else "🟢")
    console.print(
        f"{icon} [bold]{paper.paper_id:8}[/bold] "
        f"auto={auto:<3} decisions={pending:<3} "
        f"problems={errors:<3} style={warnings}"
    )


# ---------------------------------------------------------------------------
# desk — the editor's front door
# ---------------------------------------------------------------------------

@app.command()
def desk(
    submissions: Path = typer.Argument(
        Path("."), help="Folder holding the submissions (or one submission folder)."),
    port: int = typer.Option(8765, "--port", help="Port to serve on."),
    open_browser: bool = typer.Option(True, "--open/--no-open",
                                      help="Open a browser automatically."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile",
                                     help="Build a PDF when preparing a paper."),
    llm: bool = typer.Option(None, "--llm/--no-llm", help="Use a local model where one is sanctioned (default: LLM_ENABLED in .env)."),
    model: str = typer.Option(None, envvar="LLM_MODEL", help="Model name."),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL", help="Model base URL."),
) -> None:
    """Open the review desk in a browser.

    This is the only command an editor needs.  It serves a page on this
    computer only — nothing is uploaded, nothing is installed, and the
    submissions are never modified.
    """
    from src.desk.server import CONFIG_FILENAME, serve

    llm = _configure_llm(llm, model, base_url)

    root = submissions.expanduser().resolve()
    if not root.is_dir():
        console.print(f"[red]Not a folder:[/red] {root}")
        raise typer.Exit(1)

    # Remember the build preference so the page does not have to ask.
    import json as _json

    config_path = root / CONFIG_FILENAME
    try:
        config = _json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        config = {}
    config["compile"] = compile_pdf
    try:
        config_path.write_text(_json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass

    serve(root, port=port, open_browser=open_browser, llm=llm)


# ---------------------------------------------------------------------------
# indico — the editor's own credential against the editing API
# ---------------------------------------------------------------------------

@app.command()
def indico(
    url: str = typer.Option("https://indico.jacow.org", "--url",
                            envvar="INDICO_URL", help="Indico site."),
    event: int = typer.Option(..., "--event", envvar="INDICO_EVENT",
                              help="Event id, e.g. 82."),
    editable_type: str = typer.Option("paper", "--type", help="paper, slides or poster."),
    show_tags: bool = typer.Option(False, "--tags",
                                   help="List the event's tag vocabulary instead."),
    todo: bool = typer.Option(False, "--todo", help="Only papers with no editor yet."),
) -> None:
    """List a conference's papers from Indico, using your own token.

    Reads only.  The token comes from ``INDICO_TOKEN`` or your OS keyring and is
    never printed.  Create one at ``<indico>/user/tokens/`` with the
    ``read:everything`` scope.
    """
    from src.indico_client.client import IndicoClient, IndicoError, load_token

    try:
        client = IndicoClient(base_url=url, event_id=event,
                              token=load_token(), editable_type=editable_type)
        if show_tags:
            table = Table(title=f"Tag vocabulary — event {event}")
            table.add_column("Code"); table.add_column("Used"); table.add_column("Title")
            for tag in client.tags():
                table.add_row(tag.code, "yes" if tag.is_used_in_revision else "",
                              tag.title[:78])
            console.print(table)
            return

        rows = client.list_editables()
    except IndicoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    submitted = [r for r in rows if r.submitted]
    if todo:
        submitted = [r for r in submitted if not r.editor_name]

    table = Table(title=f"Event {event} — {len(submitted)} of {len(rows)} submitted")
    table.add_column("Paper"); table.add_column("Title", max_width=48)
    table.add_column("Rev", justify="right"); table.add_column("Status")
    table.add_column("Editor"); table.add_column("Tags")
    for row in submitted:
        table.add_row(row.label, row.title, str(row.editable.revision_count),
                      row.state.replace("_", " "), row.editor_name,
                      " ".join(row.tag_codes))
    console.print(table)
    not_submitted = len(rows) - len([r for r in rows if r.submitted])
    if not_submitted:
        console.print(f"[dim]{not_submitted} contribution(s) with nothing "
                      f"submitted yet.[/dim]")


# ---------------------------------------------------------------------------
# prescreen
# ---------------------------------------------------------------------------

@app.command()
def prescreen(
    paper_folder: Path = typer.Argument(..., help="Path to one submission folder."),
    llm: bool = typer.Option(None, "--llm/--no-llm", help="Use a local model where one is sanctioned (default: LLM_ENABLED in .env)."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile",
                                     help="Compile the edited source as proof it builds."),
    git: bool = typer.Option(True, "--git/--no-git",
                             help="Write a git history with one commit per edit."),
    model: str = typer.Option(None, envvar="LLM_MODEL", help="Model name."),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL", help="Model base URL."),
    open_browser: bool = typer.Option(False, "--open", help="Open review.html when done."),
) -> None:
    """Pre-screen a single submission folder."""
    llm = _configure_llm(llm, model, base_url)

    if not paper_folder.is_dir():
        console.print(f"[red]Not a directory:[/red] {paper_folder}")
        raise typer.Exit(1)

    console.print(f"[bold]Pre-screening[/bold] {paper_folder.name}")

    from src.workflow.prescreen import WordSubmissionError
    from src.workflow.prescreen import prescreen as run

    try:
        paper = run(paper_folder, llm=llm, compile=compile_pdf, git=git)
    except WordSubmissionError as exc:
        console.print(f"[yellow]Skipped (Word):[/yellow] {exc}")
        raise typer.Exit(0)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    out_dir = paper_folder / "aiagent_prescreen"
    is_word = hasattr(paper, "total_refs") and not hasattr(paper, "source_path")

    if is_word:
        _report_word(paper, out_dir, open_browser)
        return

    errors, warnings, auto, pending = _counts(paper)
    table = Table(title=f"{paper.paper_id} — {_verdict(errors, warnings, pending)}",
                  title_justify="left")
    table.add_column("Applied automatically", style="cyan", justify="right")
    table.add_column("Awaiting decision", style="yellow", justify="right")
    table.add_column("Needs a human", style="red", justify="right")
    table.add_column("Style points", style="magenta", justify="right")
    table.add_row(str(auto), str(pending), str(errors), str(warnings))
    console.print(table)

    console.print(f"\nOutputs in [cyan]{out_dir}[/cyan]")
    console.print(f"  [bold]review.html[/bold]        {pending} accept/reject decision(s)")
    console.print(f"  [bold]{paper.paper_id}_edited.tex[/bold]  the {auto} automatic change(s), already applied")
    console.print("  [bold]edits/[/bold]             one applicable patch per edit")
    if (out_dir / "history").exists():
        console.print("  [bold]history/[/bold]           git repo, one commit per edit")
    console.print("  [bold]report.md[/bold]          findings, and which checks did not run")

    if pending:
        console.print(
            f"\nNext: [bold]aiagent review {paper_folder}[/bold] then "
            f"[bold]aiagent apply {paper_folder} --decisions review_decisions.json[/bold]"
        )

    if open_browser:
        _open(out_dir / "review.html")


def _report_word(paper, out_dir: Path, open_browser: bool) -> None:
    tracked = getattr(paper, "tracked_docx", None)
    revisions = getattr(paper, "revisions", 0)
    table = Table(title=f"{paper.paper_id} — Word submission", title_justify="left")
    table.add_column("References", justify="right")
    table.add_column("Tracked changes", justify="right", style="cyan")
    table.add_column("Needs a human", justify="right", style="red")
    errors = sum(1 for f in getattr(paper, "findings", []) if f.severity.value == "error")
    table.add_row(str(getattr(paper, "total_refs", 0)), str(revisions), str(errors))
    console.print(table)
    console.print(f"\nOutputs in [cyan]{out_dir}[/cyan]")
    if tracked:
        console.print(
            f"  [bold green]{tracked}[/bold green]  open in Word and use "
            "Review → Accept / Reject on each change"
        )
    console.print("  [bold]word_references.html[/bold]  the same changes as a web page")
    console.print("  [bold]report.md[/bold]             findings")
    if open_browser:
        _open(out_dir / "word_references.html")


# ---------------------------------------------------------------------------
# prescreen-all
# ---------------------------------------------------------------------------

@app.command("prescreen-all")
def prescreen_all(
    submissions_dir: Path = typer.Argument(..., help="Directory of submission folders."),
    llm: bool = typer.Option(None, "--llm/--no-llm", help="Use a local model where one is sanctioned (default: LLM_ENABLED in .env)."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile"),
    git: bool = typer.Option(True, "--git/--no-git"),
    workers: int = typer.Option(1, "--workers", "-j", help="Parallel workers."),
    model: str = typer.Option(None, envvar="LLM_MODEL"),
    base_url: str = typer.Option(None, envvar="LLM_BASE_URL"),
) -> None:
    """Pre-screen every submission folder under a directory."""
    folders = sorted(
        p for p in submissions_dir.iterdir()
        if p.is_dir() and (p / "Source_Files").is_dir()
    )
    if not folders:
        console.print(f"[red]No submission folders under {submissions_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"Found [bold]{len(folders)}[/bold] submission(s).\n")
    llm = _configure_llm(llm, model, base_url)

    from src.workflow.prescreen import WordSubmissionError
    from src.workflow.prescreen import prescreen as run

    totals = {"auto": 0, "pending": 0, "errors": 0, "papers": 0}

    def _record(paper) -> None:
        errors, _warnings, auto, pending = _counts(paper)
        totals["auto"] += auto
        totals["pending"] += pending
        totals["errors"] += errors
        totals["papers"] += 1
        _one_line(paper)

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run, folder, llm=llm, compile=compile_pdf, git=git): folder
                for folder in folders
            }
            for future in as_completed(futures):
                folder = futures[future]
                try:
                    _record(future.result())
                except WordSubmissionError as exc:
                    console.print(f"⏭  [yellow]{folder.name}[/yellow]: {exc}")
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]{folder.name}[/red]: {exc}")
    else:
        for folder in folders:
            try:
                _record(run(folder, llm=llm, compile=compile_pdf, git=git))
            except WordSubmissionError as exc:
                console.print(f"⏭  [yellow]{folder.name}[/yellow]: {exc}")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]{folder.name}[/red]: {exc}")

    if totals["papers"]:
        console.print(
            f"\n[bold]{totals['papers']}[/bold] papers · "
            f"[cyan]{totals['auto']}[/cyan] changes applied automatically · "
            f"[yellow]{totals['pending']}[/yellow] decisions waiting · "
            f"[red]{totals['errors']}[/red] problems needing a human "
            f"({totals['pending'] / totals['papers']:.1f} decisions per paper)"
        )


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

@app.command()
def apply(
    paper_folder: Path = typer.Argument(..., help="A folder that has been pre-screened."),
    accept: str = typer.Option("", "--accept", help="Comma-separated edit ids to accept."),
    reject: str = typer.Option("", "--reject", help="Comma-separated edit ids to reject."),
    decisions: Path = typer.Option(None, "--decisions",
                                   help="review_decisions.json saved from review.html."),
    in_place: bool = typer.Option(False, "--in-place",
                                  help="Overwrite the author's .tex instead of writing a copy."),
    compile_pdf: bool = typer.Option(True, "--compile/--no-compile"),
) -> None:
    """Apply the edits an editor accepted.

    With no options this applies the AUTO tier only. ``--accept`` adds specific
    edits, ``--reject`` removes them, and ``--decisions`` reads the file
    ``review.html`` saves. Every edit is verified against the current source
    before anything is written, so a source the author has revised in the
    meantime produces a conflict rather than a scrambled file.
    """
    from src.edits import EditConflict
    from src.workflow.prescreen import apply_decisions

    def _ids(raw: str) -> list[str]:
        return [part.strip().upper() for part in raw.split(",") if part.strip()]

    try:
        target, applied, unknown = apply_decisions(
            paper_folder,
            accept=_ids(accept),
            reject=_ids(reject),
            decisions_path=decisions,
            write_to_source=in_place,
            compile=compile_pdf,
        )
    except EditConflict as exc:
        console.print(f"[red]Conflict:[/red] {exc}")
        console.print("Re-run [bold]prescreen[/bold] on this folder to recompute the edits.")
        raise typer.Exit(2)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if unknown:
        console.print(f"[yellow]Ignored unknown edit id(s):[/yellow] {', '.join(unknown)}")

    console.print(
        f"[green]Applied {len(applied)} edit(s)[/green] → [cyan]{target}[/cyan]"
    )
    if applied:
        console.print("  " + ", ".join(applied))
    if in_place:
        console.print(
            "[yellow]The author's source was overwritten.[/yellow] "
            "The original is the first commit in aiagent_prescreen/history/."
        )


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

@app.command()
def review(
    paper_folder: Path = typer.Argument(..., help="A folder that has been pre-screened."),
    show: bool = typer.Option(False, "--show", help="Print the decisions to the terminal."),
) -> None:
    """Open (or print) the accept/reject review for a screened folder."""
    out_dir = paper_folder / "aiagent_prescreen"
    review_path = out_dir / "review.html"
    if not review_path.exists():
        console.print(f"[red]No review at {review_path}.[/red] Run 'prescreen' first.")
        raise typer.Exit(1)

    if show:
        from src.edits import EditSet

        from src.autofix.structural import StructuralPlan

        editset = EditSet.read(out_dir / "edits.json")
        structural_path = out_dir / "structural.json"
        plan = StructuralPlan.read(structural_path) if structural_path.exists() else None
        table = Table(title=f"{paper_folder.name} — edits", title_justify="left")
        table.add_column("Id")
        table.add_column("Tier")
        table.add_column("Check")
        table.add_column("Line", justify="right")
        table.add_column("Change")
        for edit in editset.edits:
            table.add_row(
                edit.id,
                ("[cyan]auto[/cyan]" if edit.tier.value == "auto"
                 else "[yellow]decide[/yellow]"),
                edit.check_id,
                str(edit.line),
                edit.short(58),
            )
        for decision in (plan.decisions if plan else []):
            table.add_row(
                decision.id, "[yellow]decide[/yellow]", decision.check_id, "—",
                decision.message[:58],
            )
        console.print(table)
        return

    _open(review_path)
    console.print(f"Opened [cyan]{review_path}[/cyan]")


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

@app.command("rules")
def rules(
    query: str = typer.Option("", "--query", "-q", help="Text to search the rule pack."),
    category: str = typer.Option(None, "--category", "-c", help="Filter by category."),
    source_format: str = typer.Option(None, "--format", help="latex or word."),
    version: str = typer.Option(None, "--version", help="Rule-pack version."),
    as_json: bool = typer.Option(False, "--json", help="Print matching rules as JSON."),
) -> None:
    """Inspect the versioned JACoW editorial rules the agent applies."""
    from src.knowledge import agent_context, search_rules

    categories = [category] if category else None
    if as_json:
        import json

        console.print_json(json.dumps(search_rules(
            query, categories=categories, applies_to=source_format, version=version,
        )))
        return
    console.print(agent_context(
        query, categories=categories, applies_to=source_format, version=version,
    ))


@app.command()
def report(
    paper_folder: Path = typer.Argument(..., help="A folder that has been pre-screened."),
) -> None:
    """Print report.md from an existing prescreen run."""
    path = paper_folder / "aiagent_prescreen" / "report.md"
    if not path.exists():
        console.print(f"[red]No report at {path}.[/red] Run 'prescreen' first.")
        raise typer.Exit(1)
    console.print(path.read_text(encoding="utf-8"))


def _open(path: Path) -> None:
    if not path.exists():
        console.print(f"[yellow]Nothing to open at {path}[/yellow]")
        return
    import webbrowser

    webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    app()
