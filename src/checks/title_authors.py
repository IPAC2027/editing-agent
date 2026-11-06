"""Does the paper say what Indico says? Its title and its authors.

The proceedings' table of contents, author index and DOI metadata are built
from Indico, not from the PDF, so a paper whose title or author list differs
from its Indico record is published under the wrong name or without one of its
authors. Editors catch this by eye today, paper by paper.

The rules the editors settled:

* **the title in the paper is the right one** — a different title in Indico is
  changed to match it;
* **a different author list becomes the combined list** — anyone in the paper
  but not in Indico is added to Indico, and anyone Indico lists as an author
  but the paper does not is added to the paper.

This module only compares, and abstains where a comparison would be a guess:

* two names are one person only if their surnames agree and their initials do
  not conflict ("Y. Luo" is "Yun Luo"; "J. S. Berg" is "J. Berg"; "D. S. Doran"
  is "Scott Doran", who goes by his middle name);
* a part of the author block that is not plainly a person's name ("RadiaSoft
  LLC", "Boulder", "USA" — address fragments the LaTeX parser lets through) is
  set aside, never offered to an author as a missing co-author;
* a title using a macro the desk cannot render (``\\gtpsa``) is reported as
  unreadable rather than as different, and so is a title with almost nothing in
  common with Indico's — that is the parser reading the wrong thing, and
  proposing it as Indico's new title would be the worst possible outcome.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field

from src.parser.latex_parser import (
    _AFFILIATION_CUE_RE,
    _blank_comment,
    _extract_braced,
    parse_author_block,
)

#: Bumped whenever the paper's side is read differently, so a reading stored in
#: a report or cache by an older version is read again rather than trusted.
FRONT_MATTER_VERSION = 2

# ---------------------------------------------------------------------------
# What each side says
# ---------------------------------------------------------------------------


class Person(BaseModel):
    """One author, as one side records them."""

    name: str                    # as the source writes it
    given: str = ""
    family: str = ""
    affiliation: str = ""
    role: str = ""               # Indico: "primary" | "coauthor"; "" when unknown

    @property
    def jacow(self) -> str:
        """The name in JACoW form, "R. W. Yeung"."""
        if not self.family:
            return self.name
        initials = " ".join(_initials(self.given))
        return f"{initials} {self.family}".strip()


class FrontMatter(BaseModel):
    """The paper's title and author list, as plain text."""

    version: int = 0                                      # FRONT_MATTER_VERSION when read
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    not_names: list[str] = Field(default_factory=list)    # author-block parts that are no one
    unreadable: list[str] = Field(default_factory=list)   # title macros that render as nothing


class IndicoRecord(BaseModel):
    """The paper's title and authors as Indico has them."""

    title: str = ""
    authors: list[Person] = Field(default_factory=list)
    # True when the authors came from Indico's contribution data, with roles
    # and affiliations; False when only the names the pull recorded are known,
    # which include speakers and carry no affiliation.
    roles_known: bool = False
    as_of: str = ""


class Comparison(BaseModel):
    paper_title: str = ""
    indico_title: str = ""
    title_differs: bool = False
    proposed_indico_title: str = ""     # what Indico's title becomes
    check_capitals: bool = False        # words in it whose capitals were not known
    matched: list[tuple[str, str]] = Field(default_factory=list)   # (paper, Indico)
    paper_only: list[str] = Field(default_factory=list)            # to add to Indico
    indico_only: list[Person] = Field(default_factory=list)        # to add to the paper
    combined: list[str] = Field(default_factory=list)              # the list afterwards
    not_names: list[str] = Field(default_factory=list)
    unreadable: list[str] = Field(default_factory=list)            # why it cannot be trusted

    @property
    def differs(self) -> bool:
        return self.title_differs or bool(self.paper_only or self.indico_only)


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "dos",
              "du", "le", "la", "ter", "ten", "zu", "bin", "al", "el"}
_INITIAL = re.compile(r"^(?:[A-Z][a-z]?\.(?:-[A-Z][a-z]?\.)*|[A-Z])$")   # "J.", "Ch.", "J.-L.", "T"
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
_NOT_A_PERSON = {
    "llc", "inc", "ltd", "gmbh", "corp", "co", "usa", "uk", "germany", "france",
    "italy", "switzerland", "japan", "china", "korea", "sweden", "spain", "canada",
    "russia", "india", "netherlands", "belgium", "poland", "austria", "denmark",
    "brazil", "australia", "israel", "taiwan", "czech", "republic", "kingdom",
    "collaboration", "team", "group", "behalf", "tech", "source",
    # Institution words the affiliation cue does not list.
    "accelerator", "accelerators", "physics", "engineering", "science", "sciences",
    "zentrum", "hochschule", "istituto", "instituto", "nazionale", "synchrotron",
    "photon", "neutron", "laboratories", "operations", "systems", "solutions",
    "labs", "techlabs", "universidad", "universidade",
}
#: Two-word towns that host accelerator labs and read like a person's name.
#: A heuristic, not a gazetteer: anything it misses is still caught when the
#: author answers the email.
_PLACES = {
    "los angeles", "los alamos", "san francisco", "san diego", "san jose", "new york",
    "santa fe", "santa barbara", "menlo park", "palo alto", "east lansing",
    "newport news", "oak ridge", "stony brook", "college park", "ann arbor",
    "long island", "lemont il", "upton ny",
}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _key(text: str) -> str:
    """A surname or given name reduced to its letters, for comparing."""
    return re.sub(r"[^a-z0-9]", "", _fold(text))


def _initials(given: str) -> list[str]:
    """ "Jean-Luc Paul" -> ["J.-L.", "P."]; "R. W." stays as written."""
    out: list[str] = []
    for word in given.replace(".", ". ").split():
        if _INITIAL.match(word):
            out.append(word)
            continue
        parts = [p for p in word.split("-") if p and p[0].isalpha()]
        if parts:
            out.append("-".join(f"{p[0].upper()}." for p in parts))
    return out


def split_name(name: str) -> tuple[str, str]:
    """``(given, family)`` from a name written either way JACoW sees.

    "R. W. Y. Yeung" and "Ryan Yeung" both give family "Yeung"; particles stay
    with the surname, so "A. van der Meer" gives "van der Meer".
    """
    tokens = re.sub(r"\.(?=[A-Za-z])", ". ", " ".join((name or "").split())).split()
    suffix: list[str] = []
    while len(tokens) > 2 and _key(tokens[-1]) in _SUFFIXES:   # "Gaus III", "Edstrom Jr."
        suffix.insert(0, tokens.pop())
    if not tokens:
        return "", ""
    leading = 0
    while leading < len(tokens) - 1 and _INITIAL.match(tokens[leading]):
        leading += 1
    if leading:
        return " ".join(tokens[:leading]), " ".join(tokens[leading:] + suffix)
    start = len(tokens) - 1
    while start > 1 and tokens[start - 1].lower() in _PARTICLES:
        start -= 1
    return " ".join(tokens[:start]), " ".join(tokens[start:] + suffix)


def person(name: str, *, affiliation: str = "", role: str = "") -> Person:
    given, family = split_name(name)
    return Person(name=" ".join(name.split()), given=given, family=family,
                  affiliation=affiliation, role=role)


def _family_words(family: str) -> list[str]:
    words = [_key(w) for w in family.replace("-", " ").split()]
    return [w for w in words if w and w not in _SUFFIXES]


def _families_agree(a: str, b: str) -> bool:
    """ "Edstrom Jr" is "Edstrom"; "Temizel Ozdemir" is the "Ozdemir" a full name
    split at its last word gives; "Hoffstaetter de Torquat" is "Hoffstaetter"."""
    wa, wb = _family_words(a), _family_words(b)
    if not wa or not wb:
        return False
    if wa == wb or "".join(wa) == "".join(wb):      # "O' Shea" is "O'Shea"
        return True
    short, long = sorted((wa, wb), key=len)
    return len(short) < len(long) and short in (long[:len(short)], long[-len(short):])


def _initials_agree(given_a: str, given_b: str) -> bool:
    """No conflict between the given names: either one's first initial is among
    the other's initials, or one side has none."""
    ia = {_key(i)[:1] for i in _initials(given_a)} - {""}
    ib = {_key(i)[:1] for i in _initials(given_b)} - {""}
    if not ia or not ib:
        return True
    return _key(given_a)[:1] in ib or _key(given_b)[:1] in ia


def same_person(a: Person, b: Person) -> bool:
    """Agreeing surnames and given names — or the same with Indico's first and
    last name fields swapped, which happens."""
    return ((_families_agree(a.family, b.family) and _initials_agree(a.given, b.given))
            or (_families_agree(a.family, b.given) and _initials_agree(a.given, b.family)))


def looks_like_person(name: str) -> bool:
    """Whether an author-block fragment is plainly someone's name."""
    if not name or re.search(r"@|https?:|www\.|\d", name):
        return False
    if _AFFILIATION_CUE_RE.search(name):
        return False
    given, family = split_name(name)
    if not given or not family:
        return False            # one word: "CLASSE", "Boulder", "USA"
    # A sentence from the body that an unbalanced \author{} swallowed: too
    # long, or with words in lower case that are not particles.
    tokens = name.split()
    if len(tokens) > 6 or any(
            t[0].islower() and t.lower() not in _PARTICLES for t in tokens if t[0].isalpha()):
        return False
    words = [_key(w) for w in re.split(r"[\s.\-]+", name) if w]
    if any(w in _NOT_A_PERSON for w in words) or " ".join(words) in _PLACES:
        return False
    # "van der Meer": judge the surname by its first word that is not a particle.
    core = [w for w in family.split()
            if _key(w) not in _SUFFIXES and w.lower() not in _PARTICLES] or [family]
    letters = [c for c in " ".join(core) if c.isalpha()]
    # A surname in capitals is a person when the given name is written normally
    # ("ShuCheng PAI"); in capitals throughout it is an institution ("IHEP CAS").
    shouting = all(c.isupper() for c in letters) and not any(c.islower() for c in given)
    return bool(letters) and core[0][0].isupper() and not shouting


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

def title_words(title: str) -> list[str]:
    """The words of a title, without case, accents or punctuation."""
    return re.findall(r"[a-z0-9]+", _fold(title))


def proposed_title(paper_title: str, indico_title: str) -> tuple[str, bool]:
    """Indico's new title, and whether its capitals need a look.

    A LaTeX title is written in the case the author wants (the class sets it in
    capitals). A Word title is typed in capitals; for that one, each word takes
    the capitals Indico gives it, and a word Indico does not have is left as the
    paper writes it and reported, rather than guessed at.
    """
    if any(c.islower() for c in paper_title):
        return paper_title, False
    known = {_fold(w): w for w in re.findall(r"[\w’']+", indico_title)}
    unknown = False

    def _recase(match: re.Match) -> str:
        nonlocal unknown
        word = match.group(0)
        if _fold(word) in known:
            return known[_fold(word)]
        if any(c.isalpha() for c in word):
            unknown = True
        return word

    return re.sub(r"[\w’']+", _recase, paper_title), unknown


# ---------------------------------------------------------------------------
# Reading the paper's side
# ---------------------------------------------------------------------------

_DROP_WITH_ARGUMENT = ("thanks", "footnote", "email", "orcid", "altaffilmark")


def _drop_commands(text: str, commands: tuple[str, ...]) -> str:
    """Remove ``\\cmd{...}`` with its argument, however deeply that nests."""
    pattern = re.compile(r"\\(?:" + "|".join(commands) + r")\s*(?=\{)")
    while True:
        match = pattern.search(text)
        if not match:
            return text
        _content, end = _extract_braced(text, match.end())
        text = text[:match.start()] + text[end:]


#: Commands that set layout or spacing and print nothing, rightly.  The
#: breaks stand between two words; the rest vanish ("GTPSA.jl\\xspace:").
_BREAKS = {"newline", "linebreak", "break", "hfill"}
_SILENT = _BREAKS | {
    "xspace", "relax", "protect", "boldmath", "unboldmath", "noindent", "centering",
    "nobreak", "allowbreak", "ignorespaces", "normalfont", "bfseries", "itshape",
    "upshape", "mdseries", "scshape", "rmfamily", "sffamily", "ttfamily", "tiny",
    "scriptsize", "footnotesize", "small", "normalsize", "large", "Large", "LARGE",
    "huge", "Huge",
}


def latex_title_text(raw: str) -> tuple[str, list[str]]:
    """A LaTeX title as plain text, plus any macro that rendered as nothing."""
    from pylatexenc.latex2text import LatexNodes2Text

    raw = _drop_commands(raw or "", ("thanks", "footnote"))
    raw = re.sub(r"(?<!\\)\\(" + "|".join(_SILENT) + r")(?![A-Za-z])",
                 lambda m: " " if m.group(1) in _BREAKS else "", raw)
    converter = LatexNodes2Text()
    # "(?<!\\)": in "LANSCE\\Proton" the "\\" is a line break, not "\Proton".
    unreadable = sorted({
        f"\\{name}" for name in re.findall(r"(?<!\\)\\([A-Za-z]+)(?![A-Za-z{])(?!\s*\{)", raw)
        if not converter.latex_to_text(f"\\{name}").strip()
    })
    try:
        text = converter.latex_to_text(raw)
    except Exception:  # noqa: BLE001 — pylatexenc on author input
        text = re.sub(r"\\[A-Za-z]+|[{}]", " ", raw)
    return " ".join(text.replace("\u00a0", " ").split()), unreadable


#: Longer than any real author block: the parser ran past its closing brace.
_AUTHOR_BLOCK_LIMIT = 3000


_NEWCOMMAND = re.compile(r"\\(?:re|provide)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*(?=\{)")
_DEF = re.compile(r"\\def\s*\\([A-Za-z]+)\s*(?=\{)")


def _user_macros(source: str) -> dict[str, str]:
    """The paper's own macros that take no argument: ``\\newcommand{\\gtpsa}{GTPSA.jl}``."""
    macros: dict[str, str] = {}
    for pattern in (_NEWCOMMAND, _DEF):
        for match in pattern.finditer(source):
            body, _end = _extract_braced(source, match.end())
            macros.setdefault(match.group(1), body)
    return macros


def _expand(text: str, macros: dict[str, str]) -> str:
    for _ in range(3):                                   # a macro may use another
        text = re.sub(r"(?<!\\)\\([A-Za-z]+)(?![A-Za-z])",
                      lambda m: macros.get(m.group(1), m.group(0)), text)
    return text


def latex_source_front_matter(source: str) -> FrontMatter:
    """Title and authors straight from a LaTeX source.

    Reads ``\\title[short]{...}`` and every ``\\author[1,2]{...}`` — the
    ``authblk`` style puts one author in each, and the general parser reads
    only a single ``\\author{...}`` without an optional argument, so those papers
    had no authors at all.  Macros the paper defines itself are expanded in the
    title first.
    """
    blanked = "\n".join(_blank_comment(line) for line in source.split("\n"))
    # What LaTeX never sees: \iffalse ... \fi and comment environments.
    blanked = re.sub(r"\\iffalse\b.*?\\fi\b|\\begin\{comment\}.*?\\end\{comment\}",
                     lambda m: " " * len(m.group(0)), blanked, flags=re.DOTALL)
    # Given twice, the one LaTeX uses is the last before \maketitle.
    end = blanked.find("\\maketitle")
    head = blanked if end < 0 else blanked[:end]
    titles = list(re.finditer(r"\\title\s*(?:\[[^\]]*\])?\s*(?=\{)", head))
    title_raw = _extract_braced(head, titles[-1].end())[0] if titles else ""
    found = list(re.finditer(r"\\author\s*(\[[^\]]*\])?\s*(?=\{)", head))
    # authblk puts one author in each \author[..]{..} and uses them all;
    # otherwise one \author{..} counts, and any other is an old version left
    # in the source (TUP077 had two).
    if any(m.group(1) for m in found):
        found = [m for m in found if m.group(1)]
    else:
        found = found[-1:]
    blocks = [_extract_braced(head, m.end())[0] for m in found]
    return latex_front_matter(_expand(title_raw, _user_macros(blanked)), " \\\\ ".join(blocks))


def latex_front_matter(title_raw: str, author_raw: str) -> FrontMatter:
    title, unreadable = latex_title_text(title_raw)
    if len(author_raw or "") > _AUTHOR_BLOCK_LIMIT:
        return FrontMatter(version=FRONT_MATTER_VERSION, title=title, unreadable=unreadable)
    cleaned = _drop_commands(author_raw or "", _DROP_WITH_ARGUMENT)
    # "J.\ R. Berlioz": a control space or thin space between initials is a
    # space, not a break between two authors.  "\\" (a line break) is kept.
    cleaned = re.sub(r"(?<!\\)\\(?:\s|,)", " ", cleaned)
    # Each "\\" line starts a new group, "names, affiliation" — the template's
    # second group of authors comes after one.  parse_author_block reads every
    # line after the first as affiliation, which loses those authors.
    names: list[str] = []
    for group in re.split(r"\\\\(?:\[[^\]]*\])?", cleaned):
        names.extend(parse_author_block(group)[0])
    return _front(title, names, unreadable)


def front_matter_of(source: Path) -> FrontMatter | None:
    """Read the paper's title and authors from its source file."""
    if source.suffix.lower() == ".tex":
        return latex_source_front_matter(source.read_text(encoding="utf-8", errors="replace"))
    if source.suffix.lower() in (".docx", ".doc"):
        from src.checks.word_front_checks import read_front_matter

        front = read_front_matter(source)
        return word_front_matter(front.title, front.author_names or front.author_line)
    return None


def word_front_matter(title: str, author_line: str) -> FrontMatter:
    from src.checks.word_front_checks import _author_names

    # "COMMISSIONING OF THE HEPS*": the mark is the title's footnote, not its text.
    title = re.sub(r"\s*[*\u2020\u2021\u00a7\u00b6]+$", "", " ".join((title or "").split()))
    return _front(title, _author_names(author_line or ""), [])


def _front(title: str, candidates: list[str], unreadable: list[str]) -> FrontMatter:
    front = FrontMatter(version=FRONT_MATTER_VERSION, title=title, unreadable=unreadable)
    for candidate in candidates:
        name = " ".join(candidate.split()).strip(" ,;")
        # "A. S. WaghmareA": a letter used as an affiliation mark, run into the name.
        name = re.sub(r"(?<=[a-z])[A-Z]$", "", name)
        if not name:
            continue
        # Once the address has started ("UCLA, Los Angeles, CA"), a fragment
        # without initials is more of it, not a full-named author.
        has_initials = bool(_initials(split_name(name)[0])) and "." in name
        if looks_like_person(name) and (has_initials or not front.not_names):
            front.authors.append(name)
        else:
            front.not_names.append(name)
    return front


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

def compare(front: FrontMatter, record: IndicoRecord) -> Comparison:
    result = Comparison(paper_title=front.title, indico_title=record.title,
                        not_names=list(front.not_names))

    paper_words, indico_words = set(title_words(front.title)), set(title_words(record.title))
    shared = len(paper_words & indico_words) / max(1, min(len(paper_words), len(indico_words)))
    if front.unreadable:
        result.unreadable.append(
            "the paper's title uses " + ", ".join(front.unreadable)
            + ", which the desk cannot read")
    elif front.title and record.title and shared < 0.5:
        # The parser read the wrong thing; its author list is no better.
        result.unreadable.append(
            "the paper's title and Indico's have little in common, so the paper's "
            "may have been misread — compare them by eye")
        return result
    elif front.title and record.title and title_words(front.title) != title_words(record.title):
        result.title_differs = True
        result.proposed_indico_title, result.check_capitals = proposed_title(
            front.title, record.title)

    if not front.authors:
        result.unreadable.append("the paper's author list could not be read")
        return result
    if not record.authors:
        result.unreadable.append("Indico lists no authors for this paper")
        return result

    remaining = list(record.authors)
    for name in front.authors:
        mine = person(name)
        match = next((other for other in remaining if same_person(mine, other)), None)
        if match is None:
            result.paper_only.append(name)
        else:
            remaining.remove(match)
            result.matched.append((name, match.name))
    # Someone whose surname is in a fragment the paper's author block did not
    # yield cleanly ("E.-H" + "Huang", "ShuCheng PAI") is in the paper; the
    # parser simply could not tell.  Never ask an author to add them.
    fragments = [_key(f) for f in front.not_names]
    result.indico_only = [
        p for p in remaining
        if not any(_key(p.family) and _key(p.family) in f for f in fragments)
    ]
    result.combined = list(front.authors) + [p.jacow for p in result.indico_only]
    return result
