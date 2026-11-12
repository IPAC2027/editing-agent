"""One reference in, the same reference in Appendix B's exact layout out.

    text ──parse──▶ fields ──classify──▶ kind ──normalise──▶ fields in JACoW's forms
         ──complete (registries)──▶ every field the layout needs ──render──▶ text

* parse / classify: :mod:`src.annexb.parse`, :mod:`src.annexb.classify`; when they
  cannot read a reference, the local model reads it (:mod:`src.annexb.reader`), and
  every value it gives must be a piece of the reference itself;
* normalise: names as initials, the title in sentence case (proper nouns and
  acronyms kept), the journal's ISO 4 abbreviation (Annex C first), the conference
  label (IPAC’23), the month (Oct.), the place (Menlo Park, CA, USA);
* complete: what the layout needs and the reference does not say, from
  refs.jacow.org (JACoW papers), the JACoW conference list (place and month),
  Crossref and DataCite (journals, DOIs), the arXiv identifier (month, year, DOI);
* render: :mod:`src.annexb.categories`.

Nothing is invented: a field nobody could supply stays out of the text and is
named in ``Outcome.missing``; every value a registry supplied is named, with its
source, in ``Outcome.changes``.
"""

from __future__ import annotations

import re

from src.annexb import categories, conferences, journals
from src.annexb.classify import assign, classify
from src.annexb.model import MONTHS, Name, Outcome, Problem, Ref
from src.annexb.names import from_record, same_people
from src.annexb.parse import Parsed, month_abbr, normalize, parse

#: What each kind's layout prints; any other field the author gave is dropped (and named).
PRINTS = {
    "conference": {"authors", "title", "conference", "proceedings", "city", "state", "country",
                   "month", "year", "pages", "doi", "paper_id"},
    "conference_unpublished": {"authors", "title", "conference", "city", "state", "country",
                               "month", "year", "paper_id"},
    "conference_current": {"authors", "title", "conference", "city", "state", "country",
                           "month", "year", "paper_id"},
    "journal": {"authors", "title", "journal", "volume", "issue", "pages", "month", "year", "doi"},
    "accepted": {"authors", "title", "journal"},
    "submitted": {"authors", "title"},
    "arxiv": {"authors", "title", "month", "year", "doi", "arxiv"},
    "online": {"authors", "title", "organization", "url"},
    "book_chapter": {"authors", "title", "book", "editors", "city", "state", "country",
                     "publisher", "year", "pages", "doi", "url"},
    "book": {"authors", "book", "title", "edition", "editors", "city", "state", "country",
             "publisher", "year", "doi", "url"},
    "report": {"authors", "title", "institution", "city", "state", "country", "report", "month",
               "year", "doi", "url"},
    "technical_report": {"title", "edition", "editors", "institution", "city", "state",
                         "country", "report", "month", "year", "doi", "url"},
    "thesis": {"authors", "title", "thesis", "department", "institution", "city", "state",
               "country", "year", "doi", "url"},
    "handbook": {"title", "edition", "organization", "city", "state", "country", "month",
                 "year", "pages", "url"},
    "manual": {"title", "organization", "city", "state", "country", "month", "year", "doi",
               "url"},
    "patent": {"authors", "title", "patent", "month", "day", "year", "status"},
    "unpublished": {"authors", "title"},
    "private": {"authors", "month", "year"},
}


# ---------------------------------------------------------------------------
# Normalising what the author wrote
# ---------------------------------------------------------------------------

def _sentence_case(title: str, *, llm: bool | None = None) -> tuple[str, list[str]]:
    """The title in sentence case; (title, words left as written because unsure)."""
    from src.references import sent_case_report

    if not title or title.endswith("?") and title.isupper():
        return title, []
    try:
        report = sent_case_report(title)
    except Exception:  # noqa: BLE001
        return title, []
    text, unsure = report.text, list(report.unsure)
    # a name's possessive keeps its capital: "Green's functions", "Maxwell’s equations"
    for word in re.findall(r"\b[A-Z][a-z]+['’]s\b", title):
        text = re.sub(rf"\b{re.escape(word.lower())}\b", word, text)
    # an institution after its name keeps its capital: "Cornell University", "Oak Ridge
    # National Laboratory", "Electron-Ion Collider"
    for m in re.finditer(r"\b([A-Z][\w\-]+)\s+(University|Laboratory|Laboratories|Institute|"
                         r"College|Collider|Center|Centre|Observatory|Facility|Lab)\b", title):
        if re.search(rf"\b{re.escape(m.group(1))}\s+{m.group(2).lower()}\b", text):
            text = re.sub(rf"\b({re.escape(m.group(1))})\s+{m.group(2).lower()}\b",
                          rf"\1 {m.group(2)}", text)
    if unsure and llm:
        try:
            from src.llm.classify import resolve_title_casing
            resolved = resolve_title_casing(text, unsure)
            if resolved and resolved.text:
                text, unsure = resolved.text, list(resolved.unsure)
        except Exception:  # noqa: BLE001 — no model, the deterministic answer stands
            pass
    return text, unsure


def normalise(r: Ref, out: Outcome, *, online: bool, llm: bool | None) -> None:
    """Every field in the form Appendix B prints it."""
    if r.title and r.category not in ("online", "technical_report", "handbook", "manual"):
        cased, unsure = _sentence_case(r.title, llm=llm)
        if cased != r.title:
            r.title = cased
        if unsure:
            out.problems.append(Problem("REF-TITLE-CASE",
                                        "Sentence case: check the capitals of "
                                        + ", ".join(f"“{w}”" for w in unsure)
                                        + " (proper noun or ordinary word?).", "title", "info"))
    if r.book and r.category in ("book", "book_chapter"):
        pass                                      # book titles keep their capitals
    if r.journal_written and r.category in ("journal", "accepted"):
        abbr, source, note = journals.abbreviate(r.journal_written, online=online)
        r.put("journal", abbr, source or "text")
        if note:
            out.problems.append(Problem("REF-JOURNAL", note[0].upper() + note[1:] + ".",
                                        "journal", "info" if source else "warning"))
    if r.conference:
        found = conferences.label_in(r.conference)
        if found:
            r.conference = found[0].text
            if not r.year and r.category.startswith("conference"):
                r.put("year", found[0].year, "conference label")      # IPAC’23 was in 2023
    elif r.proceedings and r.year and r.category.startswith("conference"):
        series = conferences.series_from_name(r.proceedings)
        if series:
            r.put("conference", conferences.Label(series, r.year).text, "conference name")
            out.changes.append(f"conference written by its label: {r.proceedings} → "
                               f"{r.conference}")
    if r.proceedings and r.conference:
        # The short form is enough (Appendix B): "in Proc. IPAC’23"
        r.proceedings = ""
    if r.month:
        r.month = "-".join(month_abbr(m) if re.match(r"[A-Za-z]{3}", m) else m
                           for m in r.month.split("-"))
    if r.pages and r.category.startswith("conference") and re.fullmatch(
            r"(?:MO|TU|WE|TH|FR|SA|SU)[A-Z]{0,6}\d{1,4}[A-Z]?\d{0,2}", r.pages):
        r.put("paper_id", r.pages, r.source.get("pages", "text"))   # "p. MOYBB3" is a paper ID
        r.pages = ""
    if r.pages:
        r.pages = re.sub(r"\s*(?:-|–|—|−)+\s*", "-", r.pages)
        a, _, b = r.pages.partition("-")
        if b and a == b:
            r.pages = a
    if r.doi:
        from src.refcheck.doi import display
        r.doi = display(r.doi, r.doi)
    if r.category == "arxiv" and r.arxiv:
        r.put("doi", f"10.48550/arXiv.{r.arxiv}", r.source.get("arxiv", "text"))
        m = re.fullmatch(r"(\d{2})(\d{2})\.\d{4,5}", r.arxiv)
        if m and 1 <= int(m.group(2)) <= 12:
            year, month = f"20{m.group(1)}", MONTHS[int(m.group(2)) - 1]
            if not r.year or r.year == year:
                if not r.month:
                    r.put("month", month, "arXiv identifier")
                if not r.year:
                    r.put("year", year, "arXiv identifier")
    if r.category == "online":
        r.month = r.year = ""
    if r.category in ("report", "technical_report", "thesis", "handbook", "manual") and \
            not r.country:
        from src.annexb.places import institution_place
        where = institution_place(r.institution or r.organization)
        if where:
            city, state, land = where
            r.put("city", city, "institution list")
            r.put("state", state, "institution list")
            r.put("country", land, "institution list")
            out.changes.append(f"place of {r.institution or r.organization} added: "
                               + ", ".join(x for x in where if x))


# ---------------------------------------------------------------------------
# Rendering and comparing
# ---------------------------------------------------------------------------

def _canon(text: str) -> str:
    """Compare two references ignoring what does not show: spaces, quote styles."""
    t = normalize(text)
    t = t.replace("'", "’").replace("‘", "’").replace("--", "-").replace("–", "-")
    t = re.sub(r"\s*\n\s*", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _dropped(p: Parsed, r: Ref) -> list[str]:
    out = []
    shown = PRINTS.get(r.category, set())
    for name in ("url", "issue", "paper_id", "journal", "arxiv", "edition", "editors",
                 "publisher", "institution", "department", "organization", "report",
                 "volume", "pages", "month", "day", "proceedings"):
        value = getattr(r, name)
        if not value or name in shown:
            continue
        if name == "arxiv" and r.doi:
            continue
        if name == "journal" and r.category == "submitted":
            out.append(f"the journal “{value}” (a submitted paper names none)")
            continue
        if name == "paper_id" and r.category == "conference" and r.doi:
            continue
        if name == "proceedings" and r.conference:
            continue
        if isinstance(value, list):
            value = ", ".join(n.plain() for n in value)
        out.append(f"{name.replace('_', ' ')} “{value}”")
    if r.note:
        out.append(f"“{r.note}”")
    out += [f"“{d}”" for d in p.dropped]
    return out


def build(text: str, *, online: bool = True, llm: bool | None = None,
          record_type: str = "") -> tuple[Parsed, Outcome]:
    """Parse, classify and normalise one reference (no registry asked yet)."""
    p = parse(text)
    category = classify(p, record_type=record_type)
    r = p.ref
    r.category = category
    out = Outcome(original=text, ref=r, category=category)
    if not category:
        return p, out
    assign(p, category, normalize(text))
    out.raw = r.copy()
    normalise(r, out, online=online, llm=llm)
    return p, out


def _normalised(raw: Ref, r: Ref, original: str = "") -> list[str]:
    """What normalising changed, in the editor's words (checked against the author's text)."""
    from src.annexb.categories import _Out
    out = []
    o = _Out(False)
    seen = normalize(original).replace("'", "’") if original else ""

    def absent(piece: str) -> bool:
        return bool(piece) and bool(seen) and piece.replace("'", "’") not in seen

    if r.authors and r.source.get("authors") in ("text", "model") and absent(o.authors(r)):
        out.append("authors as initials and family name (Table 2)")
    if raw.title and r.title and raw.title != r.title:
        out.append("title in sentence case" if raw.title.lower() == r.title.lower() else
                   "title as in the record")
    elif r.title and absent(f"“{r.title}”"):
        out.append("title in “…” with the comma after it")
    if raw.journal_written and r.journal and raw.journal_written.rstrip(".") != r.journal.rstrip("."):
        src = r.source.get("journal", "")
        out.append(f"journal abbreviated: {raw.journal_written} → {r.journal}"
                   + (f" ({src})" if src and src != "text" else ""))
    if r.category == "journal" and r.volume and absent(f"vol. {r.volume}"):
        out.append("“vol.”, “no.”, “p.” written out")
    if raw.conference and raw.conference.replace("'", "’") != r.conference:
        out.append(f"conference label {r.conference}")
    elif r.conference and absent(f"Proc. {r.conference}") and r.category == "conference":
        out.append(f"“in Proc. {r.conference}”")
    if raw.proceedings and not r.proceedings and r.conference:
        out.append(f"proceedings written short: in Proc. {r.conference}")
    if r.month and absent(r.month):
        out.append(f"month written {r.month}")
    if r.state and absent(f", {r.state},"):
        out.append(f"state written {r.state}")
    if raw.country and raw.country != r.country or (r.country and absent(r.country)
                                                     and r.source.get("country") == "text"):
        out.append(f"country written {r.country}")
    if r.report and absent(f"Rep. {r.report}") and r.category in ("report", "technical_report"):
        out.append("“Rep.” before the report number")
    if r.pages and absent(o.pages(r)):
        out.append(f"pages with “{o.pages(r).split()[0]}”")
    if raw.doi and raw.doi != r.doi and raw.doi.lower() == r.doi.lower():
        out.append("DOI in its registered capitals")
    elif r.doi and absent(f"doi:{r.doi}") and r.source.get("doi") == "text":
        out.append("DOI written doi:…, last")
    return out


def finish(p: Parsed, out: Outcome) -> Outcome:
    """Render, compare with the original, and say what is missing and what was dropped."""
    r = out.ref
    if not r.category:
        out.problems.append(Problem("REF-KIND", "Could not tell which kind of reference this "
                                    "is (Appendix B's 16 kinds); left as written.",
                                    severity="error"))
        return out
    out.category = r.category
    if out.raw is not None:
        out.changes = _normalised(out.raw, r, out.original) + out.changes
    out.text = categories.render(r)
    out.latex = categories.render(r, latex=True)
    out.missing = categories.missing(r)
    out.conforms = _canon(out.text) == _canon(out.original) and not out.missing
    for name in out.missing:
        out.problems.append(Problem("REF-MISSING", f"{name.replace('_', ' ').capitalize()} "
                                    "missing: Appendix B needs it and no source gave it.",
                                    name, "error"))
    dropped = _dropped(p, r)
    if dropped:
        out.dropped = "; ".join(dropped)
        out.problems.append(Problem("REF-DROPPED", "Not in the Appendix B layout, so left "
                                    "out: " + out.dropped + ".", "", "warning"))
    out.sources = sorted({s for k, s in r.source.items() if s not in ("text", "")})
    return out


def _record_type(doi: str) -> str:
    from src.annexb.complete import crossref_message
    from src.refcheck import doi as registry

    message = crossref_message(doi)
    if message and message.get("type"):
        return str(message["type"])
    work = registry.lookup(doi)
    return str(work.type) if isinstance(work, registry.Work) and work.type else ""


def format_reference(text: str, *, lookups: bool = True, llm: bool | None = None) -> Outcome:
    """The whole path for one reference: read, complete, write in Appendix B's layout."""
    from src.annexb.complete import complete
    from src.annexb.reader import needs_reader, read_with_model

    p, out = build(text, online=lookups, llm=llm)
    if not out.ref.category and out.ref.doi and lookups:
        kind = _record_type(out.ref.doi)              # the DOI's record says what it is
        if kind:
            p, out = build(text, online=lookups, llm=llm, record_type=kind)
    if needs_reader(p, out) and llm:
        q = read_with_model(text)
        if q is not None:
            p, out = q
    if lookups and out.ref.category:
        complete(p, out, llm=llm)
    return finish(p, out)


__all__ = ["format_reference", "build", "finish", "normalise", "PRINTS"]
