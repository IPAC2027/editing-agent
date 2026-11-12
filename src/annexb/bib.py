"""BibTeX: correct each entry's fields so that JACoW's ``jacow.bbx`` prints Appendix B's layout.

A ``\\bibitem`` or a Word reference is rewritten as text; a ``.bib`` entry is not
text, it is data that ``jacow.bbx`` (biblatex, ``\\documentclass[biblatex]{jacow}``)
lays out. So each entry is read into the same fields as a text reference, sorted
into the same 16 kinds, normalised and completed by the same steps, and then its
*fields* are set the way ``jacow.bbx`` needs them for that kind, checked by
compiling with the class itself:

==========================  =================================================================
kind                        entry and fields ``jacow.bbx`` prints in Appendix B's order
==========================  =================================================================
conference                  ``@inproceedings``: booktitle = "Proc. IPAC'23", venue = "City,
                            Country", eventdate = "2023-05", pages, doi (else paper = ID).
                            ``address``/``month`` would put the date after the pages.
conference_unpublished      ``@atevent``: eventtitle = "IPAC'14", venue, eventdate, paper
conference_current          ``@thisevent``: the same; prints "this conference"
journal                     ``@article``: journal = ISO 4 (Annex C), volume, number, pages,
                            date, doi
accepted / submitted        ``@submittedto`` (journal) / ``@submitted``
arxiv                       ``@article`` with no journal: date, doi = 10.48550/arXiv.<id>
online                      ``@online``: title, url (no date)
book_chapter / book         ``@inbook`` (booktitle, editor) / ``@book`` (titleaddon = edition)
report                      ``@techreport``: institution, address, number, date
thesis                      ``@phdthesis`` / ``@mastersthesis``: school, address, year
handbook / manual           ``@manual``: organization, location, date, url
patent                      ``@patent``: location (authority), number, date
unpublished / private       ``@unpublished`` / ``@private``
==========================  =================================================================

``jacow.bbx`` writes every title in sentence case (``\\MakeSentenceCase``), so the
words that keep their capitals (names, acronyms) are braced: ``{LHC}``.
Every change to an entry is one edit, the editor's decision, with what changed
and where each new value came from.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.annexb import categories, conferences
from src.annexb.model import MONTHS, Name, Outcome, Problem, Ref
from src.annexb.names import parse_name
from src.annexb.parse import Parsed

_MONTH_NUMBER = {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)}
_MACRO_MONTHS = {m[:3].lower() for m in MONTHS}


@dataclass
class Field:
    name: str          # lower case
    written: str       # the name as written
    raw: str           # the value as written, with its braces or quotes
    inner: str         # the value without them
    start: int         # of the "name = value" pair
    end: int


@dataclass
class Entry:
    type: str
    key: str
    start: int         # of "@"
    end: int           # after the closing brace
    type_span: tuple[int, int]
    body_start: int
    fields: dict[str, Field] = field(default_factory=dict)

    def get(self, *names: str) -> str:
        for name in names:
            if name in self.fields:
                return self.fields[name].inner
        return ""


# ---------------------------------------------------------------------------
# Reading a .bib file, keeping where everything is
# ---------------------------------------------------------------------------

def _value(source: str, i: int) -> tuple[str, str, int]:
    """(raw, inner, end) of the value starting at *i*."""
    if source[i] == "{":
        depth, j = 0, i
        while j < len(source):
            if source[j] == "{" and source[j - 1:j] != "\\":
                depth += 1
            elif source[j] == "}" and source[j - 1:j] != "\\":
                depth -= 1
                if depth == 0:
                    return source[i:j + 1], source[i + 1:j], j + 1
            j += 1
        return source[i:], source[i + 1:], len(source)
    if source[i] == '"':
        depth, j = 0, i + 1
        while j < len(source):
            if source[j] == "{":
                depth += 1
            elif source[j] == "}":
                depth -= 1
            elif source[j] == '"' and depth == 0 and source[j - 1] != "\\":
                return source[i:j + 1], source[i + 1:j], j + 1
            j += 1
        return source[i:], source[i + 1:], len(source)
    m = re.match(r"[^,}\s][^,}]*", source[i:])
    raw = m.group(0).rstrip() if m else ""
    return raw, raw, i + len(raw)


def parse_bib(source: str) -> list[Entry]:
    entries: list[Entry] = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s{}]*)\s*,", source):
        etype = m.group(1).lower()
        if etype in ("comment", "string", "preamble") or any(e.start <= m.start() < e.end
                                                             for e in entries):
            continue
        e = Entry(type=etype, key=m.group(2), start=m.start(), end=m.end(),
                  type_span=(m.start(1), m.end(1)), body_start=m.end())
        i = m.end()
        while i < len(source):
            ws = re.match(r"[\s,]*", source[i:])
            i += ws.end()
            if i >= len(source) or source[i] == "}":
                e.end = i + 1
                break
            fm = re.match(r"([A-Za-z][\w\-]*)\s*=\s*", source[i:])
            if not fm:
                nxt = source.find("\n", i)
                i = nxt if nxt > i else len(source)
                continue
            start = i
            i += fm.end()
            parts, inner_parts = [], []
            while i < len(source):
                raw, inner, i = _value(source, i)
                parts.append(raw)
                inner_parts.append(inner)
                cat = re.match(r"\s*#\s*", source[i:])
                if not cat:
                    break
                i += cat.end()
            name = fm.group(1)
            e.fields[name.lower()] = Field(name.lower(), name, " # ".join(parts),
                                           "".join(inner_parts), start, i)
        entries.append(e)
    return entries


def _plain(text: str) -> str:
    from src.references import latex_to_plain
    return latex_to_plain(text or "").strip()


def _names(value: str) -> tuple[list[Name], bool]:
    """BibTeX names ("Alpha, A. T. and Beta, B. and others") -> names, et al."""
    parts, depth, cur = [], 0, ""
    for token in re.split(r"(\{|\}|\s+and\s+)", value):
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        if depth == 0 and re.fullmatch(r"\s+and\s+", token or ""):
            parts.append(cur)
            cur = ""
        else:
            cur += token or ""
    parts.append(cur)
    names, et_al = [], False
    for part in (p.strip() for p in parts if p.strip()):
        if part.lower() == "others":
            et_al = True
            continue
        if part.startswith("{") and part.endswith("}"):
            inner = _plain(part)
            person = parse_name(inner)
            from src.annexb.names import _GROUP
            if person and person.given and not _GROUP.search(inner):
                names.append(person)               # "{John T. M. Lyles}": a person, braced
            else:
                names.append(Name(literal=inner))
            continue
        plain = _plain(part)
        if "," in plain:
            from src.annexb.names import _initials
            bits = [b.strip() for b in plain.split(",")]
            family, given = bits[0], bits[-1]
            suffix = bits[1] if len(bits) == 3 else ""        # "Beta, Jr., T. M."
            names.append(Name(given=_initials(given), family=family, suffix=suffix))
        else:
            name = parse_name(plain)
            names.append(name if name else Name(literal=plain))
    return names, et_al


# ---------------------------------------------------------------------------
# An entry as a reference
# ---------------------------------------------------------------------------

_TYPE_KIND = {
    "article": "journal", "inproceedings": "conference", "conference": "conference",
    "proceedings": "conference", "atevent": "conference_unpublished",
    "atconf": "conference_unpublished", "thisevent": "conference_current",
    "thisconf": "conference_current", "submitted": "submitted", "submittedto": "accepted",
    "private": "private", "book": "book", "inbook": "book_chapter",
    "incollection": "book_chapter", "techreport": "report", "report": "report",
    "phdthesis": "thesis", "mastersthesis": "thesis", "thesis": "thesis", "manual": "manual",
    "patent": "patent", "unpublished": "unpublished", "online": "online",
    "electronic": "online", "www": "online",
}


def _date(r: Ref, value: str, source: str = "text") -> None:
    m = re.match(r"((?:19|20)\d{2})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", value or "")
    if m:
        r.put("year", m.group(1), source)
        if m.group(2) and 1 <= int(m.group(2)) <= 12:
            r.put("month", MONTHS[int(m.group(2)) - 1], source)
        if m.group(3):
            r.put("day", str(int(m.group(3))), source)


def to_ref(e: Entry) -> Ref:
    r = Ref()
    get = e.get
    if e.fields.get("author"):
        r.authors, r.et_al = _names(get("author"))
        r.source["authors"] = "text"
    if e.fields.get("editor"):
        r.editors, _ = _names(get("editor"))
        r.source["editors"] = "text"
    r.put("title", _plain(get("title")).strip(" .").strip("“”\""), "text")
    kind = _TYPE_KIND.get(e.type, "")
    note = (get("note") + " " + get("pubstate") + " " + get("howpublished")).lower()
    eprint = get("eprint")
    if (get("archiveprefix") or get("eprinttype")).lower() == "arxiv" or \
            re.search(r"arxiv", get("journal") + get("journaltitle") + note, re.I):
        m = re.search(r"(\d{4}\.\d{4,5})", eprint + " " + get("journal") + " " + note + " " +
                      get("url") + " " + get("doi"))
        if m:
            r.put("arxiv", m.group(1), "text")
    if re.match(r"10\.48550/arxiv\.", get("doi"), re.I) and not r.arxiv:
        r.put("arxiv", re.sub(r"(?i)^10\.48550/arxiv\.", "", get("doi")), "text")
    if kind in ("journal", "") and r.arxiv and not re.search(
            r"[A-Za-z]", re.sub(r"arxiv|preprint|e-?print", "", get("journal", "journaltitle"),
                                flags=re.I)):
        kind = "arxiv"
    if kind in ("journal", "") and re.match(r"10\.18429/JACoW-", get("doi"), re.I):
        kind = "conference"                          # "journal = {JACoW}, volume = {LINAC2024}"
    if kind == "journal" and "submitted" in note:
        kind = "submitted"
    elif kind == "journal" and re.search(r"to be published|accepted|in press", note):
        kind = "accepted"
    if kind == "unpublished" and (get("eventtitle") or get("booktitle")):
        kind = "conference_unpublished"
    if "this conference" in note:
        kind = "conference_current"
    if kind in ("manual", "") and re.search(r"\bhandbook\b", r.title, re.I) and not r.authors:
        kind = "handbook"
    if kind == "report" and not r.authors:
        kind = "technical_report"
    if not kind:                                     # @misc and friends
        if r.arxiv:
            kind = "arxiv"
        elif get("url") and not get("journal", "booktitle", "institution", "publisher"):
            kind = "online"
        elif get("journal", "journaltitle"):
            kind = "journal"
        elif get("booktitle"):
            kind = "conference"
        elif get("institution"):
            kind = "report" if r.authors else "technical_report"
    r.category = kind
    journal = _plain(get("journal", "journaltitle", "shortjournal"))
    if journal and kind in ("journal", "accepted", "submitted"):
        r.put("journal_written", journal, "text")
    event = get("eventtitle") or get("booktitle") or get("series")
    found = conferences.label_in(_plain(event)) if event else None
    if found:
        r.put("conference", found[0].text, "text")
    elif event and kind.startswith("conference"):
        name = _plain(event)
        r.put("proceedings", name if name.startswith("Proc") else f"Proc. {name}", "text")
    if kind == "book_chapter":
        r.put("book", _plain(get("booktitle")), "text")
    if kind == "book":
        r.put("book", r.title, "text")
        r.title = ""
    place = _plain(get("venue") if kind.startswith("conference") else "") or \
        _plain(get("address", "location"))
    if place:
        from src.annexb.parse import _set_place
        _set_place(r, [p for p in place.split(",")])
    _date(r, get("eventdate") if kind.startswith("conference") else "")
    if not r.year:
        _date(r, get("date"))
    if not r.year:
        r.put("year", re.sub(r"\D", "", get("year"))[:4], "text")
    month = get("month").strip().lower()
    if month and not r.month:
        if month[:3] in _MONTH_NUMBER:
            r.put("month", MONTHS[_MONTH_NUMBER[month[:3]] - 1], "text")
        elif month.isdigit() and 1 <= int(month) <= 12:
            r.put("month", MONTHS[int(month) - 1], "text")
    r.put("volume", _plain(get("volume")), "text")
    r.put("issue", _plain(get("number", "issue")) if kind == "journal" else _plain(get("issue")),
          "text")
    pages = re.search(r"[A-Za-z]{0,4}\d+[A-Za-z]?\d*(?:\s*(?:-+|–)\s*[A-Za-z]?\d+[A-Za-z]?\d*)?",
                      _plain(get("pages")))
    r.put("pages", re.sub(r"\s*(?:-+|–)\s*", "-", pages.group(0)) if pages else "", "text")
    from src.refcheck.doi import clean
    doi = clean(_plain(get("doi")))
    url = _plain(get("url"))
    if not doi:
        m = re.search(r"(?:doi\.org/|doi:)(10\.\d{4,9}/\S+)", url)
        doi = clean(m.group(1)) if m else ""
    r.put("doi", doi, "text")
    r.put("url", url if not re.search(r"doi\.org/", url) else "", "text")
    r.put("paper_id", _plain(get("paper", "eid")), "text")
    r.put("institution", _plain(get("institution", "school")), "text")
    r.put("organization", _plain(get("organization")), "text")
    r.put("publisher", _plain(get("publisher")), "text")
    if get("edition") or get("titleaddon"):
        ed = _plain(get("edition") or get("titleaddon"))
        r.put("edition", ed if "ed" in ed else f"{ed} ed.", "text")
    if kind in ("report", "technical_report"):
        r.put("report", _plain(get("number")), "text")
    if kind == "patent":
        r.put("patent", " ".join(x for x in (_plain(get("location", "address")),
                                             _plain(get("number"))) if x), "text")
    if kind == "thesis":
        r.put("thesis", "M.Sc." if e.type == "mastersthesis" or "master" in get("type").lower()
              else "Ph.D.", "text")
    status = {"conference_current": "this conference", "unpublished": "unpublished",
              "submitted": "submitted", "accepted": "accepted", "private": "private"}
    if kind in status:
        r.put("status", status[kind], "text")
    return r


# ---------------------------------------------------------------------------
# What jacow.bbx needs
# ---------------------------------------------------------------------------

def make_sentence_case(title: str) -> str:
    """What ``\\MakeSentenceCase`` makes of a BibTeX title (braced groups are kept)."""
    out, depth, first = [], 0, True
    i = 0
    while i < len(title):
        ch = title[i]
        if ch == "{":
            depth += 1
            out.append(ch)
        elif ch == "}":
            depth -= 1
            out.append(ch)
        elif ch == "\\" and i + 1 < len(title):
            m = re.match(r"\\[A-Za-z]+|\\.", title[i:])
            out.append(m.group(0))
            i += len(m.group(0))
            continue
        elif ch == "$":
            j = title.find("$", i + 1)
            j = len(title) if j < 0 else j
            out.append(title[i:j + 1])
            i = j + 1
            first = False
            continue
        elif ch.isalpha() and depth == 0:
            out.append(ch.upper() if first else ch.lower())
            first = False
        else:
            if ch.isalpha():
                first = False
            out.append(ch)
        i += 1
    return _plain("".join(out))


def braced_title(title: str) -> str:
    """The title for ``jacow.bbx``: every word that keeps a capital, braced."""
    words = re.split(r"(\s+)", title)
    out, first = [], True
    for w in words:
        if not w or w.isspace():
            out.append(w)
            continue
        letters = w[1:] if first else w
        if "$" in w or "\\" in w:
            out.append("{" + w + "}" if re.search(r"[A-Z]", letters) else w)
        elif re.search(r"[A-Z]", letters):
            core = re.match(r"([(“\"]*)(.*?)([)”\".,:;!?]*)$", w)
            out.append(f"{core.group(1)}{{{core.group(2)}}}{core.group(3)}")
        else:
            out.append(w)
        first = False
    # "{Oak} {Ridge} {National} {Laboratory}" -> "{Oak Ridge National Laboratory}"
    return re.sub(r"\}(\s+)\{", r"\1", "".join(out))


def _tex(value: str) -> str:
    from src.annexb.categories import tex_escape
    return tex_escape(value)


def _bib_names(names: list[Name]) -> str:
    out = []
    for n in names:
        if n.literal:
            out.append("{" + n.literal + "}")
        else:
            out.append(f"{n.family}, {n.given}".strip(", ") + (f", {n.suffix}" if n.suffix else ""))
    return " and ".join(out)


def _bbx_initials(given: str) -> str:
    """The initials jacow.bbx prints for a given name: the first letter of each word
    ("J.A." and "AJ" are one word to it, so "J." and "AJ.")."""
    words = [w for w in re.split(r"\s+", given.strip()) if w]
    out = []
    for w in words:
        parts = w.split("-")
        out.append("-".join((p[0] + ".") if p else "" for p in parts if p))
    return " ".join(out)


def _mangled_by_bbx(author_field: str) -> bool:
    """Would jacow.bbx print one of these names wrongly?"""
    from src.annexb.names import _GROUP, _initials
    for raw in re.split(r"\s+and\s+", author_field):
        raw = raw.strip()
        part = _plain(raw).strip()
        if not part or part.lower() == "others":
            continue
        if raw.startswith("{") and raw.endswith("}"):
            person = parse_name(part)
            if person and person.given and not _GROUP.search(part):
                return True                        # "{John T. M. Lyles}" prints in full
            continue
        if "," not in part:
            person = parse_name(part)
            if person and person.family and person.family != part.split()[-1]:
                return True                        # "Signorelli M. G." read as family "G."
        given = part.split(",", 1)[1] if "," in part else " ".join(part.split()[:-1])
        given = given.split(",")[-1].strip()
        if given and _bbx_initials(given) != _initials(given):
            return True
    return False


def _ymd_of(value: str) -> str:
    """"2023-10-09/2023-10-13" -> "2023-10" (when it starts and ends in one month)."""
    m = re.match(r"((?:19|20)\d{2})(?:-(\d{2}))?(?:-\d{2})?(?:/((?:19|20)\d{2})-(\d{2}))?", value or "")
    if not m:
        return ""
    if m.group(3) and (m.group(3), m.group(4)) != (m.group(1), m.group(2)):
        return ""
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


def _ymd(r: Ref) -> str:
    if not r.year:
        return ""
    if r.month:
        first = r.month.split("-")[0]
        number = _MONTH_NUMBER.get(first[:3].lower())
        if number:
            return f"{r.year}-{number:02d}"
    return r.year


def target(r: Ref, e: Entry, title_written: str) -> tuple[str, dict[str, str], set[str]]:
    """(entry type, fields to set, fields to remove) for ``jacow.bbx``."""
    k = r.category
    place = ", ".join(x for x in (r.city, r.state, r.country) if x)
    pages = r.pages.replace("-", "--")
    title = title_written
    if k in ("online", "manual", "handbook", "technical_report") and r.title:
        title = "{" + _tex(r.title) + "}"             # a name: printed as written
    sets: dict[str, str] = {}
    drop: set[str] = set()
    if r.title and k not in ("book", "private"):
        sets["title"] = title
    if pages and e.get("pages") and not re.fullmatch(r"[\w\-–]+", e.get("pages").replace(" ", "")):
        sets["pages"] = pages                          # "1270-1272 vol.2": the pages only
    if k == "conference":
        etype = "inproceedings"
        if r.conference:
            sets["booktitle"] = f"Proc. {r.conference.replace('’', chr(39))}"
        elif r.proceedings:
            sets["booktitle"] = _tex(r.proceedings)
        if place:
            sets["venue"] = _tex(place)
        if _ymd(r) and _ymd_of(e.get("eventdate")) != _ymd(r):
            sets["eventdate"] = _ymd(r)
        if pages:
            sets["pages"] = pages
        if r.doi:
            sets["doi"] = r.doi
        elif r.paper_id:
            sets["paper"] = r.paper_id
            drop |= {"url"}                            # no DOI: the paper ID, never a web address
        drop |= {"volume", "maintitle"}                # printed after "in Proc. …"
    elif k in ("conference_unpublished", "conference_current"):
        etype = "atevent" if k == "conference_unpublished" else "thisevent"
        if r.conference:
            sets["eventtitle"] = r.conference.replace("’", "'")
        if place:
            sets["venue"] = _tex(place)
        if _ymd(r) and _ymd_of(e.get("eventdate")) != _ymd(r):
            sets["eventdate"] = _ymd(r)
        if r.paper_id:
            sets["paper"] = r.paper_id
        drop |= {"journal", "journaltitle", "shortjournal", "doi", "url", "pubstate", "type"}
    elif k == "journal":
        etype = "article"
        if r.journal:
            field_name = "journaltitle" if ("journaltitle" in e.fields and
                                            "journal" not in e.fields) else "journal"
            sets[field_name] = _tex(r.journal)
            if e.get("shortjournal") and _plain(e.get("shortjournal")) != r.journal:
                drop |= {"shortjournal"}               # printed instead of the journal
        if r.volume:
            sets["volume"] = r.volume
        if r.issue and not e.get("issue"):
            sets["number"] = r.issue
        if pages:
            sets["pages"] = pages
        if r.doi:
            sets["doi"] = r.doi
        else:
            drop |= {"url"}                            # a journal article has no web address
    elif k == "accepted":
        etype = "submittedto"
        if r.journal:
            sets["journal"] = _tex(r.journal)
        drop |= {"pubstate", "type"}
    elif k == "submitted":
        etype = "submitted"
        drop |= {"journal", "journaltitle", "shortjournal", "pubstate", "type"}
    elif k == "arxiv":
        etype = "article"
        if _ymd(r):
            sets["date"] = _ymd(r)
            drop |= {"year", "month"}
        if r.doi:
            sets["doi"] = r.doi
        drop |= {"journal", "journaltitle", "shortjournal", "volume", "number", "issue",
                 "pages"}
    elif k == "online":
        etype = "online"
        if r.url:
            sets["url"] = r.url
        drop |= {"year", "date", "month"}
    elif k == "book_chapter":
        etype = "inbook"
        if r.book:
            sets["booktitle"] = "{" + _tex(r.book) + "}"
        if place:
            sets["location"] = _tex(place)
            drop |= {"address"}
        if pages:
            sets["pages"] = pages
    elif k == "book":
        etype = "book"
        if r.book:
            sets["title"] = "{" + _tex(r.book) + "}"
        if r.edition:
            sets["titleaddon"] = r.edition
            drop |= {"edition"}
        if place:
            sets["location"] = _tex(place)
            drop |= {"address"}
    elif k in ("report", "technical_report"):
        etype = "techreport" if r.report else "report"   # @techreport prints "Rep." even alone
        if place:
            sets["address"] = _tex(place)
            drop |= {"location"}
        if r.report:
            sets["number"] = _tex(r.report)
        drop |= {"type"}
    elif k == "thesis":
        etype = "mastersthesis" if r.thesis == "M.Sc." else "phdthesis"
        school = ", ".join(x for x in (r.department, r.institution) if x)
        if school:
            sets["school"] = "{" + _tex(school) + "}"
            drop |= {"institution"}
        if place:
            sets["address"] = _tex(place)
    elif k in ("handbook", "manual"):
        etype = "manual"
        if place:
            sets["location"] = _tex(place)
            drop |= {"address"}
    elif k == "patent":
        etype = "patent"
    elif k == "private":
        etype = "private"
        drop |= {"title"}
    else:
        etype = "unpublished"
        drop |= {"journal", "journaltitle", "eventtitle", "pubstate", "type", "paper", "eid"}
    if r.year and k not in ("arxiv", "online") and "eventdate" not in sets and \
            not e.get("date") and not e.get("eventdate"):
        sets.setdefault("year", r.year)
        if r.month and k in ("journal", "report", "technical_report", "manual", "handbook",
                              "private", "patent"):
            sets["month"] = str(_MONTH_NUMBER.get(r.month.split("-")[0][:3].lower(), ""))
    if r.et_al and len(r.authors) > 2 and e.get("author"):
        # three names and "others" print all three before "et al."; Table 2 wants the first
        sets["author"] = _bib_names(r.authors[:1]) + " and others"
    elif e.get("author") and r.authors and _mangled_by_bbx(e.get("author")):
        # "Holmes, J.A." would print "J. Holmes", "Kutsaev, SV" "SV. Kutsaev"
        sets["author"] = _bib_names(r.authors) + (" and others" if r.et_al else "")
    elif r.et_al and len(r.authors) <= 6 and r.authors and not e.get("author").strip().endswith(
            "others"):
        sets["author"] = _bib_names(r.authors) + " and others"
    elif not r.et_al and r.source.get("authors") not in ("text", None):
        sets["author"] = _bib_names(r.authors)        # the list written out from a registry
    return etype, {k2: v for k2, v in sets.items() if v}, drop


def _same(a: str, b: str) -> bool:
    return re.sub(r"\s+", " ", a).strip() == re.sub(r"\s+", " ", b).strip()


def rewrite(source: str, e: Entry, etype: str, sets: dict[str, str], drop: set[str]) -> str:
    """The entry with its fields set and dropped; the order and the rest kept as written."""
    def changed(name: str, f: Field) -> bool:
        return name in sets and not (_same(f.inner, sets[name]) or (
            name != "title" and _same(_plain(f.inner), _plain(sets[name]))))

    removed = [n for n in e.fields if n in drop and n not in sets]
    added = [n for n in sets if n not in e.fields]
    if not removed and not added:
        # values only: replace them in place, nothing else moves
        text, base = source[e.start:e.end], e.start
        pieces = [(f.start, f.end, f"{f.written} = {{{sets[n]}}}")
                  for n, f in e.fields.items() if changed(n, f)]
        if etype != e.type:
            pieces.append((e.type_span[0], e.type_span[1], etype))
        for a, b, new in sorted(pieces, key=lambda x: -x[0]):
            text = text[:a - base] + new + text[b - base:]
        return text
    first = next(iter(e.fields.values()), None)
    indent = "  "
    if first:
        line_start = source.rfind("\n", 0, first.start) + 1
        lead = source[line_start:first.start]
        indent = lead if lead and lead.isspace() else "  "
    lines = []
    for name, f in e.fields.items():
        if name in removed:
            continue
        lines.append(indent + (f"{f.written} = {{{sets[name]}}}" if changed(name, f)
                               else source[f.start:f.end].strip()))
    lines += [f"{indent}{name} = {{{sets[name]}}}" for name in added]
    return f"@{etype}{{{e.key},\n" + ",\n".join(lines) + "\n}"


# ---------------------------------------------------------------------------
# The edits
# ---------------------------------------------------------------------------

@dataclass
class EntryResult:
    key: str
    entry: Entry
    outcome: Outcome
    after: str            # the entry rewritten
    expected: str         # Appendix B's text, what jacow.bbx should print


def check_entries(source: str, *, lookups: bool = True, llm: bool | None = None
                  ) -> list[EntryResult]:
    from src.annexb.complete import complete
    from src.annexb.engine import _normalised, finish, normalise

    results: list[EntryResult] = []
    for e in parse_bib(source):
        r = to_ref(e)
        out = Outcome(original=source[e.start:e.end], ref=r, category=r.category)
        if not r.category:
            out.problems.append(Problem("REF-KIND", "Could not tell which kind of reference "
                                        f"@{e.type}{{{e.key}}} is; left as written.",
                                        severity="error"))
            results.append(EntryResult(e.key, e, out, source[e.start:e.end], ""))
            continue
        out.raw = r.copy()
        normalise(r, out, online=lookups, llm=llm)
        p = Parsed(ref=r, title_quoted=True, authors_ok=True)
        if lookups:
            complete(p, out, llm=llm)
        finish(p, out)
        out.conforms = False
        title_bib = e.get("title")
        if r.title and _plain(make_sentence_case(title_bib)) != r.title:
            title_bib = braced_title(_tex(r.title))
        etype, sets, drop = target(r, e, title_bib)
        after = rewrite(source, e, etype, sets, drop)
        said = []
        if etype != e.type:
            said.append(f"@{e.type} → @{etype}")
        for name, value in sets.items():
            f = e.fields.get(name)
            if f is None:
                said.append(f"{name} = {{{value}}} added")
            elif not (_same(f.inner, value) or (name != "title" and _same(_plain(f.inner),
                                                                          _plain(value)))):
                said.append(f"{name} → {{{value}}}")
        said += [f"{name} removed" for name in drop if name in e.fields and name not in sets]
        out.changes = said + out.changes
        if r.category == "technical_report":
            out.problems.append(Problem("BIB-LAYOUT", "jacow.bbx prints a report's title in "
                                        "quotes; Appendix B's technical report has none.",
                                        severity="info"))
        if r.category == "patent" and r.day:
            out.problems.append(Problem("BIB-LAYOUT", "jacow.bbx prints a patent's date without "
                                        "the day.", severity="info"))
        results.append(EntryResult(e.key, e, out, after, out.text or ""))
    return results


def bib_edits(source: str, file: str = "", *, lookups: bool = True, llm: bool | None = None,
              records: list[dict] | None = None):
    """One edit per entry whose fields must change for jacow.bbx to print Appendix B.

    *records*, when given, receives one :func:`src.references.reference_record`
    per entry (with its span and the rewritten entry), for the desk.
    """
    from src.edits import Confidence, Edit, Evidence, Tier
    from src.models import Finding, Severity
    from src.references import reference_record

    edits, findings = [], []
    for n, res in enumerate(check_entries(source, lookups=lookups, llm=llm), start=1):
        e, out = res.entry, res.outcome
        label = f"Reference {{{e.key}}}"
        if records is not None:
            records.append(reference_record(
                None, outcome=out, n=n, key=e.key, origin="bib",
                source=source[e.start:e.end], start=e.start, end=e.end,
                entry=res.after, file=file,
                line=source.count("\n", 0, e.start) + 1))
        for problem in out.problems:
            findings.append(Finding(
                check_id=problem.code, line=None,
                severity=Severity.WARNING if problem.severity in ("error", "warning")
                else Severity.INFO,
                message=f"{label}: {problem.message}", original=source[e.start:e.end][:240]))
        before = source[e.start:e.end]
        if res.after == before:
            continue
        kind = categories.CATEGORIES[out.category].name.lower() if out.category else "reference"
        said = "; ".join(dict.fromkeys(out.changes)) or "fields set for jacow.bbx"
        edits.append(Edit(
            check_id="BIB-ANNEXB-01", tier=Tier.SUGGEST, confidence=Confidence.LIKELY,
            file=file, start=e.start, end=e.end, before=before, after=res.after,
            message=(f"{label}: fields set so that jacow.bbx prints Appendix B's layout for "
                     f"{kind}: {said}. It prints: {out.text}"),
            rule="JACoW style guide, Appendix B",
            evidence=Evidence(source="crossref" if out.sources else "local-rule",
                              detail=("values from " + ", ".join(out.sources)) if out.sources
                              else "Appendix B template, jacow.bbx field conventions")))
    return edits, findings


# ---------------------------------------------------------------------------
# Checking by compiling with the JACoW class
# ---------------------------------------------------------------------------

def _biber() -> str | None:
    """biber, or its arm64 binary unpacked by hand (TeX Live's universal binary unpacks
    itself with lipo, which fails on some Macs)."""
    exe = shutil.which("biber")
    if not exe:
        return None
    try:
        ok = subprocess.run([exe, "--version"], capture_output=True, timeout=60).returncode == 0
    except Exception:  # noqa: BLE001
        ok = False
    if ok:
        return exe
    from src.references import cache_dir
    thin = cache_dir() / "biber-arm64"
    if not thin.exists() and shutil.which("lipo"):
        subprocess.run(["lipo", exe, "-thin", "arm64", "-output", str(thin)],
                       capture_output=True, timeout=120)
    return str(thin) if thin.exists() else None


def render_with_jacow(bib_text: str) -> dict[str, str] | None:
    """What ``\\documentclass[biblatex]{jacow}`` prints for each entry, or None without TeX."""
    lualatex, biber = shutil.which("lualatex"), _biber()
    pdftotext = shutil.which("pdftotext")
    if not (lualatex and biber and pdftotext):
        return None
    assets = Path(__file__).resolve().parents[2] / "assets" / "jacow"
    keys = [e.key for e in parse_bib(bib_text)]
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for f in assets.glob("jacow.*"):
            shutil.copy(f, d / f.name)
        (d / "refs.bib").write_text(bib_text, encoding="utf-8")
        cites = "".join(f"\\item[{k}] \\fullcite{{{k}}}\n" for k in keys)
        (d / "t.tex").write_text(
            "\\documentclass[a4paper,biblatex]{jacow}\n\\addbibresource{refs.bib}\n"
            "\\begin{document}\n\\nocite{*}\n\\printbibliography\n\\end{document}\n",
            encoding="utf-8")
        for step in ([lualatex, "-interaction=nonstopmode", "t.tex"], [biber, "t"],
                     [lualatex, "-interaction=nonstopmode", "t.tex"],
                     [lualatex, "-interaction=nonstopmode", "t.tex"]):
            subprocess.run(step, cwd=d, capture_output=True, timeout=300)
        bbl = (d / "t.bbl")
        pdf = d / "t.pdf"
        if not pdf.exists() or not bbl.exists():
            return None
        order = re.findall(r"\\entry\{([^}]*)\}", bbl.read_text(encoding="utf-8", errors="replace"))
        text = subprocess.run([pdftotext, "-raw", str(pdf), "-"], capture_output=True,
                              text=True).stdout
    text = text.split("REFERENCES", 1)[-1]
    text = re.sub(r"-\n(?=[a-z])", "", text)            # hyphenation at line ends
    items = re.split(r"\n?\[(\d+)\]\s", text)
    out = {}
    for i in range(1, len(items) - 1, 2):
        n = int(items[i]) - 1
        if 0 <= n < len(order):
            out[order[n]] = re.sub(r"\s+", " ", items[i + 1]).strip()
    del cites
    return out


__all__ = ["parse_bib", "to_ref", "check_entries", "bib_edits", "render_with_jacow",
           "make_sentence_case", "braced_title"]
