"""The local model reads a reference the rules could not, and only reads it.

When the rules cannot tell a reference's kind, cannot find its title or its
authors, or leave words they cannot place, the model is asked one thing:
which part of the reference is which field, and which of Appendix B's kinds
it is. It answers in JSON, and every value it gives must be copied exactly
from the reference (checked character by character): the model can point at
words, never add one. The fields it points at then go through the same steps
as the rules' (names as initials, sentence case, the journal's abbreviation,
the registries, the layout), so the text the editor sees is never written by
the model. An answer that fails the check is sent back once with the reasons.
"""

from __future__ import annotations

import json
import re

from src.annexb import conferences, places
from src.annexb.categories import CATEGORIES
from src.annexb.model import Outcome, Ref
from src.annexb.names import parse_authors
from src.annexb.parse import Chunk, Parsed, month_abbr, normalize, parse

_FIELDS = ("authors", "title", "journal", "conference", "proceedings", "book", "editors",
           "edition", "volume", "issue", "pages", "paper_id", "institution", "department",
           "organization", "publisher", "city", "state", "country", "month", "year", "report",
           "thesis", "patent")

SYSTEM = (
    "You split one bibliographic reference into its fields. Answer with one JSON object "
    "only.\n"
    "Keys: \"kind\" (one of: " + ", ".join(CATEGORIES) + ") and any of: "
    + ", ".join(_FIELDS) + ".\n"
    "Every value must be copied EXACTLY, character for character, from the reference: do "
    "not correct, abbreviate, expand, translate or reorder anything, and do not add "
    "anything that is not written there. Leave out a field the reference does not have. "
    "\"authors\" is the whole author list as written (one string). \"conference\" is the "
    "conference's short label if written (e.g. IPAC'23 or IPAC 2023); \"proceedings\" is "
    "the proceedings' name when written out. \"pages\" is the page range or article "
    "number. \"month\" and \"year\" are the date as written.\n"
    "Kinds: conference = a paper in published proceedings; conference_unpublished = "
    "presented at a past conference, not published; conference_current = at this "
    "conference; journal = a journal article; accepted = accepted for publication; "
    "submitted = submitted for publication; arxiv = an arXiv preprint; online = a web page; "
    "book_chapter; book; report = a report with authors; technical_report = a report cited "
    "by its title (design reports); thesis; handbook; manual; patent; unpublished; private "
    "= private communication.")


def needs_reader(p: Parsed, out: Outcome) -> bool:
    """The rules could not read this reference well enough."""
    r = out.ref
    if not r.category:
        return True
    if r.category not in ("online", "technical_report", "handbook", "manual", "private") and \
            not (r.title or r.book):
        return True
    if r.category not in ("online", "technical_report", "handbook", "manual") and \
            (not r.authors or not p.authors_ok):
        return True
    leftover = re.sub(r"[^\w]+", " ", r.note).split()
    return len(leftover) >= 2 or any(w.isdigit() for w in leftover)


def _verify(answer: dict, text: str) -> list[str]:
    problems = []
    kind = answer.get("kind")
    if kind not in CATEGORIES:
        problems.append(f"\"kind\" must be one of the listed kinds, not {kind!r}")
    for key, value in answer.items():
        if key == "kind" or value in (None, "", []):
            continue
        if key not in _FIELDS:
            problems.append(f"\"{key}\" is not a field")
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if not isinstance(v, (str, int)):
                problems.append(f"\"{key}\" must be text")
                continue
            if re.sub(r"\s+", " ", str(v)).strip() not in text:
                problems.append(f"\"{key}\": “{v}” is not in the reference as written")
    return problems


def _ask(text: str, feedback: str = "") -> dict | None:
    from src.llm import client

    user = f"Reference:\n{text}"
    if feedback:
        user += f"\n\nYour previous answer was refused:\n{feedback}\nCorrect it."
    try:
        raw = client.chat(SYSTEM, user, json_mode=True, temperature=0.0)
    except Exception:  # noqa: BLE001 — no model, no reading
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        answer = json.loads(raw)
    except ValueError:
        return {"kind": None, "_invalid": raw[:200]}
    return answer if isinstance(answer, dict) else None


def _to_ref(answer: dict, text: str, base: Ref) -> Ref:
    r = Ref(category=answer["kind"])
    src = "model"
    for name in ("doi", "url", "arxiv"):                  # identifiers stay the rules'
        if getattr(base, name):
            r.put(name, getattr(base, name), base.source.get(name, "text"))

    def val(key: str) -> str:
        v = answer.get(key)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        return re.sub(r"\s+", " ", str(v or "")).strip(" ,;")

    if val("authors"):
        names, et_al, ok = parse_authors(val("authors"))
        r.authors, r.et_al = names, et_al
        r.source["authors"] = src
    if val("editors"):
        r.editors = parse_authors(val("editors"))[0]
        r.source["editors"] = src
    title = val("title").strip("“”\"").rstrip(".,")
    r.put("title", title, src)
    if val("journal"):
        r.put("journal_written", val("journal"), src)
    if val("conference"):
        found = conferences.label_in(val("conference"))
        if found:
            r.put("conference", found[0].text, src)
    if val("proceedings") and not r.conference:
        found = conferences.label_in(val("proceedings"))
        if found:
            r.put("conference", found[0].text, src)
        else:
            name = re.sub(r"^(?:in\s+)?(?:the\s+)?(?:Proc(?:eedings|\.)?\s*(?:of\s+)?(?:the\s+)?)",
                          "", val("proceedings"), flags=re.I)
            r.put("proceedings", f"Proc. {name}", src)
    for key in ("book", "edition", "volume", "issue", "paper_id", "institution", "department",
                "organization", "publisher", "report", "patent"):
        r.put(key, val(key), src)
    if val("pages"):
        r.put("pages", re.sub(r"^(?:pp?\.|pages?)\s*", "", val("pages")), src)
    land = places.country(val("country")) or val("country")
    r.put("country", land, src)
    st = places.state(val("state"), land) or val("state")
    r.put("state", st, src)
    r.put("city", val("city"), src)
    month = val("month")
    m = re.match(r"([A-Za-z]{3})", month)
    if m:
        try:
            r.put("month", month_abbr(m.group(1)), src)
        except KeyError:
            pass
    year = re.search(r"(?:19|20)\d{2}", val("year"))
    if year:
        r.put("year", year.group(0), src)
    thesis = val("thesis").lower()
    if thesis or r.category == "thesis":
        r.put("thesis", "M.Sc." if thesis.startswith(("m", "ma")) else "Ph.D.", src)
    status = {"conference_current": "this conference", "unpublished": "unpublished",
              "submitted": "submitted", "accepted": "accepted", "private": "private"}
    if r.category in status:
        r.put("status", status[r.category], src)
    return r


def read_with_model(text: str) -> tuple[Parsed, Outcome] | None:
    """The model's reading, checked; None when there is no model or no acceptable answer."""
    from src.annexb.classify import assign  # noqa: F401  (kept for symmetry)
    from src.annexb.engine import normalise

    norm = normalize(text)
    base = parse(text)
    feedback = ""
    for _ in range(2):
        answer = _ask(norm, feedback)
        if answer is None:
            return None
        problems = _verify(answer, norm)
        if not problems:
            break
        feedback = "\n".join(f"- {x}" for x in problems)
    else:
        return None
    r = _to_ref(answer, norm, base.ref)
    covered = norm
    for value in answer.values():
        for v in (value if isinstance(value, list) else [value]):
            if isinstance(v, str) and v:
                covered = covered.replace(v, " ")
    for ident in (r.doi, r.url, r.arxiv):
        if ident:
            covered = covered.replace(ident, " ")
    covered = re.sub(r"\b(?:doi|https?|in|Proc|and|pp|p|vol|no|et|al)\b|[^\w]+", " ", covered)
    p = Parsed(ref=r, title_quoted=True, authors_ok=bool(r.authors))
    leftover = covered.split()
    if leftover:
        r.note = " ".join(leftover)
        p.chunks = [Chunk(0, 0, r.note)]
    out = Outcome(original=text, ref=r, category=r.category, parsed_by="model")
    normalise(r, out, online=True, llm=True)
    return p, out


__all__ = ["needs_reader", "read_with_model", "SYSTEM"]
