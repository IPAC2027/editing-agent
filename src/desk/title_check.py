"""The title and author check, as the desk runs it.

:mod:`src.checks.title_authors` says whether a paper and its Indico record
agree. This module turns a disagreement into the editor's next steps:

1. **Write to the author.** The email names each difference and says exactly
   what will change if nobody answers within 48 hours: Indico's title becomes
   the paper's, and the author list becomes the combined list.
2. **Wait.** The editor sends it — as an Indico comment or by mail; the desk
   sends nothing — and says so. The deadline the desk keeps is never earlier
   than the one the author read: the email prints 48 hours from when it is
   drafted, rounded up to the hour, and the desk counts from when the editor
   marks it sent, which can only be later.
3. **Apply what was promised**, when the deadline passes with no reply or at
   once if the author agrees. The paper's side — authors Indico has and the
   paper lacks — goes into the reviewed files, as a Word tracked change or a
   LaTeX edit, reversible like any other correction. Indico's side — its title,
   and authors the paper has and Indico lacks — becomes a checklist, because
   the desk does not write to Indico.

The plan is frozen when the email is sent. If the paper or Indico changes
afterwards (the author fixed Indico, or the authors were fetched with their
roles), the desk says so rather than apply a change nobody needs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.checks.title_authors import (
    FRONT_MATTER_VERSION,
    Comparison,
    FrontMatter,
    IndicoRecord,
    compare,
    front_matter_of,
)
from src.desk import files
from src.desk.state import ReviewState, TitleAuthorState

GRACE = timedelta(hours=48)
FRONT_CACHE = "front_matter.json"

#: The check's verdict, in the words the desk shows.  "match" is the check
#: passing; "differs" is it failing, with the email to the author drafted.
STATUS_WORDS = {
    "unknown": "Not checked",
    "match": "Author/title check done",
    "differs": "Needs correction: email drafted",
    "waiting": "Waiting for the author",
    "due": "No reply: ready to apply",
    "applied": "Corrected; Indico changes to make",
    "done": "Author/title check done (corrected)",
    "replied": "Author replied",
    "changed": "Changed since the email",
}


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def deadline_from(moment: datetime) -> datetime:
    """48 hours after *moment*, rounded up to the hour."""
    later = moment.astimezone(timezone.utc) + GRACE
    rounded = later.replace(minute=0, second=0, microsecond=0)
    return rounded if rounded == later else rounded + timedelta(hours=1)


def deadline_text(moment: datetime) -> str:
    """ "Wednesday 4 November 2026, 11:00 UTC" — authors are everywhere."""
    utc = moment.astimezone(timezone.utc)
    return f"{utc:%A} {utc.day} {utc:%B %Y, %H:%M} UTC"


# ---------------------------------------------------------------------------
# What differs, and what would change
# ---------------------------------------------------------------------------

def front_for(folder: Path, report: dict) -> FrontMatter | None:
    """The paper's title and authors, as its report recorded them.

    A paper prepared before reports carried them, or read by an older version
    of the check, is read from its source once and remembered beside the
    report — never taken from the report's old author list, which lost every
    author after the first line of the author block.
    """
    stored = report.get("front_matter")
    if stored and stored.get("version") == FRONT_MATTER_VERSION:
        return FrontMatter.model_validate(stored)
    # Found from whichever computer prepared the paper: reports record the
    # source relative to the paper now, older ones an absolute path.
    source = files.source_file(folder, report.get("source"))
    if source is None:
        return None
    cache = folder / "aiagent_prescreen" / FRONT_CACHE
    stamp = source.stat().st_mtime
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if (cached.get("source_mtime") == stamp
                and cached["front_matter"].get("version") == FRONT_MATTER_VERSION):
            return FrontMatter.model_validate(cached["front_matter"])
    except Exception:  # noqa: BLE001 — no cache, or a stale one: read the source
        pass
    try:
        front = front_matter_of(source)
    except Exception:  # noqa: BLE001 — an unreadable source is "cannot compare"
        return None
    if front is not None:
        try:
            files.write_text(cache, json.dumps({"source_mtime": stamp,
                                                "front_matter": front.model_dump()}))
        except OSError:
            pass
    return front


def comparison_for(front: FrontMatter | None, record: IndicoRecord | None) -> Comparison | None:
    if front is None or record is None:
        return None
    return compare(front, record)


def plan_of(comparison: Comparison) -> dict:
    """What will change if the author does not answer."""
    title = None
    if comparison.title_differs:
        title = {"paper": comparison.paper_title, "indico": comparison.indico_title,
                 "new_indico": comparison.proposed_indico_title,
                 "check_capitals": comparison.check_capitals}
    return {
        "title": title,
        "add_to_paper": [{"name": p.jacow, "affiliation": p.affiliation}
                         for p in comparison.indico_only],
        "add_to_indico": list(comparison.paper_only),
        "combined": list(comparison.combined),
        # The paper as it will be published if nobody objects.
        "final_title": (comparison.proposed_indico_title if comparison.title_differs
                        else comparison.paper_title),
    }


def _essence(plan: dict) -> tuple:
    title = (plan.get("title") or {}).get("new_indico", "")
    return (title, sorted(p["name"] for p in plan.get("add_to_paper", [])),
            sorted(plan.get("add_to_indico", [])))


def status_of(comparison: Comparison | None, ta: TitleAuthorState,
              now: datetime | None = None) -> str:
    now = now or _now()
    if ta.applied_at:
        tasks = indico_tasks(ta.plan, ta)
        return "done" if all(t["done"] for t in tasks) else "applied"
    if ta.reply == "declined":
        return "replied"
    if ta.sent_at:
        if comparison is not None and _essence(plan_of(comparison)) != _essence(ta.plan):
            return "changed"
        deadline = _parse(ta.deadline)
        return "due" if deadline and now >= deadline else "waiting"
    if comparison is None:
        return "unknown"
    if comparison.differs:
        return "differs"
    return "unknown" if comparison.unreadable else "match"


# ---------------------------------------------------------------------------
# The email
# ---------------------------------------------------------------------------

def _with_affiliation(person: dict) -> str:
    return f"{person['name']} ({person['affiliation']})" if person.get("affiliation") \
        else person["name"]


def email_text(*, paper_id: str, event: str, plan: dict, deadline: datetime,
               editor: str, title: str = "") -> str:
    """The email to the author: what differs, and what happens if they do not answer."""
    when = deadline_text(deadline)
    short = f"{deadline.astimezone(timezone.utc):%d %b %H:%M} UTC"
    lines = [f"Subject: {event} {paper_id}: title and author list differ from "
             f"Indico (please reply by {short})", "", "Dear author,", ""]
    opening = f"Thank you for your paper {paper_id}"
    if title:
        opening += f", \u201c{title}\u201d"
    lines += [opening + f", submitted to {event}.", "",
              "Before the proceedings are published we compare each paper's title "
              "and author list with its record in Indico, which is what the table of "
              "contents, the author index and the DOI metadata are built from. For "
              "your paper they differ.", ""]

    changed_title = plan.get("title")
    to_paper = plan.get("add_to_paper", [])
    to_indico = plan.get("add_to_indico", [])

    lines.append("What does not match")
    if changed_title:
        lines += ["  - The title.",
                  f"      In your paper: {changed_title['paper']}",
                  f"      In Indico:     {changed_title['indico']}"]
    for name in to_indico:
        lines.append(f"  - {name} is an author in your paper but not in Indico.")
    for one in to_paper:
        lines.append(f"  - {_with_affiliation(one)} is an author in Indico but not "
                     "in your paper.")
    lines.append("")

    lines += [f"If we have not heard from you by {when}, we will correct this, and "
              "your paper will be published with:", ""]
    if plan.get("final_title"):
        lines.append(f"  Title:   {plan['final_title']}")
    if plan.get("combined"):
        lines.append("  Authors: " + ", ".join(plan["combined"]))
    lines += ["", "To get there:"]
    if changed_title:
        lines.append("  - in Indico, the title will be changed to the title of your paper;")
    if to_indico:
        lines.append(f"  - in Indico, {', '.join(to_indico)} will be added to the authors;")
    if to_paper:
        lines.append("  - in your paper, " + ", ".join(_with_affiliation(p) for p in to_paper)
                     + " will be added to the author list.")
    lines += ["",
              "If any of this is wrong (for example, if someone listed in Indico is "
              "not an author of this paper, or your paper's title is not the one you "
              "want), please reply before then, or upload a corrected paper, and we "
              "will follow your correction instead.", "",
              "With thanks,", editor or "The editorial team"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# For the desk
# ---------------------------------------------------------------------------

def indico_tasks(plan: dict, ta: TitleAuthorState) -> list[dict]:
    """What the editor still has to change in Indico, by hand."""
    tasks: list[dict] = []
    if plan.get("title"):
        text = f"Change the title in Indico to \u201c{plan['title']['new_indico']}\u201d"
        if plan["title"].get("check_capitals"):
            text += " (check its capitals: the paper writes it in capitals)"
        tasks.append({"key": "title", "text": text})
    for name in plan.get("add_to_indico", []):
        tasks.append({"key": f"author:{name}", "text": f"Add {name} to the authors in Indico"})
    for task in tasks:
        task["done"] = bool(ta.indico_done.get(task["key"]))
    return tasks


def view(*, front: FrontMatter | None, prepared: bool, state: ReviewState,
         record: IndicoRecord | None, paper_id: str, event: str, indico_url: str = "",
         now: datetime | None = None) -> dict | None:
    """The "Title & authors" panel, or ``None`` for a paper Indico does not know."""
    if record is None:
        return None
    now = now or _now()
    ta = state.title_authors
    comparison = comparison_for(front, record)
    status = status_of(comparison, ta, now)
    plan = ta.plan if ta.sent_at else (
        plan_of(comparison) if comparison and comparison.differs else {})
    deadline = _parse(ta.deadline) if ta.sent_at else deadline_from(now)

    email = ""
    if plan:
        email = ta.email_override or email_text(
            paper_id=paper_id, event=event, plan=plan, deadline=deadline,
            editor=state.editor, title=(comparison.paper_title if comparison else ""))

    shown = None
    if comparison is not None:
        shown = comparison.model_dump()
        shown["indico_only"] = [{**p.model_dump(), "jacow": p.jacow}
                                for p in comparison.indico_only]
    return {
        "status": status,
        "status_word": STATUS_WORDS[status],
        "comparison": shown,
        "why_not": ("" if front is not None
                    else "The desk could not read this paper's title and authors."
                    if prepared else "Prepare this paper so the desk can read its title "
                    "and authors."),
        "roles_known": record.roles_known,
        "as_of": record.as_of,
        "plan": plan,
        "email": email,
        "email_edited": bool(ta.email_override),
        "sent_at": ta.sent_at,
        "deadline": _iso(deadline) if deadline else "",
        "deadline_text": deadline_text(deadline) if deadline else "",
        "reply": ta.reply,
        "applied_at": ta.applied_at,
        "indico_tasks": indico_tasks(plan, ta) if ta.applied_at else [],
        "indico_url": indico_url,
    }


def summary(front: FrontMatter | None, state: ReviewState, record: IndicoRecord | None,
            now: datetime | None = None) -> dict | None:
    """One worklist cell."""
    if record is None:
        return None
    status = status_of(comparison_for(front, record), state.title_authors, now)
    return {"status": status, "status_word": STATUS_WORDS[status],
            "deadline": state.title_authors.deadline}


def act(state: ReviewState, action: str, body: dict, *, front: FrontMatter | None,
        record: IndicoRecord | None, now: datetime | None = None) -> None:
    """One step of the check. Raises ``ValueError`` with an editor-facing reason."""
    now = now or _now()
    ta = state.title_authors
    if action == "send":
        comparison = comparison_for(front, record)
        if comparison is None or not comparison.differs:
            raise ValueError("the paper and Indico do not differ, so there is nothing to send")
        state.title_authors = TitleAuthorState(
            plan=plan_of(comparison), sent_at=_iso(now), deadline=_iso(deadline_from(now)),
            email_override=ta.email_override)
    elif action in ("agreed", "declined", "apply"):
        if not ta.sent_at:
            raise ValueError("mark the email as sent first")
        if action == "apply":
            deadline = _parse(ta.deadline)
            if deadline and now < deadline:
                raise ValueError(f"the author has until {deadline_text(deadline)} to reply")
        else:
            ta.reply, ta.reply_at = action, _iso(now)
        if action != "declined":
            ta.applied_at = _iso(now)
    elif action == "undo":
        ta.applied_at = ""
        if ta.reply == "agreed":
            ta.reply = ta.reply_at = ""
    elif action == "restart":
        state.title_authors = TitleAuthorState()
    elif action == "email":
        ta.email_override = str(body.get("text") or "").strip()
    elif action == "tick":
        ta.indico_done[str(body.get("key", ""))] = bool(body.get("done"))
    else:
        raise ValueError(f"unknown step: {action}")


# ---------------------------------------------------------------------------
# The paper's side of the change
# ---------------------------------------------------------------------------

def additions(state: ReviewState) -> list[dict]:
    """Authors to add to the paper, once the change has been applied."""
    ta = state.title_authors
    return list(ta.plan.get("add_to_paper", [])) if ta.applied_at else []


def _groups(people: list[dict]) -> list[tuple[list[str], str]]:
    """Names grouped by affiliation, in order, as JACoW author blocks are set."""
    groups: dict[str, list[str]] = {}
    for one in people:
        groups.setdefault(one.get("affiliation", ""), []).append(one["name"])
    return [(names, affiliation) for affiliation, names in groups.items()]


def _tex(text: str) -> str:
    return re.sub(r"(?<!\\)([&%#_$])", r"\\\1", text)


def add_authors_latex(source: str, people: list[dict]) -> str:
    r"""Append *people* to the ``\author{}`` block, each affiliation group after
    a ``\\`` break. Unchanged if the block cannot be found."""
    from src.parser.latex_parser import _blank_comment, _extract_braced

    if not people:
        return source
    blanked = "\n".join(_blank_comment(line) for line in source.split("\n"))
    match = re.search(r"\\author\s*(?=\{)", blanked)
    if not match:
        return source
    _content, end = _extract_braced(blanked, match.end())
    close = end - 1
    insertion = "".join(
        " \\\\\n  " + ", ".join(_tex(n) for n in names) + (f", {_tex(aff)}" if aff else "")
        for names, aff in _groups(people))
    return source[:close] + insertion + source[close:]


def word_author_addition(source_path: Path, people: list[dict]) -> tuple[int, str, str] | None:
    """``(paragraph index, before, after)`` adding *people* at the end of a Word
    paper's author block, or ``None`` if the block cannot be found."""
    import docx

    from src.checks.word_front_checks import read_front_matter

    if not people:
        return None
    front = read_front_matter(source_path)
    if not front.author_paragraphs:
        return None
    index = front.author_paragraphs[-1]
    before = docx.Document(str(source_path)).paragraphs[index].text
    lines = [", ".join(names) + (f", {aff}" if aff else "") for names, aff in _groups(people)]
    return index, before, before + "".join("\n" + line for line in lines)
