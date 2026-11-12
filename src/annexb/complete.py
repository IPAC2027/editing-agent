"""Fill what Appendix B's layout needs and the reference does not say, from the registries.

* JACoW papers: refs.jacow.org (authors, pages, place, month, paper ID, DOI); failing
  that, the JACoW conference list (place and month) and the DOI JACoW gives every paper
  since 2015 and IPAC2014 (10.18429/JACoW-<CONF><YEAR>-<PAPER>), checked with DataCite.
* Everything with a DOI: the DOI is checked first (:mod:`src.refcheck.doi`: it exists,
  belongs to this reference, typos corrected, a missing one found); then the DOI's
  Crossref record gives the volume, pages, year, the full author list and the journal's
  short title, and for a conference paper the event's place and month.
* "et al." with six authors or fewer is written out from the record (Table 2).

A value from a registry fills a gap; it replaces the author's own value only when
the record is certainly the same paper (the DOI checked, or the title alike and the
conference or journal the same). Every value added or replaced is named, with its
source, on the editor's card.
"""

from __future__ import annotations

import re

from src.annexb import conferences, journals
from src.annexb.model import MONTHS, Name, Outcome, Problem, Ref
from src.annexb.names import from_record, parse_authors, same_people
from src.annexb.parse import Parsed

_DOI_KIND = {"conference": "conference_published", "conference_unpublished":
             "conference_unpublished", "conference_current": "conference_current",
             "journal": "journal", "accepted": "journal_accepted", "submitted": "journal_submitted",
             "arxiv": "arxiv", "online": "web", "book_chapter": "book_chapter", "book": "book",
             "report": "report", "technical_report": "report", "thesis": "thesis",
             "unpublished": "unpublished", "private": "private_comm"}
_PRINTS_DOI = {"conference", "journal", "arxiv", "book_chapter", "book", "report",
               "technical_report", "thesis", "manual"}


def _set(r: Ref, out: Outcome, name: str, value: str, source: str, *, replace: bool = False
         ) -> None:
    """Fill a field (or replace it when *replace*); the editor's card says so."""
    if not value:
        return
    old = getattr(r, name)
    if old == value:
        return
    if old and not replace:
        return
    r.put(name, value, source)


def crossref_message(doi: str) -> dict | None:
    from src.refcheck import doi as registry

    if doi.lower().startswith(("10.18429/", "10.48550/")):
        return None
    answer = registry._get(f"https://api.crossref.org/works/{registry.clean(doi)}")
    if answer is registry.UNREACHABLE:
        return None
    status, body = answer
    if status != 200 or not body:
        return None
    return body.get("message") or None


def _record_authors(message: dict) -> list[Name]:
    out = []
    for a in message.get("author") or []:
        if a.get("family"):
            out.append(from_record(a["family"], a.get("given", "")))
        elif a.get("name"):
            out.append(Name(literal=a["name"]))
    return out


def _expand_et_al(r: Ref, out: Outcome, names: list[Name], source: str, *,
                  record_et_al: bool = False) -> None:
    """Table 2: "et al." only for more than six authors; fewer are listed."""
    if not names or not r.et_al or record_et_al or len(names) <= len(r.authors):
        return
    if len(names) <= 6 and r.authors and names[0].key() == r.authors[0].key():
        r.authors = names
        r.et_al = False
        r.source["authors"] = source
        out.changes.append(f"author list written out from {source} ({len(names)} authors; "
                           "Appendix B uses “et al.” only for more than six)")


# ---------------------------------------------------------------------------
# The DOI
# ---------------------------------------------------------------------------

def _check_doi(r: Ref, out: Outcome) -> None:
    from src.annexb.categories import render
    from src.refcheck import doi as registry

    if r.category not in _PRINTS_DOI or r.category == "arxiv":
        return
    probe = r.copy()
    probe.doi = r.doi
    text = render(probe)
    try:
        report = registry.check(text, _DOI_KIND.get(r.category, ""))
    except Exception:  # noqa: BLE001 — no verdict, nothing changes
        return
    if report.status in ("found", "corrected") and report.doi:
        before = r.doi
        r.put("doi", report.doi, report.source or "Crossref")
        out.changes.append((f"DOI corrected: {report.reason}" if before else
                            f"DOI added: {report.reason}"))
    elif report.status == "possible" and report.doi:
        out.problems.append(Problem("REF-DOI-POSSIBLE", "Possible DOI, check it before "
                                    f"adding: {report.reason}.", "doi", "info"))
    elif report.status in ("wrong", "unresolved"):
        out.problems.append(Problem("REF-DOI-WRONG", f"Wrong DOI: {report.reason}. Needs the "
                                    "right DOI, from the paper itself.", "doi", "error"))
        r.doi = ""
        r.source.pop("doi", None)


# ---------------------------------------------------------------------------
# Conference papers
# ---------------------------------------------------------------------------

def _jacow_doi_parts(doi: str) -> tuple[str, str, str] | None:
    m = re.fullmatch(r"10\.18429/JACoW-([A-Za-z]+)[-_]?(\d{4})-([A-Za-z0-9]+)", doi or "", re.I)
    return (m.group(1), m.group(2), m.group(3).upper()) if m else None


def _conference(r: Ref, out: Outcome) -> None:
    label = conferences.label_in(r.conference)[0] if r.conference and \
        conferences.label_in(r.conference) else None
    parts = _jacow_doi_parts(r.doi)
    if parts and not label:
        series = conferences.SERIES.get(parts[0].lower())
        if series:
            label = conferences.Label(series, parts[1])
            _set(r, out, "conference", label.text, "DOI")
    if parts and not r.paper_id:
        r.paper_id = parts[2]
    paper = None
    if not r.title and r.doi:
        from src.refcheck import doi as registry
        work = registry.lookup(r.doi)                 # a JACoW DOI's DataCite record
        if isinstance(work, registry.Work) and work.title:
            from src.annexb.engine import _sentence_case
            r.put("title", _sentence_case(work.title)[0], work.source or "DataCite")
            out.changes.append(f"title added from {work.source or 'DataCite'}: “{r.title}”")
    if r.title and (label or parts):
        try:
            paper = conferences.find_paper(r.title, label, r.paper_id, r.doi)
        except Exception:  # noqa: BLE001
            paper = None
    if paper:
        src = "refs.jacow.org"
        if not r.title and paper.title:
            from src.annexb.engine import _sentence_case
            r.put("title", _sentence_case(paper.title)[0], src)
        if paper.label and not label:
            label = paper.label
            _set(r, out, "conference", label.text, src)
        sure = True
        published = r.category == "conference"
        for name in ("city", "state", "country", "month", "pages", "paper_id"):
            value = getattr(paper, name)
            if name == "pages" and not published:
                continue                          # "presented at …" has no pages
            if not value:
                continue
            old = getattr(r, name)
            if old and old != value and name in ("pages", "month", "city", "country", "state"):
                out.changes.append(f"{name} corrected from {src}: {old} → {value}")
                _set(r, out, name, value, src, replace=True)
            elif not old:
                _set(r, out, name, value, src)
        if paper.year and label and paper.year == label.year:
            _set(r, out, "year", paper.year, src, replace=True)
        if paper.doi and not r.doi and published:
            r.put("doi", paper.doi, src)
            out.changes.append(f"DOI added from {src}: {paper.doi}")
        names, _, ok = parse_authors(", ".join(paper.authors))
        if ok and sure:
            _expand_et_al(r, out, names, src, record_et_al=paper.et_al)
    if label:
        place = conferences.venue(label)
        for name in ("city", "state", "country", "month"):
            value = place.get(name, "")
            if value and not getattr(r, name):
                _set(r, out, name, value, "JACoW conference list")
        if not r.year or (r.year != label.year and r.source.get("year") == "text"):
            if r.year and r.year != label.year:
                out.changes.append(f"year corrected to the conference's: {r.year} → {label.year}")
            r.put("year", label.year, "conference label")
        # every JACoW paper since 2015 (and IPAC2014) has a DOI
        if not r.doi and r.paper_id and r.category == "conference" and \
                (int(label.year) >= 2015 or label.doi_id == "IPAC2014"):
            from src.refcheck import doi as registry
            candidate = f"10.18429/JACoW-{label.doi_id}-{r.paper_id.upper()}"
            work = registry.lookup(candidate)
            if isinstance(work, registry.Work):
                r.put("doi", candidate, "DataCite")
                out.changes.append(f"DOI added: {candidate} (JACoW's DOI for paper "
                                   f"{r.paper_id}, checked with DataCite)")


def _conference_record(r: Ref, out: Outcome, message: dict) -> None:
    """A non-JACoW conference paper: Crossref's event gives place and month."""
    event = message.get("event") or {}
    loc = str(event.get("location") or "")
    if loc and not r.country:
        from src.annexb.places import country, state
        bits = [b.strip() for b in loc.split(",") if b.strip()]
        land = country(bits[-1]) if bits else ""
        if land:
            _set(r, out, "country", land, "Crossref")
            if len(bits) >= 3 and state(bits[-2], land):
                _set(r, out, "state", state(bits[-2], land), "Crossref")
                _set(r, out, "city", bits[-3], "Crossref")
            elif len(bits) >= 2:
                _set(r, out, "city", bits[-2], "Crossref")
    start = (event.get("start") or {}).get("date-parts") or [[]]
    if start and len(start[0]) >= 2 and not r.month:
        _set(r, out, "month", MONTHS[int(start[0][1]) - 1], "Crossref")
        if not r.year:
            _set(r, out, "year", str(start[0][0]), "Crossref")
    pages = str(message.get("page") or message.get("article-number") or "")
    if pages and not r.pages:
        _set(r, out, "pages", pages.replace("–", "-"), "Crossref")


# ---------------------------------------------------------------------------
# Journal articles and the rest
# ---------------------------------------------------------------------------

def _journal_record(r: Ref, out: Outcome, message: dict) -> None:
    from src.refcheck.doi import title_similarity

    title = " ".join(message.get("title") or [])
    same = bool(r.title and title and title_similarity(r.title, title) >= 0.8)
    if title and not r.title:
        from src.annexb.engine import _sentence_case
        r.put("title", _sentence_case(re.sub(r"<[^>]+>", "", title))[0], "Crossref")
        out.changes.append(f"title added from Crossref: “{r.title}”")
        same = True
    for name, key in (("volume", "volume"), ("pages", "page")):
        value = str(message.get(key) or (message.get("article-number") if key == "page" else "")
                    or "")
        value = value.replace("–", "-")
        if not value:
            continue
        old = getattr(r, name)
        if not old:
            _set(r, out, name, value, "Crossref")
        elif same and re.sub(r"\D", "", old.split("-")[0]) != re.sub(r"\D", "", value.split("-")[0]):
            out.changes.append(f"{name} corrected from Crossref: {old} → {value}")
            _set(r, out, name, value, "Crossref", replace=True)
    issued = (message.get("issued") or message.get("published") or {}).get("date-parts") or [[]]
    if issued and issued[0] and not r.year:
        _set(r, out, "year", str(issued[0][0]), "Crossref")
    # the journal: Annex C / ISO 4 from the record's full title when the author's is unknown
    full = " ".join(message.get("container-title") or [])
    short = " ".join(message.get("short-container-title") or [])
    if (not r.journal or r.source.get("journal") in ("text", "")) and (full or short):
        if not r.journal_written and full:
            r.journal_written = full
        abbr, source, note = journals.abbreviate(full or short, record_short=short)
        if abbr and source:
            if r.journal and r.journal != abbr:
                out.changes.append(f"journal written {abbr} ({source}, from the DOI's record "
                                   f"“{full or short}”)")
            r.put("journal", abbr, source)
            out.problems = [p for p in out.problems if p.code != "REF-JOURNAL"]
    if same or r.et_al:
        _expand_et_al(r, out, _record_authors(message), "Crossref")


def _book_record(r: Ref, out: Outcome, message: dict) -> None:
    place = str(message.get("publisher-location") or "")
    if place and not r.country:
        from src.annexb.places import country, state
        bits = [b.strip() for b in place.split(",") if b.strip()]
        land = country(bits[-1]) if bits else ""
        if land:
            _set(r, out, "country", land, "Crossref")
            if len(bits) >= 2:
                st = state(bits[-2], land) if len(bits) >= 3 else ""
                if st:
                    _set(r, out, "state", st, "Crossref")
                    _set(r, out, "city", bits[-3], "Crossref")
                else:
                    _set(r, out, "city", bits[-2], "Crossref")
    if message.get("publisher") and not r.publisher:
        _set(r, out, "publisher", str(message["publisher"]), "Crossref")
    if r.category == "book_chapter":
        pages = str(message.get("page") or "").replace("–", "-")
        if pages and not r.pages:
            _set(r, out, "pages", pages, "Crossref")
        container = " ".join(message.get("container-title") or [])
        if container and not r.book:
            _set(r, out, "book", container, "Crossref")
    issued = (message.get("issued") or {}).get("date-parts") or [[]]
    if issued and issued[0] and not r.year:
        _set(r, out, "year", str(issued[0][0]), "Crossref")


def canonical_case(doi: str, message: dict | None) -> str:
    """A DOI in its registered capitals (registries answer in lower case)."""
    if not message:
        return doi
    link = str(((message.get("resource") or {}).get("primary") or {}).get("URL") or "")
    k = link.lower().find(doi.lower())
    if k >= 0:
        return link[k:k + len(doi)]
    if doi.lower().startswith("10.1109/"):
        return "10.1109/" + doi[8:].upper()
    return doi


def complete(p: Parsed, out: Outcome, *, llm: bool | None = None) -> None:
    r = out.ref
    before = r.copy()
    _check_doi(r, out)
    if r.category in ("conference", "conference_unpublished", "conference_current"):
        _conference(r, out)
    message = crossref_message(r.doi) if r.doi else None
    if message and r.doi == r.doi.lower():
        r.doi = canonical_case(r.doi, message)
        out.changes = [c.replace(c[c.lower().find(r.doi.lower()):][:len(r.doi)], r.doi)
                       if r.doi.lower() in c.lower() else c for c in out.changes]
    if message:
        kind = message.get("type", "")
        if r.category == "conference" or (kind == "proceedings-article" and
                                          r.category == "conference"):
            _conference_record(r, out, message)
        elif r.category in ("journal", "accepted"):
            _journal_record(r, out, message)
        elif r.category in ("book", "book_chapter"):
            _book_record(r, out, message)
    for name in ("city", "state", "country", "month", "year", "pages", "volume", "paper_id"):
        old, new = getattr(before, name), getattr(r, name)
        if name == "paper_id" and (r.doi or r.category != "conference"):
            continue                              # not printed with a DOI
        if new and not old:
            out.changes.append(f"{name.replace('_', ' ')} {new} added from "
                               f"{r.source.get(name, 'a registry')}")


__all__ = ["complete", "crossref_message"]
