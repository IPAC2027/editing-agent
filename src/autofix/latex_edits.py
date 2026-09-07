r"""Span-anchored edit generators for LaTeX source.

Every function here scans the **original, unmodified** source and returns
candidate :class:`~src.edits.Edit` objects with absolute character offsets.
Nothing mutates the source; :meth:`~src.edits.EditSet.apply` does that once,
for whichever subset the editor accepted.

That inversion is what fixes three whole classes of earlier bug:

* a fix can no longer report itself as applied when it changed nothing
  (:func:`~src.edits.make_edit` returns ``None`` for a no-op);
* offsets are exact, so the diff can attribute a highlighted character to the
  edit that produced it instead of guessing by substring search;
* two fixes can no longer silently clobber each other, because overlapping
  spans are resolved by priority in :meth:`~src.edits.EditSet.build`.

Every generator also honours :func:`protected_spans` — regions of a ``.tex``
file where a textual "improvement" is either meaningless or actively wrong
(comments, maths, verbatim, and the argument lists of structural commands).
"""

from __future__ import annotations

import re

from src.edits import Confidence, Edit, Evidence, Tier, make_edit

# ---------------------------------------------------------------------------
# Protected regions
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?:\\.|[^$\\])*\$", re.DOTALL)
_DISPLAY_MATH_RE = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_MATH_ENV_RE = re.compile(
    r"\\begin\{(equation\*?|align\*?|eqnarray\*?|gather\*?|multline\*?|split|"
    r"verbatim|lstlisting|Verbatim|minted|tabular|tabularx|array)\}"
    r".*?\\end\{\1\}",
    re.DOTALL,
)
# Command arguments where prose rules must not apply.
_STRUCTURAL_ARG_RE = re.compile(
    r"\\(?:label|ref|eqref|cref|Cref|autoref|pageref|cite[a-z*]*|includegraphics|"
    r"input|include|bibliography|addbibresource|documentclass|usepackage|url|href|"
    r"nolinkurl|path|verb)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}"
)
_VERB_RE = re.compile(r"\\verb\|[^|]*\||\\verb!\S*?!")


def protected_spans(source: str, *, protect_urls: bool = True) -> list[tuple[int, int]]:
    """Character ranges of *source* that prose-level edits must not touch."""
    spans: list[tuple[int, int]] = []
    patterns = [
        _COMMENT_RE,
        _INLINE_MATH_RE,
        _DISPLAY_MATH_RE,
        _MATH_ENV_RE,
        _VERB_RE,
    ]
    if protect_urls:
        patterns.append(_STRUCTURAL_ARG_RE)
    for pattern in patterns:
        for match in pattern.finditer(source):
            spans.append(match.span())
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _blocked(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    for s_start, s_end in spans:
        if start < s_end and s_start < end:
            return True
        if s_start > end:
            break
    return False


def bibliography_span(source: str) -> tuple[int, int] | None:
    """Span of the ``thebibliography`` environment, if there is one."""
    match = re.search(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", source, re.DOTALL
    )
    return match.span() if match else None


# ---------------------------------------------------------------------------
# Units  (FMT-UNIT-01 / FMT-UNIT-02)
# ---------------------------------------------------------------------------

# Canonical SI-style units JACoW papers actually use.  Note the deliberate
# absence of "%": a bare percent sign in LaTeX starts a comment, so the literal
# is "\%" and is handled by its own rule below.
#
# Prefixed variants are listed *deliberately and generously*, because the table
# is what makes case ambiguity detectable.  With both mT and MT present,
# "0.4 MT/m" (megatesla per metre — a real plasma-lens gradient) is correctly
# left alone instead of being "corrected" to millitesla.
_CANONICAL_UNITS = frozenset({
    "eV", "meV", "keV", "MeV", "GeV", "TeV", "PeV",
    "Hz", "kHz", "MHz", "GHz", "THz",
    "m", "pm", "nm", "um", "mm", "cm", "km",
    "s", "fs", "ps", "ns", "us", "ms", "min", "h",
    "A", "pA", "nA", "uA", "mA", "kA", "MA",
    "V", "uV", "mV", "kV", "MV", "GV", "TV",
    "W", "uW", "mW", "kW", "MW", "GW", "TW", "PW",
    # Gauss, with its prefixes.  They are here for the same reason mT and MT
    # are: to make "mG" and "mg" collide so that *neither* is case-corrected.
    # Without the prefixed forms, "0.5 mG" (milligauss, an ordinary stray-field
    # figure) lowercased to the unique key "mg" and was rewritten to
    # milligrams.  Found by measuring against NAPAC2025, where the editors had
    # written 0.5\,mG and the agent proposed 0.5~mg.
    "T", "nT", "uT", "mT", "kT", "MT", "GT",
    "G", "uG", "mG", "kG", "MG",
    "K", "mK", "uK",
    "Pa", "hPa", "kPa", "MPa", "GPa", "bar", "mbar", "Torr", "mTorr",
    "rad", "urad", "mrad", "sr", "deg",
    "Gy", "mGy", "kGy", "Bq", "Sv", "mSv", "uSv",
    "C", "pC", "nC", "uC", "mC",
    "g", "mg", "ug", "kg",
    "mol", "cd", "lm", "lx",
    "F", "pF", "nF", "uF", "mF", "H", "nH", "uH", "mH",
    "ohm", "kohm", "Mohm",
    "J", "mJ", "uJ", "kJ", "MJ", "GJ",
    "N", "mN", "kN",
    "dB", "dBm", "ppm", "ppb", "rpm", "eVs",
})


def _build_unit_index() -> tuple[dict[str, str], frozenset]:
    """Case-insensitive unit index, with ambiguous spellings *excluded*.

    The previous implementation was a dict comprehension over a ``set``, so the
    key "mv" mapped to mV or MV depending on the interpreter's hash seed — the
    same input could be "corrected" in opposite directions on two runs, and
    "5 mV" could silently become "5 MV".  Here a spelling that more than one
    canonical unit shares is dropped from the index entirely, which makes it
    ineligible for case correction rather than resolved by luck.
    """
    buckets: dict[str, set[str]] = {}
    for unit in _CANONICAL_UNITS:
        buckets.setdefault(unit.lower(), set()).add(unit)
    unique = {key: next(iter(values)) for key, values in buckets.items() if len(values) == 1}
    ambiguous = frozenset(key for key, values in buckets.items() if len(values) > 1)
    return unique, ambiguous


_UNIT_BY_LOWER, _AMBIGUOUS_UNIT_KEYS = _build_unit_index()
_ALL_UNIT_KEYS: frozenset = frozenset(u.lower() for u in _CANONICAL_UNITS)

_NUMBER_UNIT_RE = re.compile(
    r"(?<![\\\w.])"
    r"(?P<number>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
    r"(?P<sep>[ \t]+|\\,|~)"
    r"(?P<unit>[A-Za-zµΩ]+)(?![A-Za-z])"
)

# A number preceded by one of these is a label, not a measurement.
_COUNTER_WORD_RE = re.compile(
    r"(?:Fig(?:ure)?s?|Tab(?:le)?s?|Sec(?:tion)?s?|Eq(?:uation)?s?|Ref(?:erence)?s?|"
    r"Chap(?:ter)?s?|App(?:endix)?|No|Nos|page|pages|p|pp|vol|volume|item|step|"
    r"phase|type|class|mode|run|shot|case|option|version|v)\.?\s*$",
    re.IGNORECASE,
)

_UNIT_RULE = "JACoW: a non-breaking space separates a value from its unit"
_UNIT_CASE_RULE = "JACoW: use the standard SI abbreviation and case"


def unit_edits(source: str, file: str = "") -> list[Edit]:
    r"""FMT-UNIT-01/02 as **one edit per measurement**.

    Spacing and unit case are decided together and emitted as a single edit, so
    the two can never race each other for the same span (which silently dropped
    the case fix in an earlier draft).

    * Spacing only  → :attr:`Tier.AUTO`.  Unambiguous, trivially reversible, and
      by far the most common JACoW nit: 214 of them in the 34-paper sample.
    * Unit case too → :attr:`Tier.SUGGEST`.  Changing ``Mev`` to ``MeV`` is
      safe; changing ``MT`` to ``mT`` is a factor of 10^9.  Case is therefore
      only ever *offered*, and only when the spelling is unambiguous.
    """
    spans = protected_spans(source)
    edits: list[Edit] = []

    siunitx = has_siunitx(source)
    for match in _NUMBER_UNIT_RE.finditer(source):
        if _blocked(spans, *match.span()):
            continue
        unit = match.group("unit")
        key = unit.lower()
        if key not in _ALL_UNIT_KEYS:
            continue

        # "Figure 2 A" / "Table 3 K" are labels, not measurements.
        if _COUNTER_WORD_RE.search(source[max(0, match.start() - 24):match.start()]):
            continue

        number = match.group("number")
        separator = match.group("sep")
        canonical = _UNIT_BY_LOWER.get(key)

        needs_space = separator not in ("~", "\\,")
        # Correct case only when exactly one canonical unit has this spelling.
        # An ambiguous spelling (mT/MT, mV/MV, mW/MW, mA/MA) is left alone: the
        # author's capitalisation is the only evidence of which they meant.
        needs_case = (
            canonical is not None
            and unit != canonical
            and len(canonical) > 1
            and key not in _AMBIGUOUS_UNIT_KEYS
        )
        if not (needs_space or needs_case):
            continue

        new_unit = canonical if needs_case else unit
        if siunitx:
            # House style for a measurement is \qty{N}{unit}. Applied only
            # where a fix was needed anyway: converting every already-correct
            # "10~MeV" as well would put sixty edits on a paper that has
            # nothing wrong with it.
            replacement = f"\\qty{{{number}}}{{{new_unit}}}"
        else:
            new_sep = "~" if needs_space else separator
            replacement = f"{number}{new_sep}{new_unit}"

        if needs_case:
            check_id, tier = "FMT-UNIT-02", Tier.SUGGEST
            confidence = Confidence.LIKELY
            message = (
                f"Unit abbreviation case: {unit} → {canonical}"
                + (" (and a non-breaking space before it)." if needs_space else ".")
                + " Check this is the quantity you meant before accepting."
            )
            rule = _UNIT_CASE_RULE
        else:
            check_id, tier = "FMT-UNIT-01", Tier.AUTO
            confidence = Confidence.CERTAIN
            if siunitx:
                message = ("Write the measurement as \\qty{N}{unit}, the JACoW "
                           "form, so the number and its unit cannot be split "
                           "across lines.")
                rule = _UNIT_RULE
                edit = make_edit(
                    source, match, replacement, check_id=check_id, tier=tier,
                    confidence=confidence, message=message, rule=rule, file=file,
                )
                if edit:
                    edits.append(edit)
                continue
            message = f"Non-breaking space between value and unit: {number}~{unit}."
            rule = _UNIT_RULE

        edit = make_edit(
            source, match, replacement,
            check_id=check_id,
            tier=tier,
            confidence=confidence,
            message=message,
            rule=rule,
            file=file,
        )
        if edit:
            edits.append(edit)

    # "50 \%" -> "50~\%"
    for match in re.finditer(r"(?<![\\\w.])([+-]?(?:\d+(?:\.\d+)?|\.\d+))([ \t]+)(\\%)", source):
        if _blocked(spans, *match.span()):
            continue
        edit = make_edit(
            source, match, f"{match.group(1)}~{match.group(3)}",
            check_id="FMT-UNIT-01",
            tier=Tier.AUTO,
            message="Non-breaking space before the percent sign.",
            rule=_UNIT_RULE,
            file=file,
        )
        if edit:
            edits.append(edit)

    return edits


# ---------------------------------------------------------------------------
# DOI presentation  (DOI-FMT-01 / DOI-FMT-02)
# ---------------------------------------------------------------------------

_DOI_PREFIX_RE = re.compile(
    r"(?<![\w.])(?P<prefix>DOI|Doi|doi|DOI:|Doi:|doi:)(?P<gap>\s*:?\s*)(?P<doi>10\.\d{4,9}/[^\s,;)\]}$]+)"
)
_URL_DOI_RE = re.compile(
    r"\\url\{\s*(?:https?://(?:dx\.)?doi\.org/|[Dd][Oo][Ii]\s*:\s*)(10\.\d{4,9}/[^}\s]+?)\s*\}"
)
_HREF_DOI_RE = re.compile(
    r"\\href\{\s*https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[^}\s]+?)\s*\}\{[^}]*\}"
)
_BARE_DOI_URL_RE = re.compile(
    r"(?<!\{)(?<!//)https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s,;)\]}]+)"
)

_DOI_RULE = "JACoW Annex B: DOIs are written doi:10.xxxx/yyyy (or \\doi{...} in LaTeX)"


# ---------------------------------------------------------------------------
# What this document can actually render
#
# House style says a DOI is written \doi{...} and a measurement \qty{N}{unit}.
# Both are macros, and emitting a macro a paper does not define turns a
# formatting fix into a build failure — the most expensive mistake this tool
# can make. So each is used only where the document already has it, and the
# safe older form is kept where it does not.
# ---------------------------------------------------------------------------

# The option list routinely spans lines:
#     \documentclass[a4paper,
#                    keeplastbox]{jacow}
# A pattern anchored with [^\n]* missed 82% of a real conference, which made
# the agent fall back to the "doi:" form on papers that could render \doi{}
# perfectly well. Options may contain anything but a closing bracket.
_JACOW_CLASS_RE = re.compile(
    r"\\documentclass\s*(?:\[[^\]]*\]\s*)?\{[^}]*jacow[^}]*\}", re.IGNORECASE)
_DOI_DEFINED_RE = re.compile(r"\\(?:new|renew|provide)command\*?\s*\{?\\doi\b")
_DOI_USED_RE = re.compile(r"\\doi\s*\{")
_SIUNITX_RE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\]\s*)?\{[^}]*\bsiunitx\b[^}]*\}")
_SIUNITX_USED_RE = re.compile(r"\\(?:qty|SI|num|si)\s*[\{\[]")


def has_doi_macro(source: str) -> bool:
    r"""Can this paper render ``\doi{...}``?

    True for the JACoW class, which provides it, and for any paper that defines
    or already uses the macro.
    """
    return bool(_JACOW_CLASS_RE.search(source)
                or _DOI_DEFINED_RE.search(source)
                or _DOI_USED_RE.search(source))


def has_siunitx(source: str) -> bool:
    r"""Can this paper render ``\qty{10}{MeV}``?"""
    return bool(_SIUNITX_RE.search(source) or _SIUNITX_USED_RE.search(source))


def _trim_doi(doi: str) -> tuple[str, str]:
    """Split trailing sentence punctuation off a DOI token."""
    match = re.match(r"^(.*?)([.,;:]*)$", doi, re.DOTALL)
    if not match:
        return doi, ""
    return match.group(1), match.group(2)


def doi_format_edits(source: str, file: str = "") -> list[Edit]:
    """DOI-FMT-01/02 as edits — all AUTO, all pure presentation.

    Crucially these are generated from the original text and rejected when they
    would be no-ops, so an already-correct ``doi:10.1103/…`` produces nothing
    at all.  That alone removed 7 of the 9 "auto-fixes" the previous version
    reported on the sample corpus.
    """
    edits: list[Edit] = []
    # \url{doi:...} and \url{https://doi.org/...} → \doi{...}
    for match in _URL_DOI_RE.finditer(source):
        doi, trail = _trim_doi(match.group(1))
        edit = make_edit(
            source, match, f"\\doi{{{doi}}}{trail}",
            check_id="DOI-FMT-02",
            tier=Tier.AUTO,
            message="Use \\doi{...} rather than \\url{} for a DOI so it renders as JACoW expects.",
            rule=_DOI_RULE,
            file=file,
        )
        if edit:
            edits.append(edit)

    for match in _HREF_DOI_RE.finditer(source):
        doi, trail = _trim_doi(match.group(1))
        edit = make_edit(
            source, match, f"\\doi{{{doi}}}{trail}",
            check_id="DOI-FMT-02",
            tier=Tier.AUTO,
            message="Use \\doi{...} rather than \\href{} for a DOI.",
            rule=_DOI_RULE,
            file=file,
        )
        if edit:
            edits.append(edit)

    # Bare https://doi.org/... outside any command
    protected = protected_spans(source)
    for match in _BARE_DOI_URL_RE.finditer(source):
        if _blocked(protected, *match.span()):
            continue
        doi, trail = _trim_doi(match.group(1))
        edit = make_edit(
            source, match, f"\\doi{{{doi}}}{trail}",
            check_id="DOI-FMT-02",
            tier=Tier.AUTO,
            message="A doi.org link is written \\doi{10.xxxx/yyyy} in JACoW references.",
            rule=_DOI_RULE,
            file=file,
        )
        if edit:
            edits.append(edit)

    # A written-out DOI becomes the macro: JACoW style is \doi{10.xxxx/yyyy},
    # not a "doi:" prefix. Measured against NAPAC2025, every editor who touched
    # one of these wrote the macro, and the agent's prefix-only fix left work
    # behind — which is why it showed up as disagreement rather than absence.
    macro = has_doi_macro(source)
    for match in _DOI_PREFIX_RE.finditer(source):
        if source[max(0, match.start() - 6):match.start()].endswith("\\"):
            continue  # part of \doi{...}
        doi, trail = _trim_doi(match.group("doi"))
        if macro:
            # JACoW writes no full stop after the DOI, and it is the last
            # element of a reference — so the trailing punctuation goes only
            # when nothing follows it on the line. Anywhere else it is
            # sentence punctuation and stays: removing that would be an edit
            # about prose, not about the DOI.
            rest = source[match.end():]
            ends_the_entry = rest[:rest.find("\n") if "\n" in rest else None].strip() == ""
            keep = "" if (ends_the_entry and trail in (".", "")) else trail
            replacement = f"\\doi{{{doi}}}{keep}"
            message = ("Write the DOI as \\doi{10.xxxx/yyyy}, which is the JACoW "
                       "form and renders as a link.")
        else:
            # No \doi to call: normalise the prefix and leave the rest alone
            # rather than emitting a macro that would not compile.
            replacement = f"doi:{doi}{trail}"
            message = ("Normalise the DOI prefix to lowercase 'doi:' with no "
                       "space. (This paper does not provide \\doi{...}, which "
                       "is the preferred form.)")
        edit = make_edit(
            source, match, replacement,
            check_id="DOI-FMT-01",
            tier=Tier.AUTO,
            message=message,
            rule=_DOI_RULE,
            file=file,
        )
        if edit:
            edits.append(edit)

    return edits


# ---------------------------------------------------------------------------
# Citation brackets  (CITE-BRACKET-01 / CITE-SPACE-01)
# ---------------------------------------------------------------------------

_ADJACENT_CITE_RE = re.compile(r"\[(\d[\d,\s\u2013-]*?)\]\s*\[(\d[\d,\s\u2013-]*?)\]")
_SPACED_CITE_RE = re.compile(r"\[[ \t]+(\d[\d,\s\u2013-]*?\d|\d)[ \t]+\]")
_TIGHT_COMMA_CITE_RE = re.compile(r"\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\]")

# A bracket is a citation only if it is preceded by a citation cue or sits at a
# clause boundary.  "A[1,2]" (a matrix element) is not.
_CITE_CUE_RE = re.compile(
    r"(?:\bRefs?\.?|\bReferences?|\bin|\bsee|\bfrom|\bof|\bby|\band|\bto|\bcf\.?|"
    r"[\s,;:)\]}~]|^)\s*$",
    re.IGNORECASE,
)


def _is_citation_bracket(source: str, start: int) -> bool:
    """True when the ``[`` at *start* is plausibly a rendered citation."""
    preceding = source[max(0, start - 30):start]
    if not preceding:
        return True
    # Directly attached to a word/number/closing brace → an index, not a cite.
    if re.search(r"[A-Za-z0-9_}\)]$", preceding):
        return bool(re.search(r"(?:Refs?\.?|References?)\s*$", preceding, re.IGNORECASE))
    return bool(_CITE_CUE_RE.search(preceding))


def citation_bracket_edits(source: str, file: str = "") -> list[Edit]:
    """Merge and tidy *rendered* citation brackets, never array indices."""
    spans = protected_spans(source)
    edits: list[Edit] = []

    for match in _ADJACENT_CITE_RE.finditer(source):
        if _blocked(spans, *match.span()) or not _is_citation_bracket(source, match.start()):
            continue
        left = re.sub(r"\s+", " ", match.group(1)).strip()
        right = re.sub(r"\s+", " ", match.group(2)).strip()
        edit = make_edit(
            source, match, f"[{left}, {right}]",
            check_id="CITE-BRACKET-01",
            tier=Tier.AUTO,
            message=f"Merge adjacent citation brackets: {match.group(0)} → [{left}, {right}].",
            rule="JACoW: multiple citations share one bracket, comma-separated",
            file=file,
        )
        if edit:
            edits.append(edit)

    for match in _SPACED_CITE_RE.finditer(source):
        if _blocked(spans, *match.span()) or not _is_citation_bracket(source, match.start()):
            continue
        inner = re.sub(r"\s*,\s*", ", ", match.group(1).strip())
        edit = make_edit(
            source, match, f"[{inner}]",
            check_id="CITE-SPACE-01",
            tier=Tier.AUTO,
            message="Remove padding spaces inside a citation bracket.",
            rule="JACoW: no space inside citation brackets",
            file=file,
        )
        if edit:
            edits.append(edit)

    for match in _TIGHT_COMMA_CITE_RE.finditer(source):
        if _blocked(spans, *match.span()) or not _is_citation_bracket(source, match.start()):
            continue
        inner = re.sub(r"\s*,\s*", ", ", match.group(1))
        inner = re.sub(r"\s*[\u2013-]\s*", "-", inner)
        edit = make_edit(
            source, match, f"[{inner}]",
            check_id="CITE-SPACE-01",
            tier=Tier.AUTO,
            message="One space after each comma inside a citation bracket.",
            rule="JACoW: citation lists read [1, 2, 5-7]",
            file=file,
        )
        if edit:
            edits.append(edit)

    return edits


# ---------------------------------------------------------------------------
# et al.  (AUTH-02)
# ---------------------------------------------------------------------------

# Only the *broken* spellings are matched, and the replacement preserves the
# original capitalisation of "et" so an all-caps title is not quietly
# lower-cased.
_ETAL_RE = re.compile(
    r"\b(?P<et>[Ee][Tt]|ET)(?P<mid>\.?[ \t]+|[ \t]*\.[ \t]*)(?P<al>[Aa][Ll]|AL)(?P<dot>\.?)(?![A-Za-z.])"
)


def etal_edits(source: str, file: str = "") -> list[Edit]:
    """Normalise ``et. al`` / ``et al`` to ``et al.`` without touching case."""
    spans = protected_spans(source)
    edits: list[Edit] = []
    for match in _ETAL_RE.finditer(source):
        if _blocked(spans, *match.span()):
            continue
        et, al = match.group("et"), match.group("al")
        # House style italicises it. Not applied when the author has already
        # wrapped it in an emphasis command, which would nest two of them.
        preceding = source[max(0, match.start() - 12):match.start()]
        already_emphasised = re.search(r"\\(?:emph|textit|textsl)\s*\{\s*$",
                                       preceding) is not None
        if already_emphasised:
            replacement = f"{et} {al}."
        else:
            replacement = f"\\emph{{{et} {al}.}}"
        edit = make_edit(
            source, match, replacement,
            check_id="AUTH-02",
            tier=Tier.AUTO,
            message=("Write it as \\emph{et al.} — italicised, no full stop "
                     "after 'et', one after 'al'."),
            rule="JACoW Annex B: 'et al.' punctuation",
            file=file,
        )
        if edit:
            edits.append(edit)
    return edits


# ---------------------------------------------------------------------------
# Author list  (FMT-AUTH-01 corrections, suggestion tier)
# ---------------------------------------------------------------------------

# A name with at least one given name written out in full.
#
# Three traps this has to avoid, all found on real submissions:
#
# * "D. Edstrom Jr." — the given name is already an initial and "Jr" is a
#   suffix, not a surname.  An earlier version offered "Edstrom Jr" -> "E. Jr",
#   which is not a name at all.
# * "Mary Jane Watson" — must become "M. J. Watson", not "M. Jane"; the pattern
#   has to consume every given name, not just the first.
# * "Derong Xu, Brookhaven National Laboratory" — the match must stop at the
#   comma, so an affiliation can never be read as a surname.
_NAME_SUFFIXES = frozenset({
    "jr", "sr", "ii", "iii", "iv", "phd", "md", "esq",
})
_NOT_A_SURNAME = frozenset({
    "university", "universite", "laboratory", "laboratories", "institute",
    "institut", "national", "center", "centre", "college", "school",
    "department", "division", "facility", "academy", "research", "technology",
    "alamos", "haven", "ridge", "valley", "park", "hill", "city", "state",
})
_FULL_FIRST_NAME_RE = re.compile(
    r"(?<![A-Za-z.])"
    r"(?P<pre>(?:[A-Z]\.[ \t]*)*)"                       # leading initials, kept as-is
    r"(?P<given>[A-Z][a-z]{2,}(?:[ \t]+[A-Z][a-z]{2,})*)"  # given name(s) in full
    r"(?P<mid>(?:[ \t]+[A-Z]\.)*)"                       # middle initials
    r"[ \t]+"
    r"(?P<last>[A-Z][A-Za-z'\u2019\-]+\.?)"              # surname
    r"(?=[ \t]*(?:,|;|\\|\}|$))"                         # ...and then a boundary
)


def _initials(given: str) -> str:
    return " ".join(f"{word[0]}." for word in given.split())


def author_initial_edits(source: str, author_span: tuple[int, int] | None,
                         file: str = "") -> list[Edit]:
    """Suggest ``Initials Surname`` where a given name was written out in full.

    Restricted to the ``\author{}`` names region so no body text and no
    affiliation is ever touched, and always :attr:`Tier.SUGGEST`: only the
    author can confirm which token is the given name.
    """
    if not author_span:
        return []
    start, end = author_span
    region = source[start:end]
    # Footnotes and emails sit inside the names region; blank them
    # length-preservingly so an address never looks like a name.
    searchable = re.sub(
        r"\\(?:thanks|footnote|email|orcid)\s*\{[^{}]*\}",
        lambda m: " " * len(m.group(0)),
        region,
    )
    edits: list[Edit] = []
    for match in _FULL_FIRST_NAME_RE.finditer(searchable):
        given, last = match.group("given"), match.group("last")
        if last.lower().strip(".") in _NAME_SUFFIXES:
            continue                      # a surname followed by a suffix
        if last.lower().strip(".") in _NOT_A_SURNAME:
            continue                      # an affiliation, not a person
        if any(word.lower() in _NOT_A_SURNAME for word in given.split()):
            continue
        if any(word.lower() in _NAME_SUFFIXES for word in given.split()):
            continue

        pre = match.group("pre")
        middle = match.group("mid").strip()
        replacement = pre + _initials(given)
        if middle:
            replacement += " " + middle
        replacement += " " + last

        abs_start = start + match.start()
        abs_end = start + match.end()
        before = source[abs_start:abs_end]
        if before == replacement:
            continue
        edits.append(Edit(
            check_id="FMT-AUTH-01",
            tier=Tier.SUGGEST,
            confidence=Confidence.LIKELY,
            file=file,
            start=abs_start,
            end=abs_end,
            before=before,
            after=replacement,
            message=(
                f"JACoW author lists use initials: '{before.strip()}' becomes "
                f"'{replacement.strip()}'. Reject if the first word is not a given name."
            ),
            rule="JACoW: authors are listed as 'Initials Surname'",
        ))
    return edits


# ---------------------------------------------------------------------------
# Title trailing punctuation  (FMT-TITLE-02)
# ---------------------------------------------------------------------------

def title_punctuation_edits(source: str, title_span: tuple[int, int] | None,
                            file: str = "") -> list[Edit]:
    """FMT-TITLE-02: a JACoW title carries no terminal punctuation.

    *title_span* must be the span of the title **text**, not of the whole
    ``\title{}`` argument: the argument usually ends with a ``\thanks{...}``
    footnote whose closing full stop is not the title's.
    """
    if not title_span:
        return []
    start, end = title_span
    region = source[start:end]
    match = re.search(r"[.,;:!]+\s*$", region.rstrip())
    if not match:
        return []
    stripped_len = len(region.rstrip())
    abs_start = start + match.start()
    abs_end = start + min(match.end(), stripped_len)
    if abs_end <= abs_start:
        return []
    return [Edit(
        check_id="FMT-TITLE-02",
        tier=Tier.SUGGEST,
        file=file,
        start=abs_start,
        end=abs_end,
        before=source[abs_start:abs_end],
        after="",
        message="A JACoW title does not end with punctuation.",
        rule="JACoW: no terminal punctuation in \\title{}",
    )]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def all_source_edits(
    source: str,
    *,
    file: str = "",
    author_span: tuple[int, int] | None = None,
    title_span: tuple[int, int] | None = None,
) -> list[Edit]:
    """Every source-level candidate edit, unordered and possibly overlapping.

    :meth:`~src.edits.EditSet.build` is responsible for verifying, ordering and
    de-overlapping them.
    """
    return [
        *doi_format_edits(source, file),
        *unit_edits(source, file),
        *citation_bracket_edits(source, file),
        *etal_edits(source, file),
        *author_initial_edits(source, author_span, file),
        *title_punctuation_edits(source, title_span, file),
    ]
