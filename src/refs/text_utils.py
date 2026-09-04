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

import re

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


def _sent_case_token(tok: str, is_first: bool, strict: bool = False) -> str:
    """Sentence-case a single token (no hyphens)."""
    if _is_acronym(tok, strict=strict):
        return tok
    if _is_mixed_case_name(tok):
        return tok
    if is_first:
        return tok[0].upper() + tok[1:].lower() if tok else tok
    core = tok.rstrip(".,;:!?)")
    if (
        len(core) > 1
        and core[0].isupper()
        and core[1:].islower()
        and core.lower() in _PROPER_NOUNS_LOWER
    ):
        return tok  # known proper noun — preserve
    return tok.lower()


def sent_case(s: str) -> str:
    """Convert *s* to JACoW sentence case.

    Rules (applied in order):
      - First word, and first word after a colon: capitalise.
      - All-cap acronyms (LHC, BERT, LLMs): preserved.
      - Mixed-case tokens (BIGbench, DeepSeek, GeV): preserved.
      - Known proper nouns in :data:`_PROPER_NOUNS_LOWER`: preserved.
      - Hyphenated compounds: each segment processed independently.
      - Everything else: lower-cased.
      - All-caps titles (≥80% uppercase tokens): stricter acronym test
        (only 2-3 char tokens qualify).
    """
    if not s:
        return s
    tokens = s.split()
    alpha_cores = [re.sub(r"[^A-Za-z]", "", t) for t in tokens]
    n_alpha = sum(1 for c in alpha_cores if c)
    n_upper = sum(1 for c in alpha_cores if c and c.isupper())
    strict = n_alpha > 0 and n_upper / n_alpha >= 0.8
    out: list[str] = []
    for i, tok in enumerate(tokens):
        is_first = (i == 0) or (i > 0 and tokens[i - 1].rstrip().endswith(":"))
        if "-" in tok and not tok.startswith("-"):
            parts = tok.split("-")
            result_parts: list[str] = []
            for j, part in enumerate(parts):
                if part:
                    result_parts.append(
                        _sent_case_token(part, is_first and j == 0, strict=strict)
                    )
                else:
                    result_parts.append(part)
            out.append("-".join(result_parts))
        else:
            out.append(_sent_case_token(tok, is_first, strict=strict))
    return " ".join(out)


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
