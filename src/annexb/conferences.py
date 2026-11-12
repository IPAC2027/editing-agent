"""JACoW conferences: their labels, where and when they were held, and their papers.

* A label written any way ("IPAC2021", "IPAC 2024", "IPAC ‘24", "Linac’24", "PAC99") is
  read as its series and year and written as Appendix B does: "IPAC’21", "LINAC’24".
* Where and when: the JACoW conference list (zhichu/JACoW-bib, cached by the formatter),
  311 conferences with city, state, country and month.
* A paper: refs.jacow.org, JACoW's own reference database, gives the full author list,
  title, conference, place, date, paper ID, pages and DOI of every published paper.
"""

from __future__ import annotations

import html
import re
import threading
from dataclasses import dataclass, field

#: Series as JACoW writes them.
SERIES = {s.lower(): s for s in (
    "IPAC NAPAC LINAC FEL IBIC ICALEPCS ICAP SRF HB COOL ECRIS PCaPAC SAP RuPAC Cyclotrons "
    "EPAC PAC APAC DIPAC BIW MEDSI ERL FLS HIAT eeFACT EAAC ECLOUD HBEB HF IWBS NAC NB NSS PSC "
    "SOFE TUL XB BLT BIWB EIC MOPAC IBIC").split()}
SERIES["na-pac"] = "NAPAC"
SERIES["napac"] = "NAPAC"

_SERIES_RE = "|".join(sorted((re.escape(s) for s in SERIES), key=len, reverse=True))
#: "IPAC’23", "IPAC'23", "IPAC 2023", "IPAC2023", "IPAC-23", "IPAC ‘24", "PAC99".
LABEL_RE = re.compile(rf"(?<![\w-])({_SERIES_RE})\s*[-'’‘`´]?\s*[‘’']?\s*((?:19|20)\d{{2}}|\d{{2}})"
                      rf"(?![\w])", re.I)


@dataclass
class Label:
    series: str
    year: str           # four digits

    @property
    def text(self) -> str:
        return f"{self.series}’{self.year[2:]}"

    @property
    def doi_id(self) -> str:
        return f"{self.series.upper()}{self.year}"


#: Long names -> series, for "presented at the 6th International Particle Accelerator Conference".
LONG_NAMES = (
    (r"North\s+American\s+Particle\s+Accelerator\s+Conf", "NAPAC"),
    (r"International\s+Particle\s+Accelerator\s+Conf", "IPAC"),
    (r"European\s+Particle\s+Accelerator\s+Conf", "EPAC"),
    (r"Asian\s+Particle\s+Accelerator\s+Conf", "APAC"),
    (r"Russian\s+Particle\s+Accelerator\s+Conf", "RuPAC"),
    (r"Particle\s+Accelerator\s+Conf", "PAC"),
    (r"Linear\s+Accelerator\s+Conf|\bLinac\s+Conf", "LINAC"),
    (r"Free[\s-]+Electron\s+Laser\s+Conf", "FEL"),
    (r"International\s+Beam\s+Instrumentation\s+Conf", "IBIC"),
    (r"Beam\s+Instrumentation\s+Workshop", "BIW"),
    (r"Accelerator\s+and\s+Large\s+Experimental\s+Physics\s+Control", "ICALEPCS"),
    (r"Computational\s+Accelerator\s+Physics", "ICAP"),
    (r"RF\s+Superconductivity", "SRF"),
    (r"High[\s-]+Intensity,?\s+(?:and\s+)?High[\s-]+Brightness\s+Hadron\s+Beams", "HB"),
    (r"Workshop\s+on\s+Beam\s+Cooling", "COOL"),
    (r"Cyclotrons\s+and\s+their\s+Applications", "Cyclotrons"),
    (r"Heavy\s+Ion\s+Accelerator\s+Technology", "HIAT"),
    (r"Energy\s+Recovery\s+Linac", "ERL"),
    (r"Future\s+Light\s+Sources", "FLS"),
    (r"Electron\s+Cyclotron\s+Resonance\s+Ion\s+Sources", "ECRIS"),
    (r"Mechanical\s+Engineering\s+Design\s+of\s+Synchrotron", "MEDSI"),
)


def series_from_name(name: str) -> str:
    for pattern, series in LONG_NAMES:
        if re.search(pattern, name, re.I):
            return series
    return ""


def label_in(text: str) -> tuple[Label, int, int] | None:
    """The first conference label in *text*: (label, start, end)."""
    for m in LABEL_RE.finditer(text):
        series = SERIES[m.group(1).lower()]
        year = m.group(2)
        if len(year) == 2:
            year = ("19" if int(year) > 60 else "20") + year
        if not 1960 <= int(year) <= 2040:
            continue
        # "HB 2" in "HB 2021" is fine; "PAC 1" (a page) is not a label
        return Label(series, year), m.start(), m.end()
    return None


# ---------------------------------------------------------------------------
# Where and when
# ---------------------------------------------------------------------------

_connector = None
_connector_lock = threading.Lock()


def _jacow_list():
    global _connector
    with _connector_lock:
        if _connector is None:
            from jacow_formatter.cache import SqliteCache
            from jacow_formatter.connectors import JacoWConnector

            from src.references import cache_dir, formatter_config
            _connector = JacoWConnector(SqliteCache(cache_dir() / "lookups.sqlite"),
                                        formatter_config())
    return _connector


def venue(label: Label) -> dict:
    """{city, state, country, month} of a JACoW conference, or {} if it is not listed."""
    try:
        meta = _jacow_list().lookup(label.series, label.year) or {}
    except Exception:  # noqa: BLE001 — no list, no venue
        return {}
    out = {k: str(meta[k]) for k in ("city", "state", "country", "month") if meta.get(k)}
    if out.get("city") == "New York City":
        out["city"] = "New York"
    if out.get("month") and not out["month"].endswith(".") and out["month"] != "May":
        out["month"] += "."
    return out


# ---------------------------------------------------------------------------
# refs.jacow.org
# ---------------------------------------------------------------------------

@dataclass
class Paper:
    """One paper as refs.jacow.org lists it."""
    authors: list[str] = field(default_factory=list)   # "A. Alpha" as written there
    et_al: bool = False
    title: str = ""
    label: Label | None = None
    proceedings: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    month: str = ""
    year: str = ""
    paper_id: str = ""
    pages: str = ""
    doi: str = ""


_REFDB = "https://refs.jacow.org/internal/text"


def _parse_refdb(name: str, doi: str) -> Paper | None:
    text = html.unescape(re.sub(r"</?em>", "", name)).strip()
    m = re.match(r"(?P<authors>.*?),\s*“(?P<title>.+)”,\s*in\s+(?P<proc>Proc\..*?\((?P<label>[^)]+)\))"
                 r",\s*(?P<rest>.*)$", text)
    if not m:
        return None
    p = Paper(title=m.group("title").strip().rstrip(","), proceedings=m.group("proc"), doi=doi)
    from src.annexb.names import split_et_al
    authors, p.et_al = split_et_al(m.group("authors"))
    p.authors = [a.strip() for a in re.split(r",\s*(?:and\s+)?|\s+and\s+", authors) if a.strip()]
    found = label_in(m.group("label"))
    p.label = found[0] if found else None
    rest = m.group("rest").rstrip(".")
    pm = re.search(r"\bpp?\.\s*(\d[\w]*(?:\s*[-–]\s*\d[\w]*)?)", rest)
    if pm and "XX" not in pm.group(1):
        p.pages = re.sub(r"\s*[-–]\s*", "-", pm.group(1))
    im = re.search(r"\bpaper\s+([A-Z0-9]+)", rest)
    if im:
        p.paper_id = im.group(1)
    elif doi:
        dm = re.search(r"-([A-Z0-9]+)$", doi, re.I)
        p.paper_id = dm.group(1).upper() if dm else ""
    dm = re.search(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?"
                   r"(?:\s*[-–]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?)?)\s+"
                   r"((?:19|20)\d{2})", rest)
    if dm:
        p.month, p.year = dm.group(1), dm.group(2)
        place = [x.strip() for x in rest[:dm.start()].split(",") if x.strip()]
        from src.annexb.places import country, state
        if place:
            p.country = country(place[-1]) or place[-1]
            if len(place) >= 3 and state(place[-2], p.country):
                p.state, p.city = state(place[-2], p.country), place[-3]
            elif len(place) >= 2:
                p.city = place[-2]
    return p


def refdb_search(query: str, limit: int = 8) -> list[Paper] | None:
    """Papers refs.jacow.org finds for *query*, or None when it does not answer."""
    from src.refcheck import doi as registry

    query = re.sub(r"\s+", " ", query).strip()
    if len(query) < 8:
        return []
    answer = registry._get(_REFDB, params={"query": query[:200]}, service="refs.jacow.org")
    if answer is registry.UNREACHABLE:
        return None
    status, body = answer
    if status != 200 or not isinstance(body, dict):
        return []
    out = []
    for item in (body.get("query") or [])[:limit]:
        paper = _parse_refdb(str(item.get("name") or ""), str(item.get("doi") or "").strip())
        if paper:
            out.append(paper)
    return out


def find_paper(title: str, label: Label | None = None, paper_id: str = "",
               doi: str = "") -> Paper | None:
    """The JACoW paper this reference cites, if refs.jacow.org has it and agrees."""
    from src.refcheck.doi import title_similarity

    candidates: list[Paper] = []
    for query in (title, f"{title} {label.text}" if label else ""):
        if not query:
            continue
        found = refdb_search(query)
        if found:
            candidates += found
        if candidates:
            break
    best, score = None, 0.0
    for paper in candidates:
        if doi and paper.doi and paper.doi.lower() == doi.lower():
            return paper
        if label and paper.label and (paper.label.series.lower() != label.series.lower()
                                      or paper.label.year != label.year):
            continue
        if paper_id and paper.paper_id and paper.paper_id.upper() != paper_id.upper():
            continue
        similar = title_similarity(title, paper.title) if title else 0.0
        if similar > score:
            best, score = paper, similar
    need = 0.85 if (label or paper_id) else 0.93
    return best if best is not None and score >= need else None


__all__ = ["Label", "label_in", "venue", "find_paper", "refdb_search", "Paper", "SERIES",
           "LABEL_RE"]
