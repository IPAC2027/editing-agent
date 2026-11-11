"""What the reference checker finds, how it fixes it, and the parts of a reference.

An :class:`Issue` is one way a reference breaks a JACoW rule. It says where
(``start``/``end`` in the text it was found in), which rule, and either how to
fix it (a :class:`Fix`) or why the rules cannot, and who can: the local model
(a matter of layout or judgement, with every fact already in the reference or
verified) or the editor (a fact is missing or two sources disagree).

A :class:`Fix` also tells the damage check (``check_rewrite``) exactly what it
may change, so a fix that is right by the rules is never refused as damage,
and a fix that loses anything else still is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ERROR, WARNING, INFO = "error", "warning", "info"
#: Who can fix an issue the rules cannot.
MODEL, EDITOR = "model", "editor"

OPEN_QUOTES = "“\""
CLOSE_QUOTES = "”\""


@dataclass(frozen=True)
class Fix:
    """Replace ``text[start:end]`` with *replacement*."""

    start: int
    end: int
    replacement: str
    # What the damage check is told this change may do.
    substitutions: tuple[tuple[str, str], ...] = ()
    additions: tuple[str, ...] = ()
    removals: tuple[str, ...] = ()
    # Only presentation (punctuation, spacing, the DOI's form): safe to apply
    # without asking. Anything that moves, adds or removes content is not.
    presentation: bool = True
    # A value taken from a lookup, named for the editor ("refs.jacow.org").
    source: str = ""


@dataclass
class Issue:
    code: str
    severity: str
    message: str                   # for the editor, in plain words
    rule: str                      # the JACoW rule, so the editor can look it up
    start: int = -1
    end: int = -1
    fix: Fix | None = None
    who: str = MODEL               # when there is no fix: MODEL or EDITOR
    why_not: str = ""              # why the rules do not fix it
    needs: str = ""                # the fact that would settle it
    excerpt: str = ""

    def view(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message,
                "rule": self.rule, "excerpt": self.excerpt,
                "fixable": self.fix is not None,
                "who": "rules" if self.fix else self.who,
                "why_not": self.why_not, "needs": self.needs}


@dataclass
class Parts:
    """A reference cut where JACoW references are cut: authors, “title”, the rest."""

    text: str
    authors: tuple[int, int] | None = None     # the author list, without the comma after it
    open_quote: int = -1                       # where the title's quotes are
    close_quote: int = -1
    rest: tuple[int, int] = (0, 0)             # everything after the title

    @property
    def title(self) -> tuple[int, int] | None:
        if self.open_quote < 0 or self.close_quote < 0:
            return None
        return self.open_quote + 1, self.close_quote

    def get(self, span: tuple[int, int] | None) -> str:
        return self.text[span[0]:span[1]] if span else ""


_INITIALS_NAME = re.compile(
    r"(?:[A-Z]\.\s?(?:-\s?[A-Z]\.\s?)*)+(?:[a-z]+\s)*[A-ZÀ-ɏ][\wÀ-ɏ'’\-]*"
    r"(?:\s+et\s+al\.?)?")


def _leading_names(text: str) -> int:
    """Where a list of initials-first names at the start of *text* ends (0: none).

    Only "A. B. Surname" names count, so a book's title is never taken for a
    person when there is no quoted title to stop at.
    """
    end = count = 0
    for m in re.finditer(r"[^,]+", text):
        piece = re.sub(r"^and\s+", "", m.group(0).strip())
        if count and re.fullmatch(r"et\.?\s*al\.?", piece):
            end = m.end()                # "…, B. Beta, et al." belongs to the list
            continue
        people_here = [x.strip() for x in re.split(r"\s+and\s+", piece)]
        if piece and all(_INITIALS_NAME.fullmatch(x) for x in people_here):
            end, count = m.end(), count + 1
        else:
            break
    return end if count and end < len(text.rstrip()) else 0


def split(text: str) -> Parts:
    """Find the author list, the quoted title and what follows it."""
    parts = Parts(text=text, rest=(0, len(text)))
    match = re.search(r"(^|[\s,])([“\"])", text)
    if not match:
        end = _leading_names(text)
        if end:                          # no title: authors, then the rest
            parts.authors, parts.rest = (0, end), (end, len(text))
        return parts
    opening = match.start(2)
    closing = -1
    depth = 0
    for index in range(opening + 1, len(text)):
        char = text[index]
        if char == "\u201c" and text[opening] == "\u201c":
            depth += 1                   # a quoted title inside the title
        elif char in CLOSE_QUOTES:
            if depth and char == "\u201d":
                depth -= 1
                continue
            closing = index
            break
    if closing < 0:
        return parts
    parts.open_quote, parts.close_quote = opening, closing
    head = text[:opening]
    end = len(head.rstrip(" ,"))
    if end > 0:
        parts.authors = (0, end)
    parts.rest = (closing + 1, len(text))
    return parts


# -- names ------------------------------------------------------------------

_SPLIT_NAMES = re.compile(r",\s*(?:and\s+)?|\s+and\s+|\s*&\s*")


@dataclass
class Name:
    start: int
    end: int
    text: str


def names(text: str, span: tuple[int, int] | None) -> tuple[list[Name], bool]:
    """The names in an author list, and whether it ends in "et al."."""
    if not span:
        return [], False
    body = text[span[0]:span[1]]
    et_al = bool(re.search(r"\bet\.?\s*al\b\.?\s*$", body))
    found: list[Name] = []
    position = 0
    for piece in _SPLIT_NAMES.split(body) + [""]:
        if not piece:
            continue
        start = body.find(piece, position)
        position = start + len(piece)
        cleaned = piece.strip()
        if re.fullmatch(r"et\.?\s*al\.?", cleaned):
            continue
        cleaned = re.sub(r"\s+et\.?\s*al\.?$", "", cleaned)
        if cleaned:
            found.append(Name(span[0] + start, span[0] + start + len(cleaned), cleaned))
    return found, et_al


_PERSON = re.compile(
    r"(?:(?:[A-Z]\.\s?(?:-\s?[A-Z]\.\s?)?)+|[A-Z][a-z\u00c0-\u024f'\u2019]+\s)"   # initials or a given name
    r"(?:[A-Za-z\u00c0-\u024f'\u2019]+\s)*"                                       # middle names, particles
    r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'\u2019\-]*"                               # surname
    r"|[A-Z][\w\u00c0-\u024f'\u2019\-]+(?:\s[A-Z][\w'\-]+)?,?\s(?:[A-Z]\.\s?-?)+")    # Surname, I.


def people(found: list[Name]) -> bool:
    """Whether every name looks like a person's (not a book title or a year)."""
    return bool(found) and all(len(n.text.split()) <= 5 and not re.search(r"\d", n.text)
                               and _PERSON.fullmatch(n.text.strip()) for n in found)


@dataclass
class Context:
    text: str
    parts: Parts
    kind: str = ""
    facts: dict = field(default_factory=dict)
    style: object = None                 # src.house_style.HouseStyle
