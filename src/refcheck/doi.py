"""Finding and correcting DOIs: look them up, check them against the reference, never guess.

What NAPAC'25's editors did to DOIs (2265 references, author's original
against their final version): they added one to 260 references that had none,
and corrected 19. The corrections were DOIs cut short (``10.1080/00295450.2021``,
``10.18429/JACoW-HIAT2025``), a part left out (``10.1103/.18.060702``), a typo in
a JACoW paper ID (``THCOBS02`` for ``THCOYBS02``), and another paper's DOI.

A DOI with a typo does not exist, or belongs to another paper, so the way to
correct one is the way to find a missing one: look the reference up by what
it says (title, first author, year, journal, volume, page) and take a DOI
only when its record agrees on all of them. A conference paper and the journal
article with the same title are different works with different DOIs; so are
two editions of a book. When two candidates agree equally, none is taken.

Sources, in order: a JACoW DOI built from the reference's conference and paper
ID (checked with DataCite), Crossref's bibliographic search, DataCite's search
of JACoW's prefix (10.18429), and doi.org to say whether a DOI exists at all.
Answers are cached in the agent's cache folder. A lookup that fails is
"unknown", never "the DOI is wrong".

When the strict search finds nothing, a looser one gives the closest record
(titles 75% alike, at most one thing disagreeing: a year, a page, the kind of
work, the publisher) as a *possible* DOI: always the editor's decision, with
what differs and any other close records named on the card.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from src.refcheck.model import names, split

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
_TIMEOUT = 10.0
_CACHE_DAYS = 30
_MISS_DAYS = 7


# ---------------------------------------------------------------------------
# A DOI's spelling, repaired without asking anyone
# ---------------------------------------------------------------------------

def clean(doi: str) -> str:
    """The DOI without what clung to it: LaTeX, punctuation, an encoded slash."""
    doi = doi.strip()
    doi = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)+", "", doi, flags=re.I)
    doi = doi.replace("%2F", "/").replace("%2f", "/")
    doi = re.sub(r"\\[A-Za-z]+.*$", "", doi)            # "\vskip3mm", "\vtop"
    doi = re.sub(r"\\+$", "", doi)
    doi = re.sub(r",\s*[A-Za-z]+$", "", doi)             # "…07622,journal"
    doi = re.sub(r"/(?:pdf|full|abstract|meta)$", "", doi, flags=re.I)
    doi = doi.rstrip(".,;:")
    while doi.endswith(")") and doi.count("(") < doi.count(")"):
        doi = doi[:-1].rstrip(".,;:")
    return doi


def written_dois(text: str) -> list[tuple[int, int, str]]:
    """(start, end, DOI as written) for each DOI in *text*; "10,1103/…" too."""
    found = []
    for m in re.finditer(r"10[.,]\d{4,9}/[^\s\"<>]+", text):
        raw = m.group(0)
        trimmed = raw.rstrip(".,;:")
        while trimmed.endswith(")") and trimmed.count("(") < trimmed.count(")"):
            trimmed = trimmed[:-1].rstrip(".,;:")
        found.append((m.start(), m.start() + len(trimmed), trimmed))
    return found


# ---------------------------------------------------------------------------
# What the reference says, and what a record says
# ---------------------------------------------------------------------------

def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(text))


@dataclass
class Fields:
    title: str = ""
    surname: str = ""
    year: int | None = None
    volume: str = ""
    page: str = ""
    container: str = ""
    kind: str = ""
    jacow: tuple[str, str, str] | None = None    # (series, year, paper ID)
    arxiv: str = ""
    publisher: str = ""


@dataclass
class Work:
    doi: str
    title: str = ""
    surnames: list[str] = field(default_factory=list)
    year: int | None = None
    container: str = ""
    volume: str = ""
    page: str = ""
    type: str = ""
    source: str = ""
    publisher: str = ""


_PUBLISHERS = ("Wiley", "Springer", "World Scientific", "Elsevier", "CRC", "Cambridge University "
               "Press", "Oxford University Press", "Academic Press", "Addison-Wesley", "McGraw-Hill",
               "Prentice Hall", "Taylor & Francis", "IOP Publishing", "AIP Publishing", "Dover",
               "MIT Press", "Princeton University Press", "Pergamon", "North-Holland", "Birkhäuser")


def fields_of(text: str, kind: str = "") -> Fields:
    """Title, first author's surname, year, journal, volume and page, as written."""
    from src.refcheck.difficulty import kind_of
    from src.refcheck.rules import JACOW_DOI_RE, _conference_re, journal_span
    from src.refcheck.model import Context

    parts = split(text)
    f = Fields(kind=kind or kind_of(text))
    f.title = parts.get(parts.title).strip(" ,.")
    people, _ = names(text, parts.authors)
    if people:
        first = people[0].text
        m = re.match(r"([A-Z][\wÀ-ɏ'’\-]+),\s*[A-Z]\.", first)
        f.surname = m.group(1) if m else first.split()[-1]
    elif parts.authors:
        f.surname = re.split(r"[,\s]", parts.get(parts.authors).strip())[0]
    no_links = re.sub(r"https?://\S+|10[.,]\d{4,9}/\S+", " ", text)
    # Page numbers and ranges are not years ("pp. 1916-1919").
    no_pages = re.sub(r"\bpp?\.\s*[A-Z]?\d+(?:\s*[-\u2013]\s*[A-Z]?\d+)?", " ", no_links)
    no_pages = re.sub(r"\d+\s*[-\u2013]\s*\d+", " ", no_pages)
    years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", no_pages[parts.rest[0]:] if parts.title
                       else no_pages)
    f.year = int(years[-1]) if years else None
    m = re.search(r"\bvol\.\s*(\d+)", text)
    if not m and parts.title:
        # "Phys. Rev. Lett. 104, 174801": the number right after the journal's name.
        m = re.search(r"[A-Za-z.]\s+(\d{1,4})\s*(?:\(\d+\))?\s*[,:]\s*(?:pp?\.\s*)?[A-Z]?\d",
                      no_links[parts.rest[0]:])
        if m and re.fullmatch(r"(?:19|20)\d{2}", m.group(1)):
            m = None                     # "Dec 2020, p. 124801": a year, not a volume
    f.volume = m.group(1) if m else ""
    m = re.search(r"\bpp?\.\s*([A-Z]?\d+)", text)
    f.page = m.group(1) if m else ""
    ctx = Context(text=text, parts=parts, kind=f.kind)
    span = journal_span(ctx)
    if span:
        f.container = text[span[0]:span[1]]
    elif re.search(r"\bProc\b", text):
        m = re.search(r"\bProc\.?\s+(?:of\s+)?([^,]+)", text)
        f.container = ("Proc. " + m.group(1)) if m else "Proc."
    m = re.search(r"(?:\barXiv:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?"
                  r"/\d{7})", text, re.I)
    f.arxiv = m.group(1) if m else ""
    publisher = next((p for p in _PUBLISHERS if re.search(rf"\b{re.escape(p)}\b", text, re.I)), "")
    f.publisher = publisher
    journalish = re.search(r"\b(?:journal|rev|lett|trans|series)\b", _fold(f.container))
    if publisher and not f.volume and not journalish and \
            not re.search(r"\bProc\b|\bvol\.", text) and f.kind in ("", "web", "report", "book"):
        # "…, Wiley, New York, 1993": a book; with a quoted title, perhaps a chapter of one.
        f.kind = "book_chapter" if f.title and re.search(r"\bin\b|;", text[parts.rest[0]:]) \
            else "book"
    if not f.title and f.kind == "book" and parts.authors:
        # Annex B: "A. Alpha, Title of Book. Cambridge, MA, USA: MIT Press, 1986."
        rest = text[parts.authors[1]:].lstrip(" ,")
        m = re.match(r"(.+?)(?:\.\s|,\s*(?:\d+(?:st|nd|rd|th)\s+ed|[A-Z][a-z]+(?:,\s*[A-Z]{2})?"
                     r"(?:,\s*[A-Z][\w ]+)?:|" + "|".join(re.escape(x) for x in _PUBLISHERS) + r"))",
                     rest)
        if m and len(m.group(1).split()) >= 2:
            f.title = m.group(1).strip()
    # A JACoW paper: its conference and its paper ID make its DOI.
    jd = JACOW_DOI_RE.search(text)
    conf = _conference_re().search(text, parts.rest[0] if parts.title else 0)
    paper = None
    for candidate in re.finditer(r"\b(?:paper\s+)?([A-Z]{2,6}\d{1,3}[A-Z]{0,4}\d{0,3})\b(?=[,.\s)]|$)",
                                 text[parts.rest[0]:] if parts.title else text):
        token = candidate.group(1).upper()
        if conf and token.startswith(conf.group(1).upper()) and token[len(conf.group(1)):].isdigit():
            continue                     # "HB2023" is the conference, not the paper
        paper = candidate
        break
    if jd and jd.group(3):
        f.jacow = (jd.group(1), jd.group(2), jd.group(3))
    elif conf and paper and paper.group(1).upper() != conf.group(1).upper():
        year = conf.group(2)
        year = year if len(year) == 4 else (("19" if int(year) > 50 else "20") + year)
        f.jacow = (conf.group(1).upper(), year, paper.group(1).upper())
    return f


def _work_from_crossref(item: dict, source: str = "Crossref") -> Work:
    issued = (item.get("issued") or item.get("published") or {}).get("date-parts") or [[None]]
    year = issued[0][0] if issued and issued[0] else None
    return Work(
        doi=str(item.get("DOI", "")), title=" ".join(item.get("title") or []),
        surnames=[a.get("family") or a.get("name") or "" for a in item.get("author") or []],
        year=int(year) if isinstance(year, int) else None,
        container=" ".join(item.get("container-title") or []),
        volume=str(item.get("volume") or ""), page=str(item.get("page") or
                                                        item.get("article-number") or ""),
        type=str(item.get("type") or ""), source=source,
        publisher=str(item.get("publisher") or ""))


def _work_from_datacite(data: dict) -> Work:
    a = data.get("attributes") or {}
    creators = a.get("creators") or []
    container = (a.get("container") or {}).get("title") or ""
    if not container:
        for item in a.get("relatedItems") or []:
            container = (item.get("titles") or [{}])[0].get("title", "") or container
    return Work(
        doi=str(a.get("doi") or data.get("id") or ""),
        title=((a.get("titles") or [{}])[0] or {}).get("title", ""),
        surnames=[c.get("familyName") or (c.get("name") or "").split(",")[0] for c in creators],
        year=int(a["publicationYear"]) if str(a.get("publicationYear") or "").isdigit() else None,
        container=container, type=str((a.get("types") or {}).get("resourceTypeGeneral") or ""),
        source="DataCite")


# ---------------------------------------------------------------------------
# Does the record belong to the reference?
# ---------------------------------------------------------------------------

def _plain_title(text: str) -> str:
    return re.sub(r"<[^>]*>?", " ", text or "")       # MathML, <i>, a cut-off "<mml:math"


def title_similarity(a: str, b: str) -> float:
    ta, tb = _tokens(_plain_title(a)), _tokens(_plain_title(b))
    if not ta or not tb:
        return 0.0
    sequence = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    overlap = len(set(ta) & set(tb)) / len(set(ta) | set(tb))
    return max(sequence, overlap)


_PROCEEDINGS = re.compile(r"\b(?:proc|proceedings|conference|conf|workshop|symposium|meeting)\b",
                          re.I)


def _kind_conflict(f: Fields, w: Work) -> str:
    """Why the record is another kind of work than the reference ("" if it is not)."""
    # A journal article and a conference paper of the same title are two works.
    journalish = re.search(r"\b(?:Rev|J|Lett|Phys|Sci|Instrum|Instr|Nucl|Commun|Trans|Journal|"
                           r"Letters|Review)\b", f.container)
    journal_ref = f.kind in ("journal", "journal_accepted") or bool(
        f.container and not _PROCEEDINGS.search(f.container) and (f.volume or journalish))
    proceedings_ref = f.kind.startswith("conference") or bool(_PROCEEDINGS.search(f.container))
    record_proc = w.type in ("proceedings-article", "ConferencePaper") or \
        bool(_PROCEEDINGS.search(w.container))
    record_journal = w.type == "journal-article" and not _PROCEEDINGS.search(w.container)
    if journal_ref and record_proc:
        return f"the record is a conference paper ({w.container[:60]})"
    if proceedings_ref and record_journal:
        return f"the record is a journal article ({w.container[:60]})"
    books = ("book", "monograph", "edited-book", "reference-book", "Book", "")
    if f.kind == "book" and w.type not in books:
        return f"the record is a {w.type}"
    if f.kind == "book_chapter" and w.type not in books + ("book-chapter", "BookChapter"):
        return f"the record is a {w.type}"
    if proceedings_ref and w.type in ("report", "posted-content", "dataset", "Report",
                                                 "Preprint", "Dataset", "Software"):
        return f"the record is a {w.type}, not the conference paper"
    if f.publisher and w.publisher and \
            _fold(f.publisher).split()[0] not in _fold(w.publisher):
        return f"the record's publisher is {w.publisher}"
    return ""


def match(f: Fields, w: Work, *, strict: bool = True) -> tuple[bool, str]:
    """Whether *w* is the work *f* describes, and if not, why not.

    *strict* (taking a DOI the author did not give): the title must agree
    closely (or, with no title, volume, page, author and year all agree), and
    nothing the reference says may contradict the record. Otherwise (checking
    the author's own DOI) only a clear disagreement counts against it.
    """
    if strict and not (f.year or f.container or f.volume or f.jacow):
        return False, "the reference gives no year, journal or volume to check against"
    if strict and not f.title and not (w.volume and w.page):
        return False, "with no title, the record must show the volume and page"
    if f.title and w.title:
        similar = title_similarity(f.title, w.title)
        short = len(_tokens(f.title)) < 4
        need = (0.95 if short else 0.85) if strict else 0.5
        if similar < need:
            return False, f"the record's title is “{w.title[:90]}”"
    elif strict and not (f.volume and f.page and f.surname and f.year):
        return False, "the reference gives too little to be sure"
    if f.surname and w.surnames:
        mine = _fold(f.surname)
        if not any(mine == _fold(s) or mine in _fold(s).split() for s in w.surnames if s):
            if strict or not f.title:
                return False, f"the record's first author is {w.surnames[0]}"
    if f.year and w.year and abs(f.year - w.year) > 1:
        return False, f"the record's year is {w.year}"
    if f.volume and w.volume and re.sub(r"\D", "", f.volume) != re.sub(r"\D", "", w.volume):
        return False, f"the record's volume is {w.volume}"
    if f.page and w.page:
        first = re.split(r"[-–]", w.page)[0]
        if re.sub(r"\D", "", f.page) != re.sub(r"\D", "", first):
            return False, f"the record's first page is {first}"
    conflict = _kind_conflict(f, w)
    if strict and conflict:
        return False, conflict
    return True, ""


# ---------------------------------------------------------------------------
# Asking, with a cache
# ---------------------------------------------------------------------------

class _Cache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict | None = None
        self.path: Path | None = None

    def _load(self) -> dict:
        if self.data is None:
            try:
                from src.references import cache_dir
                self.path = cache_dir() / "doi_lookups.json"
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self.data = {}
        return self.data

    def get(self, url: str):
        with self.lock:
            entry = self._load().get(url)
        if not entry:
            return None
        days = _CACHE_DAYS if entry.get("found") else _MISS_DAYS
        return entry if time.time() - entry.get("t", 0) < days * 86400 else None

    def put(self, url: str, status: int, body) -> None:
        with self.lock:
            data = self._load()
            data[url] = {"t": time.time(), "status": status, "body": body,
                         "found": status == 200}
            if self.path:
                try:
                    tmp = self.path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(data), encoding="utf-8")
                    tmp.replace(self.path)
                except OSError:
                    pass


CACHE = _Cache()
UNREACHABLE = object()


def _get(url: str, params: dict | None = None, service: str = "crossref"):
    """(status, JSON body) or UNREACHABLE. Cached by URL and parameters."""
    import httpx

    from src.lookup_status import STATUS

    key = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    hit = CACHE.get(key)
    if hit:
        return hit["status"], hit["body"]
    agent = "jacow-prescreen"
    email = os.getenv("CROSSREF_EMAIL", "").strip()
    if email and "crossref" in url:
        agent += f" (mailto:{email})"
    with STATUS.attempt(service) as outcome:
        try:
            resp = httpx.get(url, params=params, timeout=_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": agent, "Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001 — no answer is not a "no"
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return UNREACHABLE
        if resp.status_code not in (200, 404):
            outcome.failed(f"HTTP {resp.status_code}")
            return UNREACHABLE
        outcome.succeeded()
    try:
        body = resp.json() if resp.status_code == 200 else None
    except ValueError:
        body = None
    CACHE.put(key, resp.status_code, body)
    return resp.status_code, body


def lookup(doi: str):
    """The record of *doi* (a :class:`Work`), None if no registry knows it, or UNREACHABLE."""
    doi = clean(doi)
    if not DOI_RE.fullmatch(doi):
        return None
    reached = False
    if not doi.lower().startswith(("10.18429/", "10.48550/")):
        answer = _get(f"https://api.crossref.org/works/{doi}")
        if answer is not UNREACHABLE:
            reached = True
            status, body = answer
            if status == 200 and body:
                return _work_from_crossref(body.get("message") or {})
    answer = _get(f"https://api.datacite.org/dois/{doi}", service="datacite")
    if answer is not UNREACHABLE:
        reached = True
        status, body = answer
        if status == 200 and body and body.get("data"):
            return _work_from_datacite(body["data"])
    # Neither knows it: does it exist at all (another registry)?
    answer = _get(f"https://doi.org/api/handles/{doi}", service="doi.org")
    if answer is UNREACHABLE:
        return UNREACHABLE if not reached else None
    status, body = answer
    if status == 200 and body and body.get("responseCode") == 1:
        return Work(doi=doi, source="doi.org")       # exists; nothing to compare with
    return None


def _search_crossref(f: Fields, *, simple: bool = False) -> list[Work]:
    query = " ".join(x for x in ((f.title, f.surname) if simple else
                                 (f.title, f.container, f.surname, str(f.year or ""),
                                  f.volume, f.page)) if x)
    if not query.strip():
        return []
    params = {"query.bibliographic": query[:400], "rows": "6",
              "select": "DOI,title,author,issued,container-title,volume,page,type,"
                        "article-number,publisher"}
    if f.surname:
        params["query.author"] = f.surname
    answer = _get("https://api.crossref.org/works", params=params)
    if answer is UNREACHABLE or answer[0] != 200 or not answer[1]:
        return []
    return [_work_from_crossref(item) for item in
            (answer[1].get("message") or {}).get("items") or []]


def _search_jacow(f: Fields) -> list[Work]:
    """JACoW papers (DOI prefix 10.18429, registered with DataCite) by title."""
    words = [w for w in _tokens(f.title) if len(w) > 2][:12]
    if len(words) < 3:
        return []
    query = "prefix:10.18429 AND titles.title:(" + " AND ".join(words) + ")"
    answer = _get("https://api.datacite.org/dois", params={"query": query, "page[size]": "5"},
                  service="datacite")
    if answer is UNREACHABLE or answer[0] != 200 or not answer[1]:
        return []
    return [_work_from_datacite(d) for d in answer[1].get("data") or []]


def find(f: Fields) -> Work | None:
    """The one DOI a registry gives for *f*, checked against everything it says."""
    if f.jacow:
        series, year, paper = f.jacow
        work = lookup(f"10.18429/JACoW-{series}{year}-{paper}")
        if isinstance(work, Work):
            if not work.title:
                return work              # it exists: the conference and paper ID name it
            if match(f, work)[0]:
                return work
    candidates: list[Work] = []
    if f.title or (f.volume and f.page):
        candidates += _search_crossref(f)
    if f.title and (f.kind.startswith("conference") or f.jacow or
                    re.search(r"\bProc\b", f.container)):
        candidates += _search_jacow(f)
    passing: dict[str, Work] = {}
    for work in candidates:
        if work.doi and match(f, work)[0]:
            passing.setdefault(work.doi.lower(), work)
    if len(passing) == 1:
        return next(iter(passing.values()))
    if len(passing) > 1:
        # Two records that both fit: only the one whose title is clearly
        # closer is taken; a near tie (journal and conference, two editions)
        # is left for the editor.
        ranked = sorted(passing.values(), key=lambda w: title_similarity(f.title, w.title),
                        reverse=True)
        if title_similarity(f.title, ranked[0].title) - title_similarity(f.title, ranked[1].title) > 0.1:
            return ranked[0]
    return None


def display(right: str, written: str = "") -> str:
    """*right* as it should be written: JACoW's own form, else the author's capitals.

    DOIs ignore case, and registries often answer in lower case
    (``jacow-ipac2025-tupm114``, ``physrevstab.2.114202``). Written in the
    author's capitals where the two agree, a correction changes only what was
    wrong, and "PhysRevSTAB" stays as the author and APS write it.
    """
    m = re.fullmatch(r"10\.18429/jacow-([a-z]+)(\d{4})-([a-z0-9]+)", right, re.I)
    if m:
        return f"10.18429/JACoW-{m.group(1).upper()}{m.group(2)}-{m.group(3).upper()}"
    if not written:
        return right
    out = []
    matcher = difflib.SequenceMatcher(None, written.lower(), right.lower(), autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        out.append(written[i1:i2] if tag == "equal" else right[j1:j2])
    return "".join(out)


def loose_match(f: Fields, w: Work) -> tuple[bool, float, list[str]]:
    """A record close enough to show the editor: (shown?, rank, what differs).

    Looser than :func:`match`: a title 60% alike, a year two off, a type or a
    publisher that disagrees are allowed, but each is named, so the editor
    sees exactly why it is only a possible DOI. Titles must be 75% alike, and
    at most one thing may disagree.
    """
    notes: list[str] = []
    similar = title_similarity(f.title, w.title) if (f.title and w.title) else 0.0
    if f.title and w.title:
        if similar < 0.75:
            return False, 0.0, []
        if similar < 0.95:
            notes.append(f"the title is {similar:.0%} alike")
    elif not (f.volume and f.page and w.volume and w.page):
        return False, 0.0, []
    rank = similar
    if f.surname and w.surnames:
        mine = _fold(f.surname)
        if any(mine == _fold(s) or mine in _fold(s).split() for s in w.surnames if s):
            rank += 0.2
        elif similar >= 0.9:
            notes.append(f"the first author is {w.surnames[0]}")
        else:
            return False, 0.0, []
    if f.year and w.year:
        if abs(f.year - w.year) > 2:
            return False, 0.0, []
        if f.year != w.year:
            notes.append(f"the year is {w.year}, not {f.year}")
        else:
            rank += 0.1
    if f.volume and w.volume and re.sub(r"\D", "", f.volume) != re.sub(r"\D", "", w.volume):
        if similar < 0.9:
            return False, 0.0, []
        notes.append(f"the volume is {w.volume}, not {f.volume}")
    if f.page and w.page:
        first = re.split(r"[-\u2013]", w.page)[0]
        if re.sub(r"\D", "", f.page) != re.sub(r"\D", "", first):
            notes.append(f"the first page is {first}, not {f.page}")
            rank -= 0.1
        else:
            rank += 0.1
    conflict = _kind_conflict(f, w)
    if conflict and not conflict.startswith("the record's publisher"):
        notes.append(conflict.replace("the record is", "it is", 1))    # journal vs conference
        rank -= 0.2
    if f.publisher and w.publisher and _fold(f.publisher).split()[0] not in _fold(w.publisher):
        notes.append(f"the publisher is {w.publisher}")
        rank -= 0.1
    if w.type in ("posted-content", "Preprint"):
        rank -= 0.05                     # the published version first, when both fit
    # One thing may disagree (a year, a page, the kind of work); two, and it is
    # most likely another work with a similar title.
    disagreements = sum(1 for n in notes if not n.startswith("the title is"))
    if disagreements > 1:
        return False, 0.0, []
    return True, rank, notes


def find_possible(f: Fields, exclude: set[str] | None = None
                  ) -> tuple[Work | None, list[str], list[str]]:
    """The closest record a looser search gives: (record, what differs, other DOIs)."""
    exclude = {d.lower() for d in exclude or set()}
    candidates: list[Work] = []
    if f.title or (f.volume and f.page):
        candidates += _search_crossref(f)
        if f.title:
            candidates += _search_crossref(f, simple=True)
    if f.title and (f.kind.startswith("conference") or f.jacow or
                    re.search(r"\bProc\b", f.container)):
        candidates += _search_jacow(f)
    ranked: dict[str, tuple[float, Work, list[str]]] = {}
    for work in candidates:
        if not work.doi or work.doi.lower() in exclude:
            continue
        ok, rank, notes = loose_match(f, work)
        if ok and (work.doi.lower() not in ranked or ranked[work.doi.lower()][0] < rank):
            ranked[work.doi.lower()] = (rank, work, notes)
    if not ranked:
        return None, [], []
    order = sorted(ranked.values(), key=lambda r: r[0], reverse=True)
    best = order[0]
    others = [display(r[1].doi) for r in order[1:3]]
    return best[1], best[2], others


def _describe(w: Work) -> str:
    where = ", ".join(x for x in (w.container[:60], str(w.year or "")) if x)
    return f"“{_plain_title(w.title)[:90].strip()}”" + (f" ({where})" if where else "")


# ---------------------------------------------------------------------------
# The verdict on one reference
# ---------------------------------------------------------------------------

@dataclass
class DoiReport:
    status: str            # ok | found | corrected | possible | wrong | unresolved | unknown | none
    written: str = ""      # the DOI as the author wrote it
    doi: str = ""          # the DOI to give (found, corrected or possible)
    source: str = ""
    reason: str = ""
    others: list[str] = field(default_factory=list)   # other close records (possible)


_NO_DOI = re.compile(r"\bpresented at\b|\bthis conference\b|\bunpublished\b|\bsubmitted\b|"
                     r"\bprivate communication\b|\bin preparation\b|\bto be published\b", re.I)


def check(text: str, kind: str = "") -> DoiReport:
    """Is the reference's DOI right, and if it has none, is there one?"""
    f = fields_of(text, kind)
    written = written_dois(text)
    if written:
        given = written[-1][2]
        doi = clean(given.replace("10,", "10.", 1))
        work = lookup(doi)
        if work is UNREACHABLE:
            return DoiReport("unknown", given)
        if isinstance(work, Work):
            ok, why = match(f, work, strict=False) if work.title else (True, "")
            if not ok and work.title and set(_tokens(_plain_title(work.title))) <= set(_tokens(text)):
                ok = True                # "…, Chapter 11- FFAG, Linear": the record is named
            if ok:
                return DoiReport("ok", given, doi if doi != given else "", work.source)
            right = find(f)
            if right and right.doi.lower() != doi.lower():
                shown = display(right.doi, doi)
                return DoiReport("corrected", given, shown, right.source,
                                 f"the cited DOI is another paper's ({why}); {right.source} "
                                 f"gives {shown} for this reference")
            return _possible(f, given, doi, f"the cited DOI is another paper's ({why})") or \
                DoiReport("wrong", given, source=work.source,
                          reason=f"the cited DOI is another paper's: {why}")
        right = find(f)
        if right:
            near = difflib.SequenceMatcher(None, doi.lower(), right.doi.lower()).ratio() > 0.8
            shown = display(right.doi, doi)
            return DoiReport("corrected", given, shown, right.source,
                             f"the cited DOI {doi} does not exist"
                             + (", a typo" if near else "")
                             + f"; {right.source} gives {shown} for this reference")
        return _possible(f, given, doi, f"the cited DOI {doi} does not exist") or \
            DoiReport("unresolved", given,
                      reason=f"the cited DOI {doi} does not exist (no registry knows it)")
    if _NO_DOI.search(text) or f.arxiv or kind in ("web", "private_comm", "unpublished"):
        return DoiReport("none")
    right = find(f)
    if right:
        shown = display(right.doi)
        return DoiReport("found", doi=shown, source=right.source,
                         reason=f"{right.source} gives {shown} for this reference")
    return _possible(f, "", "", "") or DoiReport("none")


def _possible(f: Fields, given: str, doi: str, problem: str) -> DoiReport | None:
    """A looser search's closest record, offered for the editor to check."""
    work, notes, others = find_possible(f, exclude={doi} if doi else None)
    if work is None:
        return None
    shown = display(work.doi, doi)
    reason = (f"{problem}; " if problem else "") + \
        f"possibly {shown}: {work.source}'s closest record is {_describe(work)}"
    if notes:
        reason += " — " + "; ".join(notes)
    if others:
        reason += ". Other close records: " + ", ".join(others)
    return DoiReport("possible", given, shown, work.source, reason, others)
