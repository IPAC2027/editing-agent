"""The 16 kinds of reference in Appendix B of the JACoW style guide, and their exact layouts.

Each kind has a template that writes a reference from its fields exactly as
Appendix B prints its examples: the same fields, in the same order, with the
same words and punctuation. A field the template needs but nobody could supply
is left out of the text and named in ``missing``: the editor sees what is
still needed, never an invented value.

Appendix B's 16 headings, with their examples' numbers:

 1. Paper published in a conference proceedings [1-5]
 2. Unpublished paper from a previous conference [6]
 3. Paper presented at the current conference [7]
 4. Published in a periodical [8-12]
 5. Accepted for publication [15]
 6. Submitted for publication [16]
 7. arXiv preprint [17]
 8. Online source [18-20]
 9. Citations to books: a chapter [21], a book [22]
10. Internal report [23, 24]
11. Technical report [25-27]
12. Thesis [28]
13. Handbook [29, 30]
14. Reference, manual [31]
15. Patents [32]
16. Unpublished work [33] and private communication [34]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from src.annexb.model import PAGE_DASH, Name, Ref


@dataclass(frozen=True)
class Category:
    id: str
    number: int                  # Appendix B's heading, 1-16
    name: str
    example: str                 # Appendix B's own example
    required: tuple[str, ...]    # fields the layout cannot do without
    render: Callable[[Ref, "_Out"], str]


# ---------------------------------------------------------------------------
# Writing the pieces, as plain text or as LaTeX
# ---------------------------------------------------------------------------

class _Out:
    """The pieces of a reference, in plain text (Word, the reference page) or LaTeX."""

    def __init__(self, latex: bool) -> None:
        self.latex = latex

    def text(self, value: str) -> str:
        return tex_escape(value) if self.latex else value

    def italic(self, value: str) -> str:
        value = self.text(value)
        return f"\\emph{{{value}}}" if self.latex else value

    def label(self, label: str) -> str:
        """A conference label: "IPAC’23" in print, "IPAC'23" in LaTeX source (same glyph)."""
        return label.replace("’", "'") if self.latex else label.replace("'", "’")

    def quoted(self, title: str) -> str:
        return f"“{self.text(title)}”" if title else ""

    def name(self, n: Name) -> str:
        return self.text(n.latex()) if self.latex else n.plain()

    def et_al(self) -> str:
        return "\\emph{et al.}" if self.latex else "et al."

    def authors(self, r: Ref) -> str:
        """Appendix B, Table 2: one, two, three to six, more than six authors."""
        names = r.authors
        if not names:
            return ""
        shown = [self.name(n) for n in names]
        if len(names) > 6 or r.et_al:
            if r.et_al and len(names) == 2:          # ">6 but with two primary authors"
                return f"{shown[0]}, {shown[1]}, {self.et_al()}"
            return f"{shown[0]} {self.et_al()}"
        if len(shown) == 1:
            return shown[0]
        if len(shown) == 2:
            return f"{shown[0]} and {shown[1]}"
        return ", ".join(shown[:-1]) + f", and {shown[-1]}"

    def editors(self, r: Ref) -> str:
        if not r.editors:
            return ""
        shown = [self.name(n) for n in r.editors]
        names = shown[0] if len(shown) == 1 else (
            f"{shown[0]} and {shown[1]}" if len(shown) == 2 else
            ", ".join(shown[:-1]) + f", and {shown[-1]}")
        return names + (", Ed." if len(shown) == 1 else ", Eds.")

    def place(self, r: Ref) -> str:
        return ", ".join(self.text(x) for x in (r.city, r.state, r.country) if x)

    def date(self, r: Ref, *, day: bool = False) -> str:
        if not r.year:
            return ""
        if day and r.day and r.month:
            return f"{r.month} {r.day}, {r.year}"
        return f"{r.month} {r.year}" if r.month else r.year

    def pages(self, r: Ref) -> str:
        if not r.pages:
            return ""
        nbsp = "~" if self.latex else " "
        pages = r.pages.replace("–", PAGE_DASH).replace("--", PAGE_DASH)
        return (f"pp.{nbsp}{pages}" if PAGE_DASH in pages or "," in pages
                else f"p.{nbsp}{pages}")

    def doi(self, r: Ref) -> str:
        if not r.doi:
            return ""
        return f" \\doi{{{r.doi}}}" if self.latex else f" doi:{r.doi}"

    def url(self, r: Ref) -> str:
        if not r.url:
            return ""
        return f"\\url{{{r.url}}}" if self.latex else r.url

    def link(self, r: Ref) -> str:
        """After the final full stop: the DOI, else the web address."""
        if r.doi:
            return self.doi(r)
        return f" {self.url(r)}" if r.url else ""

    def proc(self, r: Ref) -> str:
        nbsp = "\\ " if self.latex else " "
        if r.proceedings:
            return self.italic_label(r.proceedings)
        if not r.conference:
            return ""
        inner = f"Proc.{nbsp}{self.label(r.conference)}"
        return f"\\emph{{{inner}}}" if self.latex else inner

    def italic_label(self, value: str) -> str:
        value = self.label(value)
        if not self.latex:
            return value
        return f"\\emph{{{tex_escape(value).replace('. ', '.\\ ')}}}"

    def vol(self, value: str) -> str:
        return f"vol.~{value}" if self.latex else f"vol. {value}"

    def no(self, value: str) -> str:
        return f"no.~{value}" if self.latex else f"no. {value}"


def join(*parts: str) -> str:
    return ", ".join(p for p in parts if p)


def tex_escape(text: str) -> str:
    """LaTeX's special characters escaped, outside $…$ and existing commands."""
    out = []
    for i, piece in enumerate(re.split(r"(\$[^$]*\$)", text)):
        if i % 2:
            out.append(piece)
            continue
        out.append(re.sub(r"(?<!\\)([&%#_])", r"\\\1", piece))
    return "".join(out)


# ---------------------------------------------------------------------------
# The templates
# ---------------------------------------------------------------------------

def _conference(r: Ref, o: _Out) -> str:
    paper = f"paper {r.paper_id}" if r.paper_id and not r.doi else ""
    proc = o.proc(r)
    body = join(o.authors(r), o.quoted(r.title), f"in {proc}" if proc else "", o.place(r),
                o.date(r), paper, o.pages(r))
    return body + "." + o.doi(r)


def _presented(status: str) -> Callable[[Ref, _Out], str]:
    def render(r: Ref, o: _Out) -> str:
        where = (f"presented at {o.label(r.conference)}" if r.conference else
                 f"presented at {o.text(re.sub(r'^Proc\.\s*', '', r.proceedings))}"
                 if r.proceedings else "")
        paper = f"paper {r.paper_id}" if r.paper_id else ""
        return join(o.authors(r), o.quoted(r.title), where, o.place(r), o.date(r), paper,
                    status) + "."
    return render


def _journal(r: Ref, o: _Out) -> str:
    body = join(o.authors(r), o.quoted(r.title), o.italic(r.journal) if r.journal else "",
                o.vol(r.volume) if r.volume else "", o.no(r.issue) if r.issue else "",
                o.pages(r), o.date(r))
    return body + "." + o.doi(r)


def _accepted(r: Ref, o: _Out) -> str:
    return join(o.authors(r), o.quoted(r.title), o.italic(r.journal) if r.journal else "",
                "to be published") + "."


def _submitted(r: Ref, o: _Out) -> str:
    return join(o.authors(r), o.quoted(r.title), "submitted for publication") + "."


def _arxiv(r: Ref, o: _Out) -> str:
    return join(o.authors(r), o.quoted(r.title), o.date(r)) + "." + o.doi(r)


def _online(r: Ref, o: _Out) -> str:
    # "EPICS, https://…": the name as written (jacow.bbx prints an online title unquoted)
    return join(o.authors(r), o.text(r.title or r.organization), o.url(r))


def _chapter(r: Ref, o: _Out) -> str:
    head = join(o.authors(r), o.quoted(r.title), f"in {o.italic(r.book)}" if r.book else "")
    eds = o.editors(r)
    head = join(head, eds) if eds else head + "."
    tail = _publisher(r, o)
    body = (head + " " + join(tail, o.date(r), o.pages(r))).rstrip()
    return body.rstrip(".") + "." + o.link(r)


def _book(r: Ref, o: _Out) -> str:
    head = join(o.authors(r), o.italic(r.book or r.title), r.edition)
    eds = o.editors(r)
    if eds:
        head = join(head, eds)
    tail = join(_publisher(r, o), o.date(r))
    return (head.rstrip(".") + ". " + tail).rstrip() .rstrip(".") + "." + o.link(r)


def _publisher(r: Ref, o: _Out) -> str:
    """"New York, NY, USA: Wiley"."""
    place = o.place(r)
    who = o.text(r.publisher)
    return f"{place}: {who}" if (place and who) else (who or place)


def _report(r: Ref, o: _Out) -> str:
    rep = f"Rep. {o.text(r.report)}" if r.report else ""
    return join(o.authors(r), o.quoted(r.title), o.text(r.institution), o.place(r), rep,
                o.date(r)) + "." + o.link(r)


def _technical_report(r: Ref, o: _Out) -> str:
    rep = f"Rep. {o.text(r.report)}" if r.report else ""
    return join(o.text(r.title), r.edition, o.editors(r), o.text(r.institution), o.place(r),
                rep, o.date(r)) + "." + o.link(r)


def _thesis(r: Ref, o: _Out) -> str:
    kind = f"{r.thesis} thesis" if r.thesis else ""
    return join(o.authors(r), o.quoted(r.title), kind, o.text(r.department),
                o.text(r.institution), o.place(r), o.date(r)) + "." + o.link(r)


def _handbook(r: Ref, o: _Out) -> str:
    body = join(o.text(r.title), r.edition, o.text(r.organization), o.place(r), o.date(r),
                o.pages(r), o.url(r))
    return body if r.url else body + "."


def _manual(r: Ref, o: _Out) -> str:
    return join(o.italic(r.title), o.text(r.organization), o.place(r), o.date(r)) + "." + \
        o.link(r)


def _patent(r: Ref, o: _Out) -> str:
    if r.status == "pending":
        return join(o.authors(r), o.quoted(r.title), o.text(r.patent), "patent pending") + "."
    return join(o.authors(r), o.quoted(r.title), o.text(r.patent), o.date(r, day=True)) + "."


def _unpublished(r: Ref, o: _Out) -> str:
    return join(o.authors(r), o.quoted(r.title), "unpublished") + "."


def _private(r: Ref, o: _Out) -> str:
    return join(o.authors(r), "private communication", o.date(r)) + "."


CATEGORIES: dict[str, Category] = {c.id: c for c in (
    Category("conference", 1, "Paper published in a conference proceedings",
             "A. Alpha and B. T. Beta, “An overview of modern control systems”, in Proc. "
             "ICALEPCS’23, Cape Town, South Africa, Oct. 2023, pp. 57-59. "
             "doi:10.18429/JACoW-ICALEPCS2023-PAPERID",
             ("authors", "title", "conference", "city", "country", "month", "year", "pages"),
             _conference),
    Category("conference_unpublished", 2, "Unpublished paper from a previous conference",
             "A. Alpha, “An interesting talk but paper not submitted”, presented at IPAC’14, "
             "Dresden, Germany, Jun. 2014, paper MOP057, unpublished.",
             ("authors", "title", "conference", "city", "country", "month", "year"),
             _presented("unpublished")),
    Category("conference_current", 3, "Paper presented at the current conference",
             "A. Alpha and B. T. Beta, “Title of talk or poster presented at this conference”, "
             "presented at IPAC’25, Taipei, Taiwan, Jun. 2025, paper MOAB01, this conference.",
             ("authors", "title", "conference", "city", "country", "month", "year", "paper_id"),
             _presented("this conference")),
    Category("journal", 4, "Published in a periodical",
             "A. Alpha et al., “Low dose irradiation impact on modern silicon detectors”, Nucl. "
             "Instrum. Methods Phys. Res. A, vol. 773, pp. 1-7, 2015. "
             "doi:10.1016/j.nima.2014.11.022",
             ("authors", "title", "journal", "volume", "pages", "year"), _journal),
    Category("accepted", 5, "Accepted for publication",
             "J. B. Good, “Title of paper accepted for publication”, Phys. Rev. Lett., to be "
             "published.", ("authors", "title", "journal"), _accepted),
    Category("submitted", 6, "Submitted for publication",
             "G. D. Read, “Title of paper”, submitted for publication.",
             ("authors", "title"), _submitted),
    Category("arxiv", 7, "arXiv preprint",
             "A. Alpha, “Title of arXiv preprint”, Jan. 2025. doi:10.48550/arXiv.2501.10602",
             ("authors", "title", "month", "year", "doi"), _arxiv),
    Category("online", 8, "Online source",
             "EPICS, https://www.epics-controls.org", ("title", "url"), _online),
    Category("book_chapter", 9, "Citations to books: a chapter",
             "A. Alpha and B. Beta, “Title of chapter in the book”, in Title of Book, R Mars, "
             "Ed. New York, NY, USA: Wiley, 1994, pp. 42-48.",
             ("authors", "title", "book", "publisher", "city", "country", "year", "pages"),
             _chapter),
    Category("book", 9, "Citations to books: a book",
             "A. Alpha, Title of Book. Cambridge, MA, USA: MIT Press, 1986.",
             ("authors", "book", "publisher", "city", "country", "year"), _book),
    Category("report", 10, "Internal report",
             "A. Alpha et al., “Title of report”, CERN, Geneva, Switzerland, Rep. "
             "CERN-2012-333, Oct. 2012.",
             ("authors", "title", "institution", "city", "country", "report", "year"),
             _report),
    Category("technical_report", 11, "Technical report",
             "SLS-2 Conceptional Design Report, A. Streun, Ed., Paul Scherrer Institute, "
             "Villigen, Switzerland, Rep. 17-03, Dec. 2017. "
             "https://www.dora.lib4ri.ch/psi/item/psi:34977",
             ("title", "institution", "city", "country", "report", "year"), _technical_report),
    Category("thesis", 12, "Thesis",
             "A. Student, “Title of thesis”, Ph.D. thesis, Phys. Dept., Karlsruher Institut für "
             "Technologie, Karlsruhe, Germany, 2014.",
             ("authors", "title", "thesis", "institution", "city", "country", "year"), _thesis),
    Category("handbook", 13, "Handbook",
             "Motorola Semiconductor Handbook, Motorola Semiconductor Products Inc., Phoenix, "
             "AZ, USA, Nov. 2021, https://www.motorola.com/etc",
             ("title", "organization", "country", "year"), _handbook),
    Category("manual", 14, "Reference, manual",
             "IEEE Editorial Style Manual for Authors, IEEE Periodicals, Piscataway, NJ, USA, "
             "Mar. 2025.", ("title", "organization", "city", "country", "year"), _manual),
    Category("patent", 15, "Patents",
             "A. N. Inventor, “Title of patent”, <Patent Authority and No.>, Jan. 20, 2016.",
             ("authors", "title", "patent", "year"), _patent),
    Category("unpublished", 16, "Unpublished work",
             "P. Neptune, “Title of paper”, unpublished.", ("authors", "title"), _unpublished),
    Category("private", 16, "Private communication",
             "P. Uranus, private communication, Jun. 2015.", ("authors", "year"), _private),
)}

#: The 16 headings of Appendix B, in order (two have two layouts each).
HEADINGS = {1: "Conference proceedings", 2: "Unpublished paper from a previous conference",
            3: "Paper presented at the current conference", 4: "Periodical",
            5: "Accepted for publication", 6: "Submitted for publication", 7: "arXiv preprint",
            8: "Online source", 9: "Book or book chapter", 10: "Internal report",
            11: "Technical report", 12: "Thesis", 13: "Handbook", 14: "Reference, manual",
            15: "Patent", 16: "Unpublished work or private communication"}


def missing(r: Ref) -> list[str]:
    """The fields this reference's layout needs and does not have."""
    category = CATEGORIES.get(r.category)
    if category is None:
        return []
    out = []
    for name in category.required:
        if name == "conference" and (r.conference or r.proceedings):
            continue
        if name == "title" and r.category == "online" and (r.title or r.organization):
            continue
        if name == "book" and r.category == "book" and (r.book or r.title):
            continue
        if name == "month" and r.category == "patent":
            continue
        if name in ("patent", "year") and r.status == "pending" and r.category == "patent":
            continue
        if not getattr(r, name):
            out.append(name)
    return out


def render(r: Ref, *, latex: bool = False) -> str:
    category = CATEGORIES[r.category]
    text = category.render(r, _Out(latex))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\.\.(?=\s|$)", ".", text)


__all__ = ["CATEGORIES", "HEADINGS", "Category", "render", "missing", "tex_escape"]
