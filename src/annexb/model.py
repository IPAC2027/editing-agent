"""A reference as fields, where each value came from, and what the engine made of it."""

from __future__ import annotations

from dataclasses import dataclass, field

#: JACoW's month abbreviations (Appendix B; ``jacow.bbx`` writes "Jun.", "Jul.", "Sep.").
MONTHS = ("Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.",
          "Nov.", "Dec.")

#: Between two page numbers. Appendix B's examples write "pp. 57-59".
PAGE_DASH = "-"


@dataclass
class Name:
    """One author or editor: initials and family name, or a group's name."""

    given: str = ""          # "A. T.", "J.-P.", "Th."
    family: str = ""         # "Alpha", "van der Meer"
    suffix: str = ""         # "Jr."
    literal: str = ""        # "CMS Collaboration", "Particle Data Group"

    def plain(self) -> str:
        if self.literal:
            return self.literal
        text = f"{self.given} {self.family}".strip()
        return f"{text}, {self.suffix}" if self.suffix else text

    def latex(self) -> str:
        if self.literal:
            return self.literal
        given = self.given.replace(". ", ".~")
        text = f"{given}~{self.family}" if given else self.family
        return f"{text}, {self.suffix}" if self.suffix else text

    def key(self) -> str:
        """The family name, folded, for comparing two author lists."""
        import unicodedata
        word = self.literal or self.family
        word = unicodedata.normalize("NFKD", word)
        return "".join(c for c in word if not unicodedata.combining(c)).lower().strip()


#: Every field a reference can have, in the order the editor's card lists them.
FIELDS = ("authors", "title", "conference", "proceedings", "journal", "book", "editors",
          "edition", "volume", "issue", "pages", "paper_id", "institution", "department",
          "organization", "publisher", "city", "state", "country", "month", "day", "year",
          "report", "thesis", "patent", "status", "doi", "url", "arxiv")


@dataclass
class Ref:
    """A reference, field by field. ``source`` says where each value came from:
    "text" (the author's own reference), "refs.jacow.org", "Crossref", "DataCite",
    "Annex C", "abbrevIso", "JACoW conference list", "arXiv identifier", "model"."""

    category: str = ""
    authors: list[Name] = field(default_factory=list)
    et_al: bool = False
    editors: list[Name] = field(default_factory=list)
    title: str = ""
    conference: str = ""      # the label: "IPAC'23" (rendered with ’)
    proceedings: str = ""     # a proceedings title written out: "Proc. 13th Int. ... (ICAP'18)"
    journal: str = ""         # as it is to be printed (the abbreviation)
    journal_written: str = ""  # as the author wrote it
    book: str = ""
    edition: str = ""         # "2nd ed."
    volume: str = ""
    issue: str = ""
    pages: str = ""           # "57-59", "050511", "e35"
    paper_id: str = ""
    institution: str = ""
    department: str = ""
    organization: str = ""
    publisher: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    month: str = ""           # "Oct.", "Aug.-Sep."
    day: str = ""
    year: str = ""
    report: str = ""          # "CERN-2012-333"
    thesis: str = ""          # "Ph.D." / "M.Sc." / "Diploma"
    patent: str = ""          # "U.S. Patent 9 123 456" or the authority alone
    status: str = ""          # "this conference", "unpublished", "submitted", "accepted", "pending", "private"
    doi: str = ""
    url: str = ""
    arxiv: str = ""
    note: str = ""            # what the author wrote that has no place in the layout
    source: dict[str, str] = field(default_factory=dict)

    def put(self, name: str, value, source: str) -> None:
        """Set a field and remember where its value came from (empty values are ignored)."""
        if value in ("", None, []):
            return
        setattr(self, name, value)
        self.source[name] = source

    def copy(self) -> "Ref":
        import copy
        return copy.deepcopy(self)


@dataclass
class Problem:
    """Something the editor has to see: a missing fact, a doubt, a dropped word."""

    code: str
    message: str
    field: str = ""
    severity: str = "warning"     # "error": the layout cannot be completed without it


@dataclass
class Outcome:
    """What the engine made of one reference."""

    original: str
    ref: Ref
    category: str = ""
    text: str | None = None       # Appendix B, plain text (Word, the reference page)
    latex: str | None = None      # Appendix B, LaTeX (\bibitem)
    conforms: bool = False        # the original is already exactly this
    changes: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    dropped: str = ""             # words of the original that are not in the result
    parsed_by: str = "rules"      # "rules" or "model"
    sources: list[str] = field(default_factory=list)
    raw: Ref | None = None        # the reference as read, before normalising

    def summary(self) -> str:
        """One line for the editor: the kind, and what was changed."""
        from src.annexb.categories import CATEGORIES, HEADINGS
        kind = (HEADINGS[CATEGORIES[self.category].number] if self.category in CATEGORIES
                else "reference")
        if self.conforms:
            return f"Already in Appendix B's layout ({kind.lower()})."
        said = "; ".join(dict.fromkeys(self.changes)) or "punctuation and order"
        return f"Rewritten in Appendix B's {kind.lower()} layout: {said}."

    @property
    def complete(self) -> bool:
        return not self.missing


__all__ = ["MONTHS", "PAGE_DASH", "Name", "Ref", "Problem", "Outcome", "FIELDS"]
