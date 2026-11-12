"""A reference in plain text -> its fields, the kind of reference it is, and what was left over.

The reference is read as a string in which every recognised piece is masked
once it is taken, so nothing is read twice and whatever is left at the end is
exactly the text no field explains:

1. identifiers, which have unambiguous shapes: DOIs (any form, inside web
   addresses too), web addresses, arXiv identifiers;
2. the title, in any kind of quotes, and the authors before it;
3. words that settle the kind: "this conference", "unpublished", "submitted",
   "to be published", "private communication", "Ph.D. thesis", "patent";
4. the conference ("in Proc. …", "presented at …", a label such as IPAC'23),
   the place (city, state, country), the date, pages, volume, issue, paper ID,
   report number, edition, editors, publisher;
5. what is left, in order, goes to the field the kind of reference has room
   for (the journal's name after the title of an article; the institution
   before the place in a report; the book after "in" in a chapter).

The kind of reference is decided by :mod:`src.annexb.classify`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.annexb import conferences, places
from src.annexb.model import MONTHS, Ref
from src.annexb.names import parse_authors, parse_name

_MONTH = (r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
          r"Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_MONTH_INDEX = {m[:3].lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
_YEAR = r"((?:19|20)\d{2})"
_PUBLISHERS = ("Wiley", "John Wiley", "Springer", "Springer-Verlag", "Elsevier", "CRC Press",
               "Cambridge University Press", "Oxford University Press", "Academic Press",
               "Addison-Wesley", "McGraw-Hill", "Prentice Hall", "Prentice-Hall",
               "Taylor & Francis", "IOP Publishing", "AIP Publishing", "Dover", "MIT Press",
               "Princeton University Press", "Pergamon", "North-Holland", "Birkhäuser",
               "World Scientific", "IEEE Press", "Wiley-VCH", "Artech House", "Butterworth",
               "Clarendon Press", "Plenum", "Kluwer", "De Gruyter", "SPIE", "Morgan Kaufmann",
               "O'Reilly", "Pearson", "Cengage", "Benjamin Cummings", "Harper", "Ellipses")
_PUBLISHER_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in sorted(
    _PUBLISHERS, key=len, reverse=True)) + r"|IEEE[\s-]Press|[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*"
    r"[\s-](?:Press|Verlag|Publishing|Publishers))(?:[\s,]+(?:Inc|Ltd|Co|GmbH|Publishers?|"
    r"Publishing|and Sons)\.?)*")


def month_abbr(word: str) -> str:
    return MONTHS[_MONTH_INDEX[word[:3].lower()]]


@dataclass
class Chunk:
    start: int
    end: int
    text: str


@dataclass
class Parsed:
    ref: Ref
    chunks: list[Chunk] = field(default_factory=list)   # text left, in order
    title_quoted: bool = False
    authors_ok: bool = False
    title_end: int = 0                                  # where the title ends
    cues: set[str] = field(default_factory=set)
    dropped: list[str] = field(default_factory=list)    # taken but not kept (URL boilerplate…)
    nim: tuple[int, int] | None = None

    def leftover(self) -> str:
        return ", ".join(c.text for c in self.chunks)


class _Masked:
    def __init__(self, text: str) -> None:
        self.text = text
        self.used = [False] * len(text)

    def view(self) -> str:
        return "".join("\x00" if u else c for c, u in zip(self.text, self.used))

    def take(self, start: int, end: int) -> None:
        for i in range(max(0, start), min(len(self.text), end)):
            self.used[i] = True

    def free(self, start: int = 0) -> list[Chunk]:
        """The text not taken, cut at commas, semicolons and sentence ends."""
        view = self.view()
        out: list[Chunk] = []
        for m in re.finditer(r"[^\x00]+", view[start:]):
            a = start + m.start()
            for piece in re.finditer(r"[^,;]+", m.group(0)):
                text = piece.group(0)
                # A sentence end inside: "Visualization Handbook. Elsevier"
                for p0, p1 in _sentences(text):
                    chunk = text[p0:p1]
                    lead = len(chunk) - len(chunk.lstrip(" .:()[]"))
                    body = _trim(chunk)
                    if re.search(r"[A-Za-z0-9]", body) and body.lower() not in (
                            "and", "in", "pp", "p", "vol", "no", "doi", "url", "online"):
                        s = a + piece.start() + p0 + lead
                        out.append(Chunk(s, s + len(body), body))
        return out


def _trim(chunk: str) -> str:
    body = chunk.strip(" :()[]").lstrip(".")
    stripped = body.rstrip(".")
    last = re.search(r"([^\s(]+)$", stripped)
    if body.endswith(".") and last and (last.group(1).lower() in _ABBREVIATIONS or
                                        re.fullmatch(r"[A-Z]", last.group(1))):
        return stripped.strip() + "."
    return stripped.strip()


_ABBREVIATIONS = {
    "eds", "ed", "no", "vol", "rep", "int", "conf", "proc", "phys", "rev", "lett", "nucl",
    "instrum", "meth", "methods", "res", "sci", "technol", "dept", "univ", "inst", "lab",
    "natl", "nat", "appl", "app", "j", "mod", "opt", "accel", "spec", "top", "trans",
    "commun", "electron", "eng", "mater", "adv", "am", "annu", "inc", "ltd", "co", "st", "mt",
    "vs", "al", "pp", "jr", "sr", "dr", "prof", "jan", "feb", "mar", "apr", "jun", "jul",
    "aug", "sep", "sept", "oct", "nov", "dec", "fig", "eq", "ser", "sect", "symp", "workshop",
    "assoc", "soc", "acad", "comput", "syst", "theor", "exp", "radiat", "supercond", "magn",
    "quantum", "chem", "biol", "math", "stat", "mech", "therm", "vac", "plasma", "part",
    "high", "energy", "ph", "d", "th", "ch", "prog", "jpn", "chin", "eur", "ann", "can",
    "aust", "cryog", "surf", "coat", "sens", "meas", "microw", "propag", "circ", "ind", "med",
    "electr", "semicond", "photon", "quant", "struct", "anal", "environ", "geophys", "astron",
    "astrophys", "atmos", "mag", "rad", "grav", "cosmol", "numer", "ber", "dtsch", "ges", "z",
    "zh", "fiz", "compd", "alloys", "mol", "cond", "lasers", "beam", "instr", "techn", "sect",
    "lab", "ctr", "corp", "assn", "dev", "sol", "appl", "proc", "ieee", "aip", "iop", "spie",
}


def _sentences(text: str) -> list[tuple[int, int]]:
    """Spans of *text* cut at full stops that end a sentence (not "Phys.", not "A.")."""
    out, start = [], 0
    for m in re.finditer(r"\.(?=\s)", text):
        word = re.search(r"([^\s(“\"]+)$", text[start:m.start()])
        w = word.group(1).lower() if word else ""
        if not w or re.fullmatch(r"[a-z]", w) or w in _ABBREVIATIONS or \
                re.fullmatch(r"(?:[a-z]\.)+[a-z]", w):
            continue
        # "Prog. Theor. Exp. Phys.": a short capitalised word followed by another abbreviation
        if word and re.fullmatch(r"[A-Z][a-z]{1,11}", word.group(1)) and \
                re.match(r"\s+[A-Z][a-z]{0,8}\.", text[m.end():]):
            continue
        out.append((start, m.start()))
        start = m.end()
    out.append((start, len(text)))
    return out


# ---------------------------------------------------------------------------
# 1. Identifiers
# ---------------------------------------------------------------------------

_DOI_RE = re.compile(
    r"(?:\[\s*)?(?:https?://)?(?:\b(?:doi|DOI|Doi)\s*[:=]?\s*)?(?:<)?(?:https?://)?(?:dx\.)?"
    r"(?:doi\.org/|doi/|(?:[\w.-]+/)+?(?=10[.,]\d{4,9}/))?(10[.,]\d{4,9}/[^\s\"<>]+)(?:>)?(?:\s*\])?",
    re.I)
_URL_RE = re.compile(r"(?:\[\s*Online\s*\]\.?\s*)?(?:(?:Available|Online|URL)\s*(?:at|from)?\s*:\s*)?"
                     r"(?:<)?((?:https?://|www\.)\S+?)(?:>)?(?=[\s,;]|[.)\]]*(?:\s|$))", re.I)
_ACCESSED_RE = re.compile(r"[\[(]?\s*(?:last\s+)?accessed(?:\s+on)?\s*:?\s*[^)\],;]*[\])]?", re.I)
_ARXIV_RE = re.compile(r"(?:(?:arXiv\s*(?:preprint|e-print)\s*)?arXiv\s*:?\s*|(?:https?://(?:www\.)?)?arxiv\.org/(?:abs|pdf)/)"
                       r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?:\.pdf)?"
                       r"(?:\s*\[[\w.\-]+\])?", re.I)


def _identifiers(m: _Masked, ref: Ref, p: Parsed) -> None:
    from src.refcheck.doi import clean

    view = m.view()
    for match in _DOI_RE.finditer(view):
        doi = clean(match.group(1).replace("10,", "10.", 1))
        if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            continue
        end = match.start(1) + len(match.group(1))
        # what the DOI's "clean" dropped at its end stays in the text ("…\vskip3mm" aside)
        written = match.group(1)
        keep_tail = written[len(written.rstrip(".,;:)")):]
        m.take(match.start(), end - len(keep_tail))
        arx = re.fullmatch(r"10\.48550/arxiv\.(.+)", doi, re.I)
        if arx:
            ref.put("arxiv", arx.group(1), "text")
            p.cues.add("arxiv")
        if ref.doi and ref.doi.lower() != doi.lower():
            p.dropped.append(f"doi:{ref.doi}")
        ref.put("doi", doi, "text")
    view = m.view()
    for match in _ARXIV_RE.finditer(view):
        ref.put("arxiv", match.group(1), "text")
        p.cues.add("arxiv")
        m.take(match.start(), match.end())
    view = m.view()
    for match in _URL_RE.finditer(view):
        url = match.group(1).rstrip(".,;)]")
        if "\x00" in url:
            continue
        arx = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url, re.I)
        if arx:
            ref.put("arxiv", arx.group(1), "text")
            p.cues.add("arxiv")
        elif re.search(r"accelconf\.web\.cern\.ch|jacow\.org/\w+/papers|/PAPERS?/", url, re.I):
            pid = re.search(r"/([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*)\.pdf", url, re.I)
            if pid:
                ref.put("paper_id", pid.group(1).upper(), "text")
            p.cues.add("jacow-url")
            p.dropped.append(url)
            m.take(match.start(), match.start(1) + len(url))
            continue
        if not ref.url and not arx:
            ref.put("url", url, "text")
        elif not arx and url != ref.url:
            p.dropped.append(url)
        m.take(match.start(), match.start(1) + len(url))
    view = m.view()
    for match in _ACCESSED_RE.finditer(view):
        p.dropped.append(match.group(0).strip())
        m.take(match.start(), match.end())
    view = m.view()
    for match in re.finditer(r"\[\s*Online\.?\s*\]\.?|\bAvailable\s*(?:at|from)?\s*:|\bURL\s*:|"
                             r"\bWeb\s*:", view, re.I):
        m.take(match.start(), match.end())
    view = m.view()
    for match in re.finditer(r"\bISBN(?:-1[03])?\s*:?\s*[\dXx][\d\-– Xx]{8,}[\dXx]", view):
        p.dropped.append(match.group(0))
        m.take(match.start(), match.end())
    view = m.view()
    # NIM's full name has commas in it
    nim = re.search(r"Nucl(?:ear|\.)\s+Inst(?:r(?:uments|um)?)?\.?\s+(?:(?:and|&)\s+)?Meth(?:ods|\.)?\s+"
                    r"(?:in\s+)?Phys(?:ics|\.)\s+Res(?:earch|\.)?\s*,?\s*(?:Sect(?:ion|\.)?\s*)?"
                    r"([AB])\b(?:\s*:\s*(?:Accelerators,\s*Spectrometers,\s*Detectors,?\s+and\s+"
                    r"Associated\s+Equipment|Beam\s+Interactions\s+with\s+Materials\s+and\s+Atoms))?",
                    view, re.I)
    if nim:
        ref.put("journal_written", f"Nucl. Instrum. Methods Phys. Res. {nim.group(1).upper()}", "text")
        p.cues.add("journal-name")
        p.nim = (nim.start(), nim.end())
        m.take(nim.start(), nim.end())


# ---------------------------------------------------------------------------
# 2. Title and authors
# ---------------------------------------------------------------------------

_PAIRS = (("“", "”"), ("\"", "\""), ("„", "“"), ("«", "»"), ("``", "''"), ("”", "”"),
          ("“", "\""), ("\"", "”"))


def _quoted_title(view: str) -> tuple[int, int, int, int] | None:
    """(open, inner start, inner end, close end) of the title's quotes."""
    best = None
    for opener, closer in _PAIRS:
        i = view.find(opener)
        while i >= 0:
            j = i + len(opener)
            depth = 0
            k = j
            while k < len(view):
                if opener != closer and view.startswith(opener, k) and opener in "“„«":
                    depth += 1
                elif view.startswith(closer, k):
                    if depth == 0:
                        break
                    depth -= 1
                k += 1
            if k < len(view) and len(view[j:k].split()) >= 1 and "\x00" not in view[j:k]:
                cand = (i, j, k, k + len(closer))
                if best is None or cand[0] < best[0]:
                    best = cand
                break
            i = view.find(opener, i + 1)
    if best:
        return best
    # single curly quotes, only for a title of several words
    m = re.search(r"‘([^’]{8,})’", view)
    if m and len(m.group(1).split()) >= 3:
        return m.start(), m.start(1), m.end(1), m.end()
    return None


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return title.rstrip(" ,;:").rstrip(".") if not title.endswith("..") else title


_CUE_AFTER_TITLE = re.compile(
    r"^\s*(?:in\s+(?:Proc|Proceedings|the\s+[Pp]roceed)|Proc(?:eedings)?\b|presented\s+at|"
    r"(?:Ph\.?\s?D|M\.?\s?Sc?|Master|Doctoral|Diploma|Bachelor)\b|vol\.|Vol\.|"
    r"[A-Z][a-z]{0,10}\.\s+[A-Z][a-z]{0,10}\.|J\.\s|Phys\.|IEEE\b|"
    + _MONTH + r"\b|\(?(?:19|20)\d{2}\b|[A-Z][\w ]+:\s*[A-Z]|" + r"(?:" +
    "|".join(re.escape(p) for p in _PUBLISHERS[:12]) + r"))")


def _looks_like_container(tail: str) -> bool:
    """The next phrase is not more title: a journal and its numbers, a report, a lab."""
    first = re.match(r"[^,\x00]*", tail).group(0)
    if any(p.match(tail.lstrip()) for p in _JOURNAL_NUMBERS):
        return True
    return bool(re.search(r"\b(?:Rep(?:ort)?\.?\s+(?:No\.?\s*)?[A-Z0-9]|Tech(?:nical)?\.?\s+"
                          r"(?:Rep|Note|Memo)|Laboratory|Univ(?:ersity)?\b|Institute|"
                          r"Press\b|Publish|Verlag|Note\s+No)", first)) or \
        bool(re.match(r"\s*[A-Z][\w&. ]+\s\d{1,4}\s*\((?:19|20)\d{2}\)", first))


_DOC_WORDS = re.compile(
    r"\b(?:Handbook|Manual|Report|Guide|Design|Conceptual|Technical|Proposal|Notes?|"
    r"Specification|Standard|Software|Code|Packages?|Library|Toolkit|Documentation|Review|"
    r"Analysis|Overview|Introduction|Theory|Principles|Physics|Engineering|Systems?|Tools?|"
    r"Data|Project|Upgrade|Final|Annual|Status|Program(?:me)?|Plan|Stud(?:y|ies)|"
    r"Accelerators?|Beams?|Source|Facility|Products?|Semiconductor|Laser|Magnet|Model|"
    r"Method|Version|Release|Series|Edition|Volume|Chapter|Section|Appendix|Table|Figure|"
    r"Encyclopedia|Dictionary|Wikipedia|Website|Online|Portal|Database|Archive)\b")


def _plausible_author(token: str, *, full_names_ok: bool) -> bool:
    """A name in an author list with no quoted title after it (stricter than parse_name)."""
    t = re.sub(r"^\s*and\s+", "", token.strip())
    if not t or re.search(r"\d", t) or _DOC_WORDS.search(t) or \
            places.country(t) or re.search(r"\b(?:University|Laboratory|Institute|College|"
                                           r"Universit\w+|Center|Centre|Lab)\b", t):
        return False
    name = parse_name(t)
    if name is None:
        return False
    if name.literal:
        return True
    has_initials = bool(re.search(r"(?:^|\s)[A-Z][a-z]?\.|,\s*[A-Z]\.?\s*$|"
                                  r"\s[A-Z]{1,3}$|^[A-Z]{1,2}\s+[A-Z][a-z]", t))
    if has_initials and re.fullmatch(r"(?:[A-ZÀ-Þ][a-z]?\.\s*-?\s*)+[A-ZÀ-Þ][\w'’À-ɏ\-]+(?:\s+(?:van|von|der|de|"
                                     r"den|del|di|da|le|la)\s*)*(?:\s+[A-ZÀ-Þ][\w'’À-ɏ\-]+)*|"
                                     r"[A-ZÀ-Þ][\w'’À-ɏ\-]+,?\s+(?:[A-Z]\.?\s*)+|[A-Z]{1,2}\s+[A-Z][a-z]+", t):
        return True                   # initials and a family name, whatever the cues say
    if _CUE_AFTER_TITLE.match(t):
        return False                  # "Phys. Rev." is a journal
    if has_initials:
        return True
    words = t.split()
    return full_names_ok and 2 <= len(words) <= 3 and not any(
        w.isupper() and len(w) > 1 for w in words)


def _quoted(m: _Masked, ref: Ref, p: Parsed) -> bool:
    view = m.view()
    q = _quoted_title(view)
    if q:
        o, s, e, c = q
        title = _clean_title(m.text[s:e])
        ref.put("title", title, "text")
        p.title_quoted = True
        p.title_end = c
        m.take(o, c)
        # "Title," (comma inside the quotes) or "Title", — the comma is punctuation either way
        before = m.text[:o]
        names, et_al, ok = parse_authors(before) if before.strip(" ,.;:\x00") else ([], False, True)
        names_ok = ok and (bool(names) or not before.strip(" ,.;:"))
        if before.strip(" ,.;:") and not names:
            p.authors_ok = False
        else:
            ref.authors, ref.et_al = names, et_al
            if names:
                ref.source["authors"] = "text"
            p.authors_ok = names_ok
            m.take(0, o)
        return True
    return False


def _unquoted(m: _Masked, ref: Ref, p: Parsed) -> None:
    """No quotes: an author list, then a title running to the first cue."""
    view = m.view()
    free = view
    pos = 0
    names_end = 0
    tokens = list(re.finditer(r"(?:(?!\s+and\s+)[^,;\x00])+", free))
    full_ok = bool(re.search(r"\band\b|\bet\.?\s*al\b|&", free.split("\x00")[0])) or \
        sum(1 for t in tokens[:4] if parse_name(t.group(0).strip()) is not None) >= 3
    if not full_ok and len(tokens) >= 2:
        # "Arno Vettel, Design study for a compact x-ray source …": a name, then a title
        first, second = tokens[0].group(0).strip(), tokens[1].group(0).strip()
        full_ok = bool(re.fullmatch(r"[A-Z][a-zà-ÿ'’\-]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zà-ÿ'’\-]+", first)) \
            and len(second.split()) >= 4 and sum(w.islower() for w in second.split()) >= 2
    names_text = []
    skip = 0
    for i, tok in enumerate(tokens):
        if skip:
            skip -= 1
            continue
        text = tok.group(0)
        stripped = text.strip()
        if not stripped:
            continue
        lead_etal = re.match(r"(?:and\s+)?et\.?\s*al\.?\s+(?=[A-Z0-9“\"])", stripped)
        if lead_etal and names_text:
            names_text.append("et al.")
            names_end = tok.start() + (len(text) - len(text.lstrip())) + lead_etal.end()
            break
        etal = re.search(r"\s+et\.?\s*al\.?\s*$", stripped)
        if etal and _plausible_author(stripped[:etal.start()], full_names_ok=True):
            names_text.append(stripped)
            names_end = tok.end()
            break
        nxt = tokens[i + 1].group(0).strip() if i + 1 < len(tokens) else ""
        if not names_text and full_ok and re.fullmatch(r"[A-Z][\w'’\-]+", stripped) and \
                re.fullmatch(r"[A-Z][a-z]+(?:-[A-Z]?[a-z]+)?(?:\s+[A-Z]\.?)?", nxt):
            names_text.append(f"{stripped}, {nxt}")           # "Ahrens, James, Berk Geveci, …"
            names_end = tokens[i + 1].end()
            skip = 1
            continue
        # "C. Law. ParaView: An End-User Tool …": a name, a full stop, the title
        lead = re.match(r"\s*((?:and\s+)?[^.]*?(?:\b[A-Z][a-z]+|\bal))\.\s+(?=[A-Z0-9“\"])", text)
        candidate = re.sub(r"^\s*and\s+", "", stripped)
        if re.fullmatch(r"(?:et\.?\s*al\.?|and others)", candidate, re.I):
            names_text.append(stripped)
            names_end = tok.end()
            continue
        if names_text and re.fullmatch(r"(?:Jr|Sr)\.?|II|III|IV", candidate):
            names_text[-1] += f" {candidate}"                 # "T.M. Beta, Jr."
            names_end = tok.end()
            continue
        if _plausible_author(candidate, full_names_ok=full_ok):
            names_text.append(stripped)
            names_end = tok.end()
            continue
        if lead and _plausible_author(lead.group(1), full_names_ok=full_ok):
            names_text.append(lead.group(1).strip())
            names_end = tok.start() + lead.end()
        break
    if names_text:
        names, et_al, ok = parse_authors(", ".join(names_text))
        if names:
            ref.authors, ref.et_al = names, et_al
            ref.source["authors"] = "text"
            p.authors_ok = ok
            m.take(0, names_end)
            pos = names_end
    # the title: from here to a cue (", in Proc.", ". Phys. Rev.", ", 2019")
    rest = m.view()[pos:]
    lead = len(rest) - len(rest.lstrip(" ,.;:"))
    start = pos + lead
    body = m.view()[start:]
    end = None
    sentence_ends = {e for _, e in _sentences(body)[:-1]}
    if not ref.authors:
        # No authors: the title is the first phrase ("SLS-2 Conceptional Design Report, …")
        first = re.match(r"[^,\x00]+", body)
        if first:
            cut = first.end()
            for _, e in _sentences(body[:cut])[:-1]:
                cut = e
                break
            title = body[:cut].strip(" .")
            if title and len(title.split()) >= 1:
                ref.put("title", title, "text")
                p.title_end = start + cut
                m.take(start, start + cut)
        p.title_quoted = False
        return
    for sep in re.finditer(r"(?:,|\.(?=\s)|:(?=\s))\s*", body):
        tail = body[sep.end():]
        if sep.group(0).startswith("."):
            if sep.start() in sentence_ends:
                end = sep.start()
                break
            continue
        if sep.group(0).startswith(":") and not re.match(r"[A-Z][\w ,]*:\s", body[sep.end():]):
            # "ParaView: An End-User Tool" is one title; "New York: Wiley" is not
            if not re.match(r"\s*(?:" + "|".join(re.escape(x) for x in _PUBLISHERS) + ")", tail):
                continue
        if _CUE_AFTER_TITLE.match(tail) or tail.startswith("\x00") or not tail.strip("\x00 .") \
                or _looks_like_container(tail):
            end = sep.start()
            break
    if end is None:
        stop = body.find("\x00")
        end = stop if stop > 0 else len(body.rstrip())
    title = body[:end].strip()
    if any(p.match(body.lstrip()) for p in _JOURNAL_NUMBERS):
        title = ""                     # "New J. Phys. 19, 023020 (2017)" is the journal, not a title
    if title and "\x00" not in title and len(title.split()) >= 2 and \
            not _CUE_AFTER_TITLE.match(title):
        ref.put("title", _clean_title(title), "text")
        p.title_end = start + end
        m.take(start, start + end)
    p.title_quoted = False


# ---------------------------------------------------------------------------
# 3. Words that decide the kind
# ---------------------------------------------------------------------------

_STATUS = (
    ("this conference", r"\bthis\s+(?:conference|workshop|meeting|symposium)\b"),
    ("private", r"\b(?:private|personal)\s+communications?\b"),
    ("pending", r"\bpatent\s+pending\b"),
    ("submitted", r"\bsubmitted(?:\s+(?:for\s+publication|to\s+(?:the\s+)?(?:journal\s+)?"
                  r"[^,\x00]*?(?=,|\.?\s*$|\x00)))?"),
    ("accepted", r"\b(?:to\s+be\s+published(?:\s+in)?|accepted(?:\s+for\s+publication)?"
                 r"(?:\s+(?:in|by))?|in\s+press|forthcoming)\b"),
    ("unpublished", r"\bunpublished\b"),
)
_THESIS = re.compile(r"\b(Ph\.?\s?D\.?|Doctoral|Doctorate|Dr\.|Master(?:'s|’s|s)?|M\.?\s?Sc?\.?|"
                     r"M\.?\s?Eng\.?|Diploma|Bachelor(?:'s|’s)?|B\.?\s?Sc?\.?|Habilitation)\s*"
                     r"(?:thesis|dissertation)\b|\b(?:thesis|dissertation)\b", re.I)


def _kind_words(m: _Masked, ref: Ref, p: Parsed) -> None:
    view = m.view()
    for match in re.finditer(r"\barXiv(?:\s+(?:preprint|e-print))?\b(?!\s*:?\s*\d)", view, re.I):
        m.take(match.start(), match.end())                # "arXiv preprint" with its ID taken
        p.cues.add("arxiv-word")
    view = m.view()
    for status, pattern in _STATUS:
        match = re.search(pattern, view, re.I)
        if match:
            if not ref.status or ref.status == "unpublished":
                ref.put("status", status, "text")
            p.cues.add(status)
            m.take(match.start(), match.end())
            view = m.view()
    match = _THESIS.search(view)
    if match:
        word = (match.group(1) or "").lower().replace(" ", "")
        kind = ("Ph.D." if word.startswith(("ph", "doct", "dr")) else
                "M.Sc." if word.startswith(("master", "m.", "m")) else
                "Diploma" if word.startswith("dipl") else
                "B.Sc." if word.startswith(("bach", "b")) else
                "Habilitation" if word.startswith("habil") else "Ph.D.")
        ref.put("thesis", kind, "text")
        p.cues.add("thesis")
        m.take(match.start(), match.end())
    view = m.view()
    match = re.search(r"\b(?:U\.\s?S\.|US|European|EP|WO|Japanese|JP|German|DE|Chinese|CN|"
                      r"French|FR|British|GB)?\s*Pat(?:ent|\.)(?:\s*(?:No\.?\s*)?[\d,. ]*\d)?(?!\s+pending)", view)
    if match and not ref.title.lower().startswith(match.group(0).lower()):
        ref.put("patent", re.sub(r"\s+", " ", match.group(0)).strip(), "text")
        p.cues.add("patent")
        m.take(match.start(), match.end())
    if re.search(r"\bhandbook\b", ref.title + " " + view, re.I):
        p.cues.add("handbook")
    if re.search(r"\b(?:manual|style guide|user'?s?\s+guide|reference guide)\b",
                 ref.title + " " + view, re.I):
        p.cues.add("manual")


# ---------------------------------------------------------------------------
# 4. Conference, place, date, numbers
# ---------------------------------------------------------------------------

_PROC_RE = re.compile(r"(?:\b[Ii]n\s+)?(?:the\s+)?\b(?:Proc(?:eedings|eeding)?\b\.?)\s*"
                      r"(?:of\s+)?(?:the\s+)?", re.I)
_EVENT_WORD = re.compile(r"\b(?:Conf(?:erence)?|Symp(?:osium)?|Workshop|Meeting|Congress|"
                         r"School|Colloquium|Forum|Summit)\b", re.I)


def _conference(m: _Masked, ref: Ref, p: Parsed) -> None:
    view = m.view()
    jp = re.search(r"\bJACoW\s+Publishing\b", view)
    if jp:
        p.cues.add("proc")
        p.cues.add("jacow")
        m.take(jp.start(), jp.end())
        view = m.view()
    start = p.title_end
    match = re.search(r"\bpresented\s+at\s+(?:the\s+)?", view[start:], re.I)
    proc = _PROC_RE.search(view, start) if not match else None
    head = None
    if match:
        p.cues.add("presented")
        head = (start + match.start(), start + match.end())
    elif proc:
        p.cues.add("proc")
        head = (proc.start(), proc.end())
    else:
        # "in 2012 IEEE 51st Conf. on Decision and Control (CDC)"
        ev = re.search(r"\b[Ii]n\s+((?:the\s+)?[^,\x00]*?" + _EVENT_WORD.pattern + r")", view[start:])
        if ev:
            p.cues.add("proc")
            head = (start + ev.start(), start + ev.start(1))
        elif "jacow" not in p.cues:
            ev = re.search(r"(?:^|[,.]\s*)((?:the\s+)?(?:\d+(?:st|nd|rd|th)\s+)?(?:Int(?:ernational|\.)\s+|"
                           r"IEEE\s+|European\s+|Asian\s+|North\s+American\s+)?"
                           r"(?:Conf(?:erence|\.)|Symp(?:osium|\.)|Workshop)\s+on\s+[^,\x00]+)",
                           view[start:])
            if ev and p.title_quoted:
                p.cues.add("proc")
                head = (start + ev.start(1), start + ev.start(1))
    if head:
        a, b = head
        # the name runs to the next comma, or past it to a ")" that closes a "(" in it
        k = b
        depth = 0
        while k < len(view):
            ch = view[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth <= 0 and depth < 0:
                    break
            elif ch in ",;\x00" and depth <= 0:
                break
            k += 1
        name = m.text[b:k].strip(" .")
        # "EPAC’06 (Edinburgh, UK)": a place in brackets after the label
        paren = re.search(r"\(([^()]*)\)\s*$", name)
        if paren and places.country(paren.group(1).split(",")[-1]) and \
                not conferences.label_in(paren.group(1)):
            name = name[:paren.start()].strip()
        found = conferences.label_in(m.text[b:k])
        if found:
            ref.put("conference", found[0].text, "text")
            p.cues.add("label")
        if name and not (found and re.fullmatch(r"[\w\s'’‘\-`]*", name) and
                         len(name.split()) <= 3):
            # a name written out: kept, with Proc. (Appendix B allows it)
            written = re.sub(r"^(?:the\s+)", "", name, flags=re.I)
            if not match:
                ref.put("proceedings", "Proc. " + written if not written.startswith("Proc")
                        else written, "text")
            else:
                ref.put("proceedings", written, "text")      # the event, for "presented at"
        m.take(a, k)
    if not ref.conference:
        found = conferences.label_in(m.view())
        if found and "\x00" not in m.view()[found[1]:found[2]]:
            ref.put("conference", found[0].text, "text")
            p.cues.add("label")
            m.take(found[1], found[2])


def _place_publisher(m: _Masked, ref: Ref, p: Parsed) -> None:
    """"New York, NY, USA: Wiley" — a place before a publisher (books, Appendix B [21, 22])."""
    view = m.view()
    pub = re.search(r"([^\x00,.;:]+(?:,\s*[^\x00,;:]+){0,2}):\s*([^\x00,;]+?)(?=,|\.|\s*$|\x00)", view)
    if pub and places.country(pub.group(1).split(",")[-1]):
        _set_place(ref, [x.strip() for x in pub.group(1).split(",")])
        who = pub.group(2).strip()
        ref.put("publisher", _publisher(who), "text")
        p.cues.add("publisher")
        p.cues.add("place")
        m.take(pub.start(), pub.end())


def _place(m: _Masked, ref: Ref, p: Parsed) -> None:
    if ref.country:
        return
    chunks = m.free(p.title_end)
    for i, chunk in enumerate(chunks):
        words = chunk.text
        if i >= 1 and re.fullmatch(r"[A-Z]{2}", words) and words in places.US_STATES.values() and \
                _looks_like_place(chunks[i - 1].text) and not any(places.country(c.text) for c in chunks):
            _set_place(ref, [chunks[i - 1].text, words, "USA"])
            ref.source["country"] = "state"
            m.take(chunks[i - 1].start, chunk.end)
            p.cues.add("place")
            return
        land = places.country(words)
        if not land:
            # "IL USA", "Tennessee USA"
            two = re.fullmatch(r"(.+?)\s+(\S+)", words)
            if two and places.country(two.group(2)) and places.state(two.group(1), places.country(two.group(2))):
                parts = [two.group(1), two.group(2)]
                start = chunks[i - 1].start if i >= 1 else chunk.start
                city = chunks[i - 1].text if i >= 1 else ""
                _set_place(ref, ([city] if city else []) + parts)
                m.take(start, chunk.end)
                p.cues.add("place")
                return
            continue
        before = chunks[max(0, i - 2):i]
        parts = [c.text for c in before]
        start = chunk.start
        if parts and places.state(parts[-1], land):
            take = parts[-2:] if len(parts) >= 2 else parts
            start = before[-len(take)].start
            _set_place(ref, take + [words])
        elif parts:
            city = parts[-1]
            # "Nashville Tennessee"
            two = re.fullmatch(r"(.+?)\s+(\w[\w ]*)", city)
            if two and places.state(two.group(2), land):
                _set_place(ref, [two.group(1), two.group(2), words])
            elif _looks_like_place(city):
                _set_place(ref, [city, words])
            else:
                _set_place(ref, [words])
                m.take(chunk.start, chunk.end)
                p.cues.add("place")
                return
            start = before[-1].start
        else:
            _set_place(ref, [words])
        m.take(start, chunk.end)
        p.cues.add("place")
        return


def _looks_like_place(text: str) -> bool:
    return bool(re.fullmatch(r"[A-ZÀ-Þ][\w'’.\-]*(?:\s+[A-Za-zÀ-ÿ][\w'’.\-]*){0,3}", text)) and \
        not re.search(r"\d|\b(?:Proc|Conf|Rev|Phys|Lett|Journal|Univ|Lab|Laboratory|Inc|"
                      r"Press|Report|Rep|Note|Dept|Department|Institute|Center|Centre|Company|"
                      r"Corporation|Corp|Society|Association|Products|Periodicals|Group|Ltd|"
                      r"GmbH|Name)\b|\sof\s", text)


def _set_place(ref: Ref, parts: list[str]) -> None:
    parts = [x.strip(" .()") for x in parts if x and x.strip(" .()")]
    if not parts:
        return
    land = places.country(parts[-1]) or parts[-1]
    ref.put("country", land, "text")
    if len(parts) >= 3:
        st = places.state(parts[-2], land)
        ref.put("state", st or parts[-2], "text")
        ref.put("city", parts[-3], "text")
    elif len(parts) == 2:
        st = places.state(parts[-2], land)
        if st and land in ("USA", "Canada") and len(parts[-2]) == 2:
            ref.put("state", st, "text")
        else:
            ref.put("city", parts[-2], "text")


def _publisher(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,")
    text = re.sub(r",?\s*(?:Inc|Ltd|Co|GmbH|LLC)\.?$", "", text)
    text = re.sub(r"\s+and\s+Sons$", "", text)
    return text


def _date(m: _Masked, ref: Ref, p: Parsed, *, with_month: bool) -> None:
    if ref.year:
        return
    view = m.view()
    patterns = (
        # "19-24 May 2024", "May 19-24, 2024"
        (rf"\b\d{{1,2}}\s*[-–]\s*\d{{1,2}}\s+{_MONTH}\.?,?\s+{_YEAR}", ("m", "y")),
        (rf"\b{_MONTH}\.?\s+\d{{1,2}}\s*[-–]\s*\d{{1,2}},?\s+{_YEAR}", ("m", "y")),
        # "Aug.-Sep. 2023", "Apr.–May 2018"
        (rf"\b{_MONTH}\.?\s*[-–/]\s*{_MONTH}\.?,?\s+{_YEAR}", ("m", "m2", "y")),
        # "Jan. 20, 2016"
        (rf"\b{_MONTH}\.?\s+(\d{{1,2}}),\s+{_YEAR}", ("m", "d", "y")),
        # "20 Jan. 2016"
        (rf"\b(\d{{1,2}})\s+{_MONTH}\.?,?\s+{_YEAR}", ("d", "m", "y")),
        # "October 2021", "Oct. 2021", "August, 2011"
        (rf"\b{_MONTH}\.?,?\s+{_YEAR}", ("m", "y")),
    )
    for pattern, roles in patterns:
        match = re.search(pattern, view)
        if not match:
            continue
        got = dict(zip(roles, match.groups()))
        month = month_abbr(got["m"])
        if got.get("m2"):
            month = f"{month}-{month_abbr(got['m2'])}"
        ref.put("month", month, "text")
        ref.put("year", got["y"], "text")
        if got.get("d"):
            ref.put("day", str(int(got["d"])), "text")
        m.take(match.start(), match.end())
        return
    if with_month:
        return
    # a year alone: the last one not inside a number
    years = [y for y in re.finditer(rf"(?<![\w./-]){_YEAR}(?![\w/-])", view)]
    if years:
        y = years[-1]
        ref.put("year", y.group(1), "text")
        a, b = y.start(), y.end()
        if a > 0 and view[a - 1] == "(" and b < len(view) and view[b] == ")":
            a, b = a - 1, b + 1
        m.take(a, b)


def _numbers(m: _Masked, ref: Ref, p: Parsed) -> None:
    view = m.view()
    match = re.search(r"\bp{1,2}[.,]?\s*([A-Za-z]{0,4}\d+[A-Za-z]?\d*)(?:\s*(?:-|–|—|−|--)\s*"
                      r"([A-Za-z]?\d+[A-Za-z]?\d*))?\b|\bpages?\s+(\d+)\s*(?:-|–)\s*(\d+)\b", view)
    if match:
        first = match.group(1) or match.group(3)
        last = match.group(2) or match.group(4)
        ref.put("pages", f"{first}-{last}" if last and last != first else first, "text")
        m.take(match.start(), match.end())
        p.cues.add("pages")
    view = m.view()
    match = re.search(r"\bArt(?:icle|\.)?\s*(?:no\.?|number|ID)?\s*:?\s*([A-Za-z]?\d[\w]*)", view)
    if match and not ref.pages:
        ref.put("pages", match.group(1), "text")
        m.take(match.start(), match.end())
    view = m.view()
    match = re.search(r"\b(?:[Vv]ol(?:ume)?|[Vv])\s*[.,]?\s*(\d+[A-Z]?)\b", view)
    if match:
        ref.put("volume", match.group(1), "text")
        m.take(match.start(), match.end())
        p.cues.add("volume")
    view = m.view()
    match = re.search(r"\b(?:[Nn]o|[Nn]r|[Ii]ssue|[Ii]ss)\.?\s*(\d+(?:[-–/]\d+)?)\b", view)
    if match:
        ref.put("issue", match.group(1), "text")
        m.take(match.start(), match.end())
    view = m.view()
    match = re.search(r"\bpaper\s+(?:ID\s*:?\s*)?([A-Z][A-Z0-9]{2,11})\b", view)
    if match:
        ref.put("paper_id", match.group(1), "text")
        m.take(match.start(), match.end())
    elif "proc" in p.cues or "presented" in p.cues or "label" in p.cues:
        match = re.search(r"\b((?:MO|TU|WE|TH|FR|SA|SU)[A-Z]{0,6}\d{1,4}[A-Z]?\d{0,2})\b", view)
        if match:
            ref.put("paper_id", match.group(1), "text")
            m.take(match.start(), match.end())
    view = m.view()
    match = re.search(r"\b(\d+(?:st|nd|rd|th))\s+(?:[Ee]d(?:ition)?\.?|[Ee]dition)", view) or \
        re.search(r"\b(First|Second|Third|Fourth|Fifth)\s+[Ee]dition\b", view)
    if match:
        word = match.group(1)
        ordinal = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
                   "fifth": "5th"}.get(word.lower(), word)
        ref.put("edition", f"{ordinal} ed.", "text")
        m.take(match.start(), match.end())
    view = m.view()
    match = re.search(r"(?:\b(?:Tech(?:nical)?\.?\s*)?(?:Rep(?:ort)?\.?|Note|Memo(?:randum)?|"
                      r"Preprint|App\.\s*Note|Application\s+Note)\s*(?:No\.?|Number)?\s*:?\s*)"
                      r"([A-Z0-9][\w./\-]*\d[\w./\-]*)", view) or \
        re.search(r"\b([A-Z]{2,}[A-Z0-9]*(?:[-/][A-Z0-9]+)*[-/]\d[\w\-/]*)\b", view)
    if match and not re.fullmatch(r"10\.\d+.*", match.group(1)):
        ref.put("report", match.group(1).rstrip("."), "text")
        m.take(match.start(), match.end())
        p.cues.add("report")
    view = m.view()
    # "R. Mars, Ed." / "A. Streun, Ed." / "J. Smith and K. Doe, Eds." / "(Ed.)"
    match = re.search(r",?\s*\(?\b(?:Eds?)\.\)?(?=[\s,.\x00]|$)", view)
    if match:
        # the names just before "Ed.", read backwards: "in Title of Book, R. Mars, Ed."
        before = view[:match.start()]
        tokens = list(re.finditer(r"[^,;\x00]+", before))
        start = None
        names_text: list[str] = []
        for tok in reversed(tokens):
            text = re.sub(r"^\s*and\s+", "", tok.group(0).strip())
            if tok.end() < len(before.rstrip()) - 1 and before[tok.end():].strip(" ,") and \
                    start is None:
                break
            if not text or not _plausible_author(text, full_names_ok=True):
                break
            names_text.insert(0, text)
            start = tok.start()
        if names_text and start is not None:
            names, _, ok = parse_authors(", ".join(names_text))
            if names and ok:
                ref.editors = names
                ref.source["editors"] = "text"
                m.take(start, match.end())
                p.cues.add("editors")
    view = m.view()
    pub = _PUBLISHER_RE.search(view)
    if pub and not ref.publisher:
        a = max(view.rfind(",", 0, pub.start()), view.rfind(":", 0, pub.start()),
                view.rfind("\x00", 0, pub.start())) + 1
        b = len(view)
        for stop in (",", "\x00", ". "):
            k = view.find(stop, pub.end())
            if k >= 0:
                b = min(b, k)
        phrase = view[a:b].strip(" .")
        if len(phrase.split()) <= 7 and not re.search(r"\d{4}", phrase):
            lead = view[a:b].find(phrase)
            ref.put("publisher", _publisher(phrase), "text")
            m.take(a + lead, a + lead + len(phrase))
        else:
            ref.put("publisher", _publisher(pub.group(0)), "text")
            m.take(pub.start(), pub.end())
        p.cues.add("publisher")


_JOURNAL_NUMBERS = (
    # "Phys. Rev. Lett. 104, 174801 (2010)", "Rev. Sci. Instr., 73, 2002,888",
    # "Physical Review Letters, 102(11), 114801"
    re.compile(r"^(?P<j>[A-Za-z][^\x00\d]*?)[\s,]+(?P<v>\d{1,4}[A-Z]?)\s*(?:\((?P<n>[\w\-]{1,6})\))?"
               r"\s*[,:]\s*(?:(?P<y>(?:19|20)\d{2})\s*,\s*)?(?:pp?\.?\s*)?(?P<p>[A-Za-z]?\d+[A-Za-z]?\d*"
               r"(?:\s*[-–]\s*[A-Za-z]?\d+)?)"),
    # "Nucl. Instrum. Methods A 600 (2009) 123"
    re.compile(r"^(?P<j>[A-Za-z][^\x00\d]*?)\s+(?P<v>\d{1,4})\s*,?\s*\((?P<y>(?:19|20)\d{2})\)\s*,?\s*"
               r"(?:pp?\.?\s*)?(?P<p>[A-Za-z]?\d+[A-Za-z]?\d*(?:\s*[-–]\s*\d+)?)"),
    # "J. Instrum. 16 (10) T10002", "JINST 19 (2024) 02, P02012"
    re.compile(r"^(?P<j>[A-Za-z][^\x00\d]*?)\s+(?P<v>\d{1,4})\s*\((?P<n>\d{1,3})\)\s*,?\s*"
               r"(?P<p>[A-Z]\d{3,})"),
)


def _journal_numbers(m: _Masked, ref: Ref, p: Parsed) -> None:
    """The journal and its numbers when written without "vol."/"pp."."""
    view = m.view()
    start = p.title_end
    rest = view[start:]
    lead = len(rest) - len(rest.lstrip(" ,.;:\x00"))
    seg_start = start + lead
    seg = view[seg_start:]
    for pattern in _JOURNAL_NUMBERS:
        match = pattern.match(seg)
        if not match:
            continue
        journal = match.group("j").strip(" ,")
        if not journal or conferences.label_in(journal) or re.match(r"(?:in\s+)?Proc", journal) \
                or re.fullmatch(_MONTH + r"\.?", journal):
            continue
        ref.put("journal_written", journal, "text")
        if not ref.volume:
            ref.put("volume", match.group("v"), "text")
        if match.groupdict().get("n") and not ref.issue:
            ref.put("issue", match.group("n"), "text")
        if not ref.pages:
            ref.put("pages", re.sub(r"\s*[-–]\s*", "-", match.group("p")), "text")
        if match.groupdict().get("y") and not ref.year:
            ref.put("year", match.group("y"), "text")
        m.take(seg_start, seg_start + match.end())
        p.cues.add("journal-numbers")
        return


def _clean_label(m: _Masked) -> None:
    """Drop the list number: "[12] A. Alpha …"."""
    match = re.match(r"\s*(?:\[\d+\]|\d{1,3}\.(?=\s+[A-Z]))\s*", m.text)
    if match:
        m.take(0, match.end())


_LOOKALIKE = str.maketrans("\u0410\u0412\u0421\u0415\u041d\u041a\u041c\u041e\u0420\u0422\u0425"
                           "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0405\u0455",
                           "ABCEHKMOPTXaeopcyxijSs")


def _unbracket(m: re.Match) -> str:
    inner = m.group(1)
    parts = [x.strip() for x in inner.split(",")]
    if _PUBLISHER_RE.search(inner) or (len(parts) >= 3 and re.fullmatch(r"(?:19|20)\d{2}", parts[-1])
                                        and places.country(parts[-2])):
        return f", {inner},"
    return m.group(0)


def normalize(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    cyrillic = len(re.findall(r"[\u0400-\u04FF]", text))
    if cyrillic and cyrillic < 0.3 * len(re.findall(r"[A-Za-z\u0400-\u04FF]", text)):
        text = text.translate(_LOOKALIKE)        # "РАС2003", "рр." typed in Cyrillic
    text = re.sub(r"``(.*?)''", "\u201c\\1\u201d", text)
    # "Principles of Lasers (Springer Nature, Cham, Switzerland, 2024)": the book's details
    text = re.sub(r"\s*\(([^()]{3,90}?)\)(?=[\s,.;]|$)", _unbracket, text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def parse(text: str) -> Parsed:
    """Read one reference (plain text) into fields."""
    text = normalize(text)
    m = _Masked(text)
    ref = Ref()
    p = Parsed(ref=ref)
    _clean_label(m)
    _identifiers(m, ref, p)
    quoted = _quoted(m, ref, p)
    _kind_words(m, ref, p)
    if not quoted:
        _unquoted(m, ref, p)
        _kind_words(m, ref, p)
    _conference(m, ref, p)
    _date(m, ref, p, with_month=True)
    _place_publisher(m, ref, p)
    _numbers(m, ref, p)
    _journal_numbers(m, ref, p)
    _place(m, ref, p)
    _date(m, ref, p, with_month=False)
    if not p.title_end and ref.title:
        p.title_end = 0
    p.chunks = m.free(0)
    return p


__all__ = ["parse", "Parsed", "Chunk", "normalize", "month_abbr"]
