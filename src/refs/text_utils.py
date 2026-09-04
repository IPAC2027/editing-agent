"""Text helpers: author parsing, sentence casing, month/title cleaners.

Migrated from the v1.0.0 standalone formatter. Pure stdlib, no I/O. Used by
:mod:`src.refs.formatters` and by reference checks that need to compare or
normalise free-text reference fields.

Public symbols (the leading underscore on internal helpers from the source
file has been dropped where the helper is genuinely part of the surface):

- :func:`parse_authors` / :func:`fmt_authors`
- :func:`sent_case` / :func:`clean_title`
- :func:`norm_month`
- :func:`pages_fmt`
- :func:`to_initials`
- :func:`extract_valid_year_month`
- :func:`author_families`
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Month name constants (used by date formatting + LTWA / Crossref parsing) ──

# Single source of truth for the abbreviated month list (Jan., Feb., …, May, …).
# Note: May has no period because the unabbreviated form is already three chars.
MONTH_LIST: list[str] = [
    "Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.",
    "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.",
]

# Long/short month-name → JACoW abbreviation lookup. Lower-cased keys, dots
# stripped before lookup (see :func:`norm_month`).
MONTH_ABBR: dict[str, str] = {
    "january": "Jan.", "february": "Feb.", "march": "Mar.", "april": "Apr.",
    "may": "May", "june": "Jun.", "july": "Jul.", "august": "Aug.",
    "september": "Sep.", "october": "Oct.", "november": "Nov.", "december": "Dec.",
    "jan": "Jan.", "feb": "Feb.", "mar": "Mar.", "apr": "Apr.",
    "jun": "Jun.", "jul": "Jul.", "aug": "Aug.", "sep": "Sep.",
    "oct": "Oct.", "nov": "Nov.", "dec": "Dec.",
}


def norm_month(s: str) -> str:
    """Normalise a month string to ``'Jan.'``-style abbreviation."""
    return MONTH_ABBR.get(s.lower().replace(".", "").strip(), s)


# ─────────────────────────────────────────────────────────────────────────────
# Author parsing
# ─────────────────────────────────────────────────────────────────────────────

def _is_author_unit(s: str) -> bool:
    """Return True if *s* looks like a single author name (initials + family)."""
    s = s.strip().rstrip(",")
    if not s:
        return False
    if re.match(r"^(?:[A-Z]\.[-\s]?)+\s+[A-Z][a-z]", s):
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z]", s):
        return True
    if re.match(
        r"^[A-Z][a-zÀ-ɏ\-]+(?:\s+[A-Z][a-zÀ-ɏ\-]+)*"
        r",\s*[A-Z]\.",
        s,
    ):
        return True
    return False


def _normalize_one(p: str) -> str:
    """Reorder ``Family, Given`` → ``Given Family`` for a single author string."""
    p = p.strip().rstrip(",").strip()
    m = re.match(
        r"^([A-ZÀ-ɏ][a-zÀ-ɏ\-]+"
        r"(?:\s+[A-Z][a-zÀ-ɏ\-]+)*),\s*(.+)$",
        p,
    )
    return f"{m.group(2).strip()} {m.group(1).strip()}" if m else p


def to_initials(given: str) -> str:
    """Convert a given name string to dot-separated initials.

    Handles all common cases:
      ``Jean-Pierre`` → ``J.-P.``
      ``J.-P.``       → ``J.-P.``   (already initials — preserved exactly)
      ``B.T.``        → ``B.T.``    (multi-initial — preserved)
      ``Jean Pierre`` → ``J.P.``
    """
    given = given.strip()
    if not given:
        return ""
    core = given.replace(" ", "")
    # Already in initials form — return unchanged so J.-P. stays J.-P.
    if re.match(r"^(?:[A-Z]\.(?:-[A-Z]\.)*)+$", core):
        return core
    if re.match(r"^(?:[A-Z]\.)+$", core):
        return core
    # Full given name: split on whitespace and hyphens
    # Hyphen-connected parts (Jean-Pierre) produce J.-P.
    # Space-connected parts (Jean Pierre) produce J.P.
    result = ""
    raw_parts = re.split(r"([-\s])", given)
    for part in raw_parts:
        if part == "-":
            result += "-"
        elif part.strip() == "":
            pass
        elif re.match(r"^[A-Z]\.$", part):
            result += part  # already an initial like 'J.'
        elif part and part[0].isalpha():
            result += part[0].upper() + "."
    return result if result else given[0].upper() + "."


def extract_valid_year_month(date_parts: list) -> tuple[str, str]:
    """Extract plausible year/month from a Crossref ``date-parts`` list."""
    year = ""
    month = ""
    if not date_parts:
        return year, month
    try:
        y = int(date_parts[0])
    except (TypeError, ValueError, IndexError):
        y = 0
    if 1900 <= y <= 2100:
        year = str(y)
    try:
        m = int(date_parts[1]) if len(date_parts) > 1 else 0
    except (TypeError, ValueError):
        m = 0
    if year and 1 <= m <= 12:
        month = MONTH_LIST[m - 1]
    return year, month


def parse_authors(raw) -> list[str]:
    """Parse a raw author value into a list of ``'I. Family'`` strings.

    Accepts either a string (any common JACoW/BibTeX format) or a Crossref-style
    list of ``{'given': ..., 'family': ...}`` dicts.
    """
    if isinstance(raw, list):
        parts: list[str] = []
        for a in raw:
            literal = (a.get("literal") or a.get("name") or "").strip()
            if literal and not (a.get("family") or a.get("given")):
                parts.append(_normalize_one(literal))
                continue
            given = (a.get("given") or "").strip()
            family = (a.get("family") or "").strip()
            if not family:
                if given:
                    parts.append(given)
                continue
            if not given:
                parts.append(family)
                continue
            initials = to_initials(given)
            parts.append(f"{initials} {family}" if initials else family)
        return [p for p in parts if p]
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    if re.search(r"\bet\s+al\.?", s, re.IGNORECASE):
        first = re.split(r",|;|\s+and\s+", s, maxsplit=1)[0].strip()
        first = re.sub(r"\s*et\s+al\.?", "", first, flags=re.IGNORECASE).strip()
        return [_normalize_one(first) + " et al."]
    if ";" in s:
        parts = [p.strip() for p in s.split(";") if p.strip()]
    else:
        parts = re.split(r",?\s+and\s+", s, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]
        expanded: list[str] = []
        for chunk in parts:
            sub = [x.strip() for x in chunk.split(",") if x.strip()]
            if len(sub) > 1 and all(_is_author_unit(x) for x in sub):
                expanded.extend(sub)
            else:
                expanded.append(chunk)
        parts = expanded
    return [_normalize_one(p) for p in parts if p]


def fmt_authors(raw) -> str:
    """Format an author list per JACoW style.

    Rules:
      - 1 author  → ``A``
      - 2 authors → ``A and B``
      - 3-6       → ``A, B, …, and Z`` (Oxford comma)
      - 7+        → ``A et al.``
    """
    if raw is None:
        return ""
    authors = parse_authors(raw)
    if not authors:
        return str(raw) if raw else ""
    if authors[-1].endswith("et al."):
        return authors[0]
    n = len(authors)
    if n == 1:
        return authors[0]
    if n == 2:
        return f"{authors[0]} and {authors[1]}"
    if n <= 6:
        return ", ".join(authors[:-1]) + ", and " + authors[-1]
    return authors[0] + " et al."


def author_families(raw) -> list[str]:
    """Return lowercase ASCII-folded family names from a raw author value."""
    from src.refs.similarity import ascii_fold

    if isinstance(raw, list):
        return [ascii_fold(a.get("family", "")) for a in raw if a.get("family")]
    if not raw:
        return []
    parts = re.split(r",?\s+and\s+|;", str(raw), flags=re.IGNORECASE)
    families: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        sub = [x.strip() for x in p.split(",") if x.strip()]
        if len(sub) > 1 and all(_is_author_unit(x) for x in sub):
            for s in sub:
                words = s.split()
                if words:
                    families.append(ascii_fold(words[-1]))
        elif re.match(r"^[A-Z][a-z]", p):
            families.append(ascii_fold(p.split(",")[0].split()[0]))
        else:
            words = p.split()
            if words:
                families.append(ascii_fold(words[-1]))
    return [f for f in families if len(f) > 1]


# ─────────────────────────────────────────────────────────────────────────────
# Sentence casing for titles
# ─────────────────────────────────────────────────────────────────────────────

_ACRONYM_RE = re.compile(r"^[A-Z0-9]{1,6}$")
_ACRONYM_RE_STRICT = re.compile(r"^[A-Z0-9]{2,3}$")  # for all-caps titles

# Short all-uppercase English words that are NOT acronyms.
_STOP_WORDS: frozenset = frozenset({
    "A", "AN", "THE", "AND", "BUT", "OR", "NOR", "FOR", "YET", "SO",
    "AT", "BY", "IN", "OF", "ON", "TO", "UP", "AS", "IS", "IT",
    "ITS", "BE", "DO", "GO", "IF", "NO", "NOT", "VS",
    # Extended set for all-caps title detection (common 3-letter words)
    "WAS", "ARE", "HAS", "HAD", "HIS", "HER", "OUR", "USE", "NEW",
    "OLD", "ALL", "ANY", "SET", "RUN", "ONE", "TWO", "OWN", "CAN",
    "MAY", "HOW", "WAY", "OUT", "END", "LOW", "BIG", "FEW", "GOT",
    "LET", "PUT", "SAY", "WHO", "WHY", "DID", "TOP", "MID", "KEY",
    "ADD", "CUT", "FIT", "GET", "VIA", "PER", "DUE",
})


def _is_acronym(tok: str, strict: bool = False) -> bool:
    """Return True if *tok* is a short all-uppercase acronym (LHC, BERT, IEEE).

    Also matches pluralised acronyms (LLMs, GPTs) outside strict mode.
    Trailing/leading punctuation is stripped before testing so ``BERT:`` and
    ``LHC,`` still match. Common English stop words (FOR, THE, …) are excluded.
    In strict mode (used when ≥80% of the title is already uppercase) only
    2-3 character tokens qualify so we don't preserve every random capital.
    """
    core = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", tok)
    if not core:
        return False
    pat = _ACRONYM_RE_STRICT if strict else _ACRONYM_RE
    if pat.match(core) and core not in _STOP_WORDS:
        return True
    if not strict:
        m = re.match(r"^([A-Z]{2,6})(s|es|ed)$", core)
        if m and m.group(1) not in _STOP_WORDS:
            return True
    return False


# Whitelist of proper nouns that keep their capitalisation in sentence case.
_PROPER_NOUNS_LOWER: frozenset = frozenset({
    # Scientists / mathematicians used as adjectives
    "turing", "bayesian", "gaussian", "markov", "markovian",
    "fourier", "lagrangian", "hamiltonian", "boolean", "kalman",
    "newtonian", "boltzmann", "maxwell", "maxwellian",
    "coulomb", "lorentz", "lorentzian", "dirac", "hilbert",
    "cauchy", "heisenberg", "hermitian", "euclidean", "cartesian",
    "jacobian", "hessian", "hadamard", "poisson", "laplacian",
    "lyapunov", "chebyshev", "bernoulli", "riemannian",
    "wiener", "feynman", "planck", "doppler", "kelvin",
    "monte", "carlo",  # "Monte Carlo"
    "fermi", "raman", "bragg", "compton", "debye",
    # Place-derived adjectives
    "european", "american", "chinese", "english", "french", "german",
    "japanese", "korean", "italian", "spanish", "russian", "indian",
    "african", "asian", "latin", "arabic", "australian", "canadian",
    "swiss", "brazilian", "swedish", "danish", "dutch", "polish",
    # Companies / products / proper-noun brands
    "google", "github", "wikipedia", "youtube", "twitter",
    "internet",
    # Detector / instrument / facility proper nouns (accelerator physics)
    "jungfrau", "pilatus", "eiger", "mythen", "medipix", "timepix",
})


def _is_mixed_case_name(tok: str) -> bool:
    """Detect intentionally mixed-case tokens (BIGbench, GeV, SwissFEL, DeepSeek)."""
    core = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", tok)
    if len(core) < 2:
        return False
    has_upper = bool(re.search(r"[A-Z]", core))
    has_lower = bool(re.search(r"[a-z]", core))
    if not (has_upper and has_lower):
        return False
    # Simple Title-Case (first upper, rest lower) is NOT mixed-case
    if core[0].isupper() and core[1:].islower():
        return False
    if any(c.isupper() for c in core[1:]):
        return True
    if core[0].islower() and bool(re.search(r"[A-Z]", core)):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Safe-to-lowercase lexicon
# ─────────────────────────────────────────────────────────────────────────────
#
# JACoW wants reference titles in sentence case, which means lowercasing
# ordinary words while leaving proper nouns alone.  Doing that with a
# hand-maintained whitelist of proper nouns cannot work: the set of surnames,
# facilities, codes and instruments in accelerator physics is open-ended, and
# an earlier version of this module lowercased "Poincaré", "Tevatron", "Twiss"
# and "Landau" because they were not on a 60-item list.
#
# The polarity is now inverted.  A Title-Case word is lowercased only when it
# is *positively known* to be an ordinary word; otherwise the function abstains,
# leaves the word exactly as the author wrote it, and reports it so the caller
# can ask a human (or a model — see src/llm/classify.py) instead of guessing.
#
# The shipped lexicon is built from two sources, both of which key on evidence
# rather than opinion:
#
#   1. An English dictionary, restricted to words that have **no** capitalised
#      homograph.  This is what protects Watt, May, March, Kelvin and Newton:
#      each is both a common word and a name, so neither is in the lexicon.
#   2. Words that accelerator-physics authors themselves write in lowercase
#      mid-sentence, mined from the JACoW corpus.  An author never writes a
#      real proper noun in lowercase, so a word seen lowercase in two or more
#      papers is an ordinary word ("emittance", "quadrupole", "symplectic").
#
# Callers may extend it per paper via ``evidence=`` — see
# :func:`lowercase_evidence`, which harvests the same signal from the body text
# of the paper being screened.

_LEXICON_PATH = Path(__file__).with_name("data") / "common_words.txt.gz"
_LEXICON: frozenset | None = None


def safe_to_lowercase_lexicon() -> frozenset:
    """The shipped set of words that may be lowercased in a title."""
    global _LEXICON
    if _LEXICON is None:
        try:
            import gzip

            with gzip.open(_LEXICON_PATH, "rt", encoding="utf-8") as handle:
                _LEXICON = frozenset(line.strip() for line in handle if line.strip())
        except OSError:
            logger.warning(
                "sentence-case lexicon missing at %s; every ambiguous word will be "
                "reported as unsure rather than lowercased", _LEXICON_PATH,
            )
            _LEXICON = frozenset()
    return _LEXICON


_WORD_RE = re.compile(r"(?<![\w./@-])([a-z][a-z\-]{2,})(?![\w./@-])")

# Always safe to lowercase mid-title; never an acronym.
_FUNCTION_WORDS = frozenset({
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor",
    "of", "on", "onto", "or", "over", "per", "the", "to", "up", "upon", "via",
    "with", "within", "without", "is", "are", "was", "were", "be", "been", "its",
    "it", "that", "this", "these", "those", "than", "then", "when", "where",
})


def lowercase_evidence(body_text: str) -> set[str]:
    r"""Words the paper's own prose writes in lowercase.

    Used to extend the shipped lexicon with this paper's vocabulary. If the
    author writes "cryomodule" lowercase in a sentence, it is an ordinary word
    in this field even if no dictionary knows it.
    """
    text = re.sub(r"(?<!\\)%[^\n]*", " ", body_text)
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    return {match.group(1) for match in _WORD_RE.finditer(text)}


# Multi-word proper nouns made entirely of ordinary words.  Word-by-word
# classification cannot possibly catch these — every token in "Large Hadron
# Collider" is an ordinary English word — but the set of accelerator facilities
# and projects is *bounded*, unlike the set of surnames, so a phrase list is
# the right tool here.  Anything not listed and not classifiable is still
# reported as unsure rather than guessed.
_PROPER_PHRASES: tuple[str, ...] = (
    "large hadron collider", "high luminosity large hadron collider",
    "electron ion collider", "electron-ion collider",
    "future circular collider", "compact linear collider",
    "international linear collider", "muon collider",
    "relativistic heavy ion collider", "advanced photon source",
    "national synchrotron light source", "diamond light source",
    "european spallation source", "spallation neutron source",
    "linac coherent light source", "european x-ray free electron laser",
    "swiss light source", "canadian light source", "australian synchrotron",
    "advanced light source", "stanford linear accelerator center",
    "thomas jefferson national accelerator facility",
    "continuous electron beam accelerator facility",
    "facility for rare isotope beams", "rare isotope science project",
    "heavy ion research facility", "china spallation neutron source",
    "shanghai synchrotron radiation facility", "taiwan photon source",
    "taiwan light source", "korea multi-purpose accelerator complex",
    "japan proton accelerator research complex",
    "super proton synchrotron", "proton synchrotron booster",
    "alternating gradient synchrotron", "cornell electron storage ring",
    "argonne wakefield accelerator", "brookhaven national laboratory",
    "los alamos national laboratory", "lawrence berkeley national laboratory",
    "oak ridge national laboratory", "argonne national laboratory",
    "fermi national accelerator laboratory", "paul scherrer institute",
    "helmholtz zentrum berlin", "institute of high energy physics",
    "national institute of standards and technology",
    "department of energy", "national science foundation",
    "european organization for nuclear research",
    "conceptual design report", "technical design report",
    "final design report", "preliminary design report",
    "united states", "united kingdom", "people's republic of china",
    "light source", "free electron laser",
)
_PROPER_PHRASE_TOKENS: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split()) for phrase in
    sorted(_PROPER_PHRASES, key=lambda phrase: -len(phrase.split()))
)


def _protected_indices(tokens: list[str]) -> set[int]:
    """Token positions covered by a known multi-word proper noun."""
    folded = [_fold(token.strip("\u201c\u201d\"'()[],.;:!?")) for token in tokens]
    protected: set[int] = set()
    for phrase in _PROPER_PHRASE_TOKENS:
        length = len(phrase)
        if length < 2:
            continue
        for start in range(len(folded) - length + 1):
            if tuple(folded[start:start + length]) == phrase:
                protected.update(range(start, start + length))
    return protected


class TitleCasing(NamedTuple):
    """Result of a sentence-case pass, including what it refused to decide."""

    text: str
    unsure: tuple[str, ...]
    changed: bool
    protected: tuple[str, ...] = ()

    @property
    def confident(self) -> bool:
        return not self.unsure


# Bibliographic abbreviations whose full stop does NOT end a sentence.  Without
# this, "Proc. IPAC'24" reads as two sentences and IPAC'24 gets recapitalised to
# "Ipac'24" — a real regression caught on the sample .bib files.
_ABBREVIATIONS = frozenset({
    "proc", "procs", "rev", "phys", "nucl", "instrum", "meth", "methods",
    "j", "jour", "vol", "no", "nos", "pp", "p", "ed", "eds", "et", "al",
    "univ", "inst", "lab", "labs", "conf", "trans", "sci", "technol", "tech",
    "appl", "opt", "express", "lett", "commun", "eng", "res", "int", "natl",
    "am", "eur", "chin", "jpn", "sect", "sec", "ser", "suppl", "abstr",
    "rep", "dept", "div", "fig", "figs", "tab", "eq", "eqs", "ref", "refs",
    "chap", "ch", "app", "st", "nd", "rd", "th", "mr", "ms", "dr", "prof",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "cf", "eg", "ie", "etc", "viz", "ibid", "op", "cit",
})


def _is_sentence_start(tokens: list[str], index: int) -> bool:
    """True when the token at *index* begins a sentence.

    A colon always starts one.  A full stop only does when the token it
    terminates is a real word rather than an abbreviation or an initial:
    "magnetic field. Part 1" is two sentences, "Proc. IPAC'24" is not, and
    "M. Ruth" certainly is not.
    """
    if index == 0:
        return True
    previous = tokens[index - 1].rstrip()
    if previous.endswith((":", "?", "!")):
        return True
    if not previous.endswith("."):
        return False

    stem = previous.rstrip(".").strip("\u201c\u201d\"'()[]")
    if len(stem) <= 1:
        return False                          # an initial, e.g. "M."
    folded = _fold(stem)
    if folded in _ABBREVIATIONS:
        return False
    if stem.isupper():
        return False                          # an acronym followed by a stop
    # Only a word we positively recognise ends a sentence.  Anything unknown is
    # treated as an abbreviation, which errs towards leaving capitals alone.
    return folded in safe_to_lowercase_lexicon() and len(stem) >= 3


def _sent_case_token(
    tok: str,
    is_first: bool,
    strict: bool = False,
    lexicon: frozenset | set = frozenset(),
    unsure: list[str] | None = None,
) -> str:
    """Sentence-case a single token, abstaining when it cannot be classified."""
    # Function words are never acronyms, even in an ALL-CAPS title where the
    # strict acronym test would otherwise keep "IN" and "OF" shouting.
    if not is_first and _fold(tok.strip('.,;:!?()[]')) in _FUNCTION_WORDS:
        return tok.lower()
    if _is_acronym(tok, strict=strict):
        return tok
    if _is_mixed_case_name(tok):
        return tok
    if is_first:
        return tok[0].upper() + tok[1:].lower() if tok else tok

    core = tok.strip("\u201c\u201d\"'()[]").rstrip(".,;:!?)")
    if not core or not core[0].isupper():
        return tok.lower() if core.islower() or not core else tok

    key = _fold(core)
    if key in lexicon:
        return tok.lower()

    # Not positively known to be an ordinary word — leave it exactly as the
    # author wrote it and tell the caller.
    if unsure is not None and core not in unsure:
        unsure.append(core)
    return tok


def _fold(word: str) -> str:
    """Lowercase and strip diacritics so 'Poincaré' can be looked up."""
    lowered = word.lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(ch) != "Mn"
    )


def sent_case_report(s: str, *, evidence: set[str] | None = None) -> TitleCasing:
    """Convert *s* to JACoW sentence case, reporting anything it would not decide.

    Rules, in order:

    - The first word, and the first word after a colon or full stop, is
      capitalised.
    - All-caps acronyms (LHC, BERT) and intentionally mixed-case tokens
      (GeV, SwissFEL, DeepSeek) are preserved.
    - A word positively known to be ordinary — in the shipped lexicon or in
      *evidence* — is lowercased.
    - **Anything else is left untouched and listed in**
      :attr:`TitleCasing.unsure`.  A title with any unsure token must not be
      rewritten automatically.
    - Hyphenated compounds are handled segment by segment.
    """
    if not s:
        return TitleCasing(s, (), False)

    lexicon = safe_to_lowercase_lexicon()
    if evidence:
        lexicon = lexicon | {_fold(word) for word in evidence}

    tokens = s.split()
    alpha_cores = [re.sub(r"[^A-Za-z]", "", token) for token in tokens]
    n_alpha = sum(1 for core in alpha_cores if core)
    n_upper = sum(1 for core in alpha_cores if core and core.isupper())
    strict = n_alpha > 0 and n_upper / n_alpha >= 0.8

    unsure: list[str] = []
    out: list[str] = []
    protected_positions = _protected_indices(tokens)
    protected: list[str] = []
    for index, token in enumerate(tokens):
        if index in protected_positions:
            out.append(token)
            if token not in protected:
                protected.append(token)
            continue
        is_first = _is_sentence_start(tokens, index)
        if "-" in token and not token.startswith("-"):
            parts = token.split("-")
            rebuilt: list[str] = []
            for position, part in enumerate(parts):
                if part:
                    rebuilt.append(_sent_case_token(
                        part, is_first and position == 0, strict, lexicon, unsure,
                    ))
                else:
                    rebuilt.append(part)
            out.append("-".join(rebuilt))
        else:
            out.append(_sent_case_token(token, is_first, strict, lexicon, unsure))

    text = " ".join(out)
    return TitleCasing(text, tuple(unsure), text != s, tuple(protected))


def sent_case(s: str, *, evidence: set[str] | None = None) -> str:
    """Sentence-case *s*, abstaining on words that cannot be classified.

    Prefer :func:`sent_case_report` in new code: it tells you which words were
    left alone, which is the difference between a safe rewrite and a silent
    one.
    """
    return sent_case_report(s, evidence=evidence).text


# ─────────────────────────────────────────────────────────────────────────────
# Misc helpers
# ─────────────────────────────────────────────────────────────────────────────

def pages_fmt(s: str) -> str:
    """Normalise page-range punctuation: ``1-3`` / ``1--3`` → ``1–3`` (en dash)."""
    return re.sub(r"(\d)\s*[-–]\s*(\d)", r"\1–\2", (s or "")).replace("--", "–")


def clean_title(t: str) -> str:
    """Strip artefacts that often contaminate auto-extracted titles.

    Removes embedded arXiv IDs, category tags, trailing year, and assorted
    journal-abbreviation fragments that end up appended by heuristic parsers.
    Returns an empty string when *t* looks like a venue header rather than a
    paper title.
    """
    # Remove 'arXiv:XXXX.XXXXX' and optional '[cs.XX]' category
    t = re.sub(r"\s*[Aa]r[Xx]iv:\d{4}\.\d{4,5}(?:v\d+)?\s*(?:\[[a-zA-Z\-.]+\])?", "", t)
    # Remove trailing '(YYYY).' or '(YYYY)'
    t = re.sub(r"\s*\(\d{4}\)\.?\s*$", "", t)
    # Pattern 1: starts with "in Proc." → the conference header got into title
    if re.match(r"^in\s+Proc\.", t, re.IGNORECASE):
        return ""
    # Pattern 2: starts with a bare conf acronym + year (e.g. "IPAC'23, Venice…")
    if re.match(r"^[A-Z][A-Z0-9\-]+['’]\d{2}\b", t):
        return ""
    # Pattern 3: trailing journal-abbreviation fragment absorbed mid-title
    t = re.sub(
        r"\.\s+(?:J\.|Nat\.|Sci\.|Phys\.|Rev\.|Lett\.|Proc\.|"
        r"Ann\.|Adv\.|Int\.|Eur\.|IEEE|ACM|BMJ|Lancet|JMIR|NPJ|npj|"
        r"Radiol\.|Theranostics|N\.)\s*\S*\s*$",
        "",
        t,
    ).strip()
    # Pattern 4: ends with bare single capitalised word absorbed from venue
    if len(t) > 20:
        t = re.sub(r"\s+[A-Z][a-z]+$", "", t).strip()
    t = re.sub(r"\s+", " ", t).strip().rstrip(".")
    return t


def clean_doi(value: str) -> str:
    """Strip ``doi:`` / ``https://doi.org/`` prefixes and trailing punctuation."""
    if not value:
        return ""
    s = str(value).strip()
    s = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi[:\s]+)",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = s.strip().rstrip(".,)>]\"'")
    return s
