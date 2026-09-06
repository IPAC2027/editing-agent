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


@app.command("indico-pull")
def indico_pull(
    destination: Path = typer.Argument(..., help="Folder to write the conference into."),
    url: str = typer.Option("https://indico.jacow.org", "--url", envvar="INDICO_URL"),
    event: int = typer.Option(..., "--event", envvar="INDICO_EVENT"),
    editable_type: str = typer.Option("paper", "--type"),
    which: str = typer.Option("first-last", "--revisions",
                              help="first-last, latest or all."),
    only: str = typer.Option("", "--only",
                             help="Comma-separated paper codes, e.g. MOX01,TUZ02."),
    dry_run: bool = typer.Option(False, "--dry-run",
                                 help="Say what would be fetched and how big it is."),
) -> None:
    """Download a conference from Indico for study. Reads only; writes nothing.

    Fetches the author's first revision and the current one for every paper, with
    a manifest carrying the editors' tags — the labels for what changed between
    them.  The client refuses any request that is not a GET.
    """
    from src.indico_client.client import IndicoClient, IndicoError, load_token
    from src.indico_client.pull import build_plan, _human, pull

    codes = {c.strip() for c in only.split(",") if c.strip()} or None
    try:
        client = IndicoClient(base_url=url, event_id=event, token=load_token(),
                              editable_type=editable_type, read_only=True)
        console.print(f"[dim]Reading event {event}…[/dim]")
        plan = build_plan(client, which=which, only=codes)
    except IndicoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{plan.summary()}[/bold]")
    if dry_run:
        table = Table(title="What would be downloaded")
        table.add_column("Paper"); table.add_column("Revisions")
        table.add_column("Size", justify="right"); table.add_column("Tags")
        for paper in plan.papers[:400]:
            table.add_row(
                paper.folder,
                ", ".join(r.role for r in paper.revisions) or f"[dim]{paper.note}[/dim]",
                _human(paper.bytes) if paper.revisions else "",
                " ".join(paper.row.tag_codes))
        console.print(table)
        console.print("[dim]Nothing was downloaded. Drop --dry-run to fetch.[/dim]")
        return

    def _progress(index: int, total: int, paper) -> None:
        console.print(f"  [{index}/{total}] {paper.folder} "
                      f"[dim]{_human(paper.bytes)}[/dim]")

    try:
        pull(client, destination, which=which, only=codes, plan=plan,
             on_paper=_progress)
    except IndicoError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("[dim]Already-downloaded files are kept; run again to "
                      "resume.[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[green]Done.[/green] {destination}")
    console.print("[dim]index.json lists every paper; each folder has a "
                  "manifest.json with the editors' tags.[/dim]")


@app.command()
def corpus(
    folder: Path = typer.Argument(..., help="A conference pulled with indico-pull."),
    save: bool = typer.Option(True, "--save/--no-save",
                              help="Write corpus_report.json beside the papers."),
    limit: int = typer.Option(0, "--papers", help="Also list this many papers."),
) -> None:
    """Describe a pulled conference: what is usable, in what format, and what
    the editors actually spend their time on.

    Reads the folder only.  Nothing is sent anywhere, and no paper is modified.
    """
    from src.corpus.index import PAIRED, build_index

    try:
        index = build_index(folder)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if not index.papers:
        console.print(f"[yellow]No paper folders with a manifest under {folder}."
                      "[/yellow]  Is this a folder written by `indico-pull`?")
        raise typer.Exit(1)

    total = len(index.papers)
    usable, teachable = len(index.usable), len(index.teachable)

    console.print(f"\n[bold]{folder}[/bold]"
                  + (f"  ·  event {index.event_id}" if index.event_id else ""))

    status = Table(title=f"{total} paper(s)")
    status.add_column("What"); status.add_column("Papers", justify="right")
    status.add_column("", style="dim")
    labels = {
        PAIRED: "both revisions, and they differ",
        "unchanged": "both revisions, identical — nothing was edited",
        "single-revision": "submitted once, never edited",
        "not-submitted": "nothing submitted",
        "no-files": "revisions carry no files",
    }
    for key, count in index.by_status().most_common():
        status.add_row(key, str(count), labels.get(key, ""))
    console.print(status)

    console.print(f"[bold]{teachable}[/bold] of {usable} usable pair(s) have a "
                  f"changed document rather than only changed figures — "
                  f"[bold]that is the sample size that matters[/bold].")

    fmt = Table(title="Format of what the author submitted")
    fmt.add_column("Format"); fmt.add_column("All", justify="right")
    fmt.add_column("Usable pairs", justify="right")
    usable_formats = index.by_format(index.usable)
    for name, count in index.by_format().most_common():
        fmt.add_row(name, str(count), str(usable_formats.get(name, 0)))
    console.print(fmt)

    rows = index.tag_rows(index.usable)
    if rows:
        tags = Table(title="What the editors corrected, on the usable pairs")
        tags.add_column("Code"); tags.add_column("Papers", justify="right")
        tags.add_column("Share", justify="right"); tags.add_column("Agent")
        tags.add_column("What it means", max_width=52)
        style = {"agent proposes this": "green", "NOT IMPLEMENTED": "yellow",
                 "out of reach": "dim", "editing service": "dim"}
        for row in rows:
            colour = style.get(row["coverage"], "")
            tags.add_row(row["code"], str(row["papers"]),
                         f"{row['share'] * 100:.0f}%",
                         f"[{colour}]{row['coverage']}[/{colour}]" if colour
                         else row["coverage"],
                         row["title"])
        console.print(tags)

        gaps = [r for r in rows if r["coverage"] == "NOT IMPLEMENTED"]
        if gaps:
            console.print("[yellow]Worth building next[/yellow] — frequent, and "
                          "needs no PDF: "
                          + ", ".join(f"{g['code']} ({g['papers']})" for g in gaps))
    else:
        console.print("[dim]No tags on the usable pairs.[/dim]")

    if limit:
        listing = Table(title=f"First {limit} paper(s)")
        listing.add_column("Paper"); listing.add_column("Format")
        listing.add_column("Status"); listing.add_column("Changed files",
                                                         justify="right")
        listing.add_column("Tags")
        for paper in index.papers[:limit]:
            listing.add_row(paper.code, paper.fmt, paper.status,
                            str(len(paper.changed_files)), " ".join(paper.tags))
        console.print(listing)

    if save:
        import json as _json

        out = folder / "corpus_report.json"
        out.write_text(_json.dumps(index.to_dict(), indent=2, ensure_ascii=False),
                       encoding="utf-8")
        console.print(f"[dim]Written {out}[/dim]")


@app.command()
def corpus(
    folder: Path = typer.Argument(..., help="A conference pulled by 'indico-pull'."),
    usable_only: bool = typer.Option(False, "--usable-only",
                                     help="Count tags only on pairs we can learn from."),
    show_papers: bool = typer.Option(False, "--papers", help="List every paper."),
) -> None:
    """Describe a pulled conference: what can be learned from it, and what cannot.

    Runs no checks and scores nothing.  It answers how many papers give a real
    before/after pair, in what format, and what the editors said was wrong —
    joined with whether this agent can propose the same thing.
    """
    from src.corpus.index import load, measurable_sample, summary, tag_report

    try:
        data = load(folder)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{summary(data)}[/bold]\n")

    sizes = Table(title="How much evidence there is")
    sizes.add_column("Checks"); sizes.add_column("Pairs to score on", justify="right")
    for label, count in measurable_sample(data).items():
        sizes.add_row(label, str(count))
    console.print(sizes)

    reasons = data.reasons()
    if reasons:
        skipped = Table(title="Why the rest cannot be used")
        skipped.add_column("Reason"); skipped.add_column("Papers", justify="right")
        for reason, count in reasons.most_common():
            skipped.add_row(reason, str(count))
        console.print(skipped)

    tags = Table(title="What the editors corrected"
                       + (" (usable pairs only)" if usable_only else ""))
    tags.add_column("Tag"); tags.add_column("Papers", justify="right")
    tags.add_column("Us"); tags.add_column("What it means", max_width=44)
    tags.add_column("Detail", max_width=40)
    from rich.markup import escape as _escape

    for row in tag_report(data, usable_only=usable_only):
        tags.add_row(row.code, str(row.papers), row.status,
                     _escape(row.title), _escape(row.detail))
    console.print(tags)

    if show_papers:
        listing = Table(title="Papers")
        listing.add_column("Paper"); listing.add_column("Format")
        listing.add_column("Usable"); listing.add_column("Tags")
        for paper in data.papers:
            usable, reason = paper.usability()
            listing.add_row(paper.code, paper.kind,
                            "yes" if usable else f"[dim]{reason}[/dim]",
                            " ".join(paper.tags))
        console.print(listing)


@app.command("corpus-diff")
def corpus_diff(
    folder: Path = typer.Argument(..., help="A conference pulled by 'indico-pull'."),
    top: int = typer.Option(25, "--top", help="How many recurring corrections to show."),
    only: str = typer.Option("", "--only", help="Comma-separated paper codes."),
) -> None:
    """Extract what the editors actually changed, paper by paper.

    Writes one json per paper into ``<folder>/_diffs`` and prints the
    corrections that recur most often across the conference — which is where
    candidate new checks come from.
    """
    from collections import Counter

    from rich.markup import escape

    from src.corpus.diff import diff_paper, write
    from src.corpus.index import load

    try:
        data = load(folder)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    codes = {c.strip() for c in only.split(",") if c.strip()}
    papers = [p for p in data.usable if not codes or p.code in codes]
    if not papers:
        console.print("[yellow]No usable pairs to diff.[/yellow]")
        raise typer.Exit(1)

    diffs = [diff_paper(p) for p in papers]
    out = write(diffs, folder / "_diffs")

    total = sum(len(d.hunks) for d in diffs)
    small = sum(len(d.small) for d in diffs)
    per_paper = sorted(len(d.small) for d in diffs)

    shape = Table(title="What the editors changed")
    shape.add_column("Measure"); shape.add_column("Value", justify="right")
    shape.add_row("papers compared", str(len(diffs)))
    shape.add_row("corrections found", str(small))
    shape.add_row("whole-paragraph rewrites (excluded)", str(total - small))
    shape.add_row("median corrections per paper",
                  str(per_paper[len(per_paper) // 2]) if per_paper else "0")
    by_source = Counter(h.source for d in diffs for h in d.small)
    for source, count in by_source.most_common():
        shape.add_row(f"  from {source}", str(count))
    console.print(shape)

    notes = Counter(d.note for d in diffs if d.note)
    if notes:
        skipped = Table(title="Papers that yielded nothing")
        skipped.add_column("Reason"); skipped.add_column("Papers", justify="right")
        for note, count in notes.most_common():
            skipped.add_row(escape(note), str(count))
        console.print(skipped)

    recurring = Counter(h.signature for d in diffs for h in d.small)
    table = Table(title=f"The {top} most repeated corrections "
                        "(digits shown as #)")
    table.add_column("Times", justify="right"); table.add_column("Correction")
    for signature, count in recurring.most_common(top):
        # LaTeX is full of [!htb] and [width=...]; Rich would read those as
        # markup and silently render the row blank.
        table.add_row(str(count), escape(signature))
    console.print(table)
    console.print(f"[dim]{out}[/dim]")


@app.command("corpus-score")
def corpus_score(
    folder: Path = typer.Argument(..., help="A conference pulled by 'indico-pull'."),
    top: int = typer.Option(20, "--top", help="How many missed corrections to list."),
    only: str = typer.Option("", "--only", help="Comma-separated paper codes."),
) -> None:
    """Score the agent's proposals against what the editors actually did.

    Screens every author revision in the corpus and looks for each proposed
    edit in the editors' real diff.  Reports confirmed, contradicted and
    unconfirmed per check — and unconfirmed is not evidence of error.
    """
    from rich.markup import escape

    from src.corpus.diff import diff_paper
    from src.corpus.index import load
    from src.corpus.score import by_check, missed_signatures, score_paper, totals

    try:
        data = load(folder)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    codes = {c.strip() for c in only.split(",") if c.strip()}
    papers = [p for p in data.usable if not codes or p.code in codes]
    if not papers:
        console.print("[yellow]No usable pairs to score.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[dim]Screening {len(papers)} paper(s)…[/dim]")
    scores = [score_paper(p, diff_paper(p)) for p in papers]

    shape = Table(title="Overall")
    shape.add_column("Measure"); shape.add_column("Value", justify="right")
    for label, value in totals(scores).items():
        shape.add_row(label, str(value))
    console.print(shape)

    checks = Table(title="Per check — against what the editors really did")
    checks.add_column("Check"); checks.add_column("Tier")
    checks.add_column("Proposed", justify="right")
    checks.add_column("Confirmed", justify="right")
    checks.add_column("Contradicted", justify="right")
    checks.add_column("Papers", justify="right"); checks.add_column("Verdict")
    for score in by_check(scores):
        checks.add_row(score.check_id, score.tier, str(score.proposals),
                       f"{score.confirmed} ({score.rate:.0%})",
                       str(score.contradicted) or "", str(len(score.papers)),
                       escape(score.verdict))
    console.print(checks)

    disagreements = [(c, e) for c in by_check(scores) for e in c.examples]
    if disagreements:
        table = Table(title="Where the editors did something else "
                            "(the strongest evidence against a rule)")
        table.add_column("Check"); table.add_column("What happened", max_width=88)
        for check, example in disagreements:
            table.add_row(check.check_id, escape(example))
        console.print(table)

    missed = Table(title=f"The {top} most common corrections nothing proposed")
    missed.add_column("Times", justify="right"); missed.add_column("Correction")
    for signature, count in missed_signatures(scores, top=top):
        missed.add_row(str(count), escape(signature))
    console.print(missed)

    failed = [s for s in scores if s.error]
    if failed:
        console.print(f"[yellow]{len(failed)} paper(s) could not be "
                      f"screened:[/yellow]")
        for score in failed[:8]:
            console.print(f"  {score.paper}: {escape(score.error[:100])}")


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
