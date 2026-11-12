"""Which of Appendix B's 16 kinds a reference is, and where the rest of its words go.

The kind is decided by what the reference says, strongest sign first: the
words Appendix B's own layouts use ("private communication", "this
conference", "presented at", "patent", "thesis", "submitted for publication",
"to be published", "in Proc."), then the shape of what follows the title
(a journal and its volume, a report number, a publisher), then a registry's
record of the DOI, if there is one.
"""

from __future__ import annotations

import re

from src.annexb import places
from src.annexb.parse import Parsed

#: Crossref / DataCite types -> Appendix B kinds.
RECORD_TYPES = {
    "journal-article": "journal", "proceedings-article": "conference",
    "book-chapter": "book_chapter", "book-section": "book_chapter", "book-part": "book_chapter",
    "book": "book", "monograph": "book", "edited-book": "book", "reference-book": "book",
    "report": "report", "report-component": "report", "dissertation": "thesis",
    "posted-content": "arxiv", "Preprint": "arxiv", "ConferencePaper": "conference",
    "JournalArticle": "journal", "Report": "report", "Dissertation": "thesis", "Book": "book",
    "BookChapter": "book_chapter", "Text": "", "standard": "manual",
}

_INSTITUTION = re.compile(r"\b(?:Univ(?:ersity|ersität|ersité|ersidad|ersità)?|Institut[eo]?|"
                          r"College|Laborator(?:y|ies)|Lab|Center|Centre|CERN|SLAC|DESY|GSI|PSI|"
                          r"KEK|BNL|ANL|LBNL|FNAL|Fermilab|JLab|Jefferson|ORNL|LANL|LLNL|TRIUMF|"
                          r"ESRF|ELETTRA|Elettra|Diamond|SOLEIL|MAX IV|RIKEN|IHEP|BINP|JINR|ITER|"
                          r"Synchrotron|Accelerator|Research|Agency|Organi[sz]ation|"
                          r"Corporation|Company|Inc\.?|Ltd\.?|GmbH|Technologies|Facility)\b")
_DEPARTMENT = re.compile(r"\b(?:Dept|Department|Faculty|School of|Div|Division|"
                         r"Fachbereich|Fakultät)\b", re.I)


def classify(p: Parsed, *, record_type: str = "") -> str:
    r, cues = p.ref, p.cues
    journalish = bool(r.journal_written or "journal-numbers" in cues or r.volume)
    if r.status == "private":
        return "private"
    if r.status == "this conference":
        return "conference_current"
    if "presented" in cues:
        return "conference_unpublished"
    if r.status == "pending" or "patent" in cues:
        return "patent"
    if r.thesis:
        return "thesis"
    if r.status == "submitted":
        return "submitted"
    if r.status == "accepted":
        return "accepted"
    if "proc" in cues or (r.conference and not journalish and not r.report):
        return "conference_unpublished" if r.status == "unpublished" else "conference"
    if journalish:
        return "journal"
    if r.arxiv:
        return "arxiv"
    if journalish is False and r.volume == "" and r.journal_written == "":
        pass
    if record_type and RECORD_TYPES.get(record_type):
        kind = RECORD_TYPES[record_type]
        if kind == "report":
            return "report" if r.authors else "technical_report"
        return kind
    if "handbook" in cues and not p.title_quoted and not (r.authors and r.publisher):
        return "handbook"
    if "manual" in cues and not p.title_quoted and not (r.authors and r.publisher):
        return "manual"
    if r.report:
        return "report" if (r.authors and p.title_quoted) else "technical_report"
    if r.editors or (p.title_quoted and _in_chunk(p) and (r.publisher or r.year)):
        return "book_chapter"
    if r.publisher or r.edition:
        return "book_chapter" if (p.title_quoted and _in_chunk(p)) else "book"
    if r.status == "unpublished":
        return "unpublished"
    after = [c for c in p.chunks if c.start >= p.title_end]
    if p.title_quoted and r.authors and any(
            re.search(r"\b(?:Workshop|Conference|Meeting|Symposium|Seminar|Colloquium)\b",
                      c.text) for c in after) and not r.doi:
        return "conference_unpublished"
    if p.title_quoted and r.authors and any(_INSTITUTION.search(c.text) for c in after):
        return "report"
    if r.url and not r.doi:
        return "online"
    if p.title_quoted and _first_after_title(p):
        from src.annexb.journals import annex_c, _key
        first = _first_after_title(p).text
        if _key(first) in annex_c():
            return "journal"
    if r.doi and p.title_quoted and _first_after_title(p) and r.year:
        return "journal"           # "Title", Some Journal, 2021. doi:… — the record decides later
    return ""


def _first_after_title(p: Parsed):
    for chunk in p.chunks:
        if chunk.start >= p.title_end:
            return chunk
    return None


def _in_chunk(p: Parsed):
    for chunk in p.chunks:
        if chunk.start >= p.title_end and re.match(r"in\s+\S", chunk.text):
            return chunk
    return None


def assign(p: Parsed, category: str, original: str) -> None:
    """Give the words left over to the fields this kind of reference has room for."""
    r = p.ref
    left = [c for c in p.chunks]

    def take(chunk) -> str:
        from src.annexb.parse import _trim
        left.remove(chunk)
        return _trim(chunk.text.strip(" ,;:"))

    after = [c for c in left if c.start >= p.title_end]
    if category in ("journal", "accepted") and not r.journal_written and after:
        r.put("journal_written", re.sub(r"^in\s+", "", take(after[0])), "text")
    if category == "journal" and not r.volume:
        for chunk in list(left):                      # "…, Phys. Rev. ST Accel. Beams, 17, p. 034001"
            if re.fullmatch(r"\d{1,4}[A-Z]?", chunk.text) and not re.fullmatch(r"(?:19|20)\d{2}",
                                                                              chunk.text):
                r.put("volume", take(chunk), "text")
                break
    elif category == "book_chapter":
        chunk = _in_chunk(p) or (after[0] if after else None)
        if chunk and chunk in left and not r.book:
            r.put("book", re.sub(r"^in\s+", "", take(chunk)), "text")
    elif category == "book":
        if not r.book:
            r.put("book", r.title, r.source.get("title", "text"))
            r.title = ""
        if not r.publisher and after:
            for chunk in list(after):
                if _INSTITUTION.search(chunk.text) or re.search(r"Press|Verlag|Publish", chunk.text):
                    r.put("publisher", take(chunk), "text")
                    break
    elif category in ("report", "technical_report", "thesis"):
        if category == "technical_report" and not r.title and left:
            r.put("title", take(left[0]), "text")
        for chunk in [c for c in left if c.start >= p.title_end]:
            if category == "thesis" and _DEPARTMENT.search(chunk.text) and not r.department:
                r.put("department", take(chunk), "text")
            elif not r.institution and (_INSTITUTION.search(chunk.text) or
                                        category != "thesis"):
                r.put("institution", take(chunk), "text")
    elif category in ("handbook", "manual"):
        if not r.title and left:
            r.put("title", take(left[0]), "text")
        rest = [c for c in left if c.start >= p.title_end]
        if rest and not r.organization:
            r.put("organization", take(rest[0]), "text")
    elif category == "online":
        if not p.title_quoted:
            # Everything before the web address is its name ("JACoW", "Julia Packages,
            # BenchmarkTools.jl"), whatever the name parser made of it.
            url_at = original.find(r.url) if r.url else -1
            head = original[:url_at] if url_at > 0 else original
            head = re.sub(r"\[\s*Online\s*\]\.?|\bAvailable\s*(?:at|from)?\s*:|\bURL\s*:", "",
                          head, flags=re.I)
            head = re.sub(r"^\s*\[\d+\]\s*", "", head).strip(" ,.;:")
            if head:
                r.authors, r.et_al = [], False
                r.source.pop("authors", None)
                r.put("title", head, "text")
                left.clear()
                r.year = r.month = ""
    elif category == "conference" and not r.conference and not r.proceedings and after:
        chunk = after[0]
        if re.search(r"\b(?:Conf|Symp|Workshop|Meeting)", chunk.text, re.I):
            r.put("proceedings", "Proc. " + take(chunk), "text")
    # a city before the country that the place reader could not tell from a name
    if r.country and not r.city and category in ("conference", "conference_unpublished",
                                                 "conference_current", "report", "thesis"):
        for chunk in list(left):
            if places.state(chunk.text, r.country):
                continue
    r.note = ", ".join(c.text for c in left)
    p.chunks = left


__all__ = ["classify", "assign", "RECORD_TYPES"]
