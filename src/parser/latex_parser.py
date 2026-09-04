"""LaTeX source parser — Phase 1 implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from src.models import Paper, Reference

# Latest JACoW class version published on https://jacow.org/Authors/Templates
JACOW_LATEST_VERSION = "3.0"
JACOW_LATEST_DATE = "2026-02-10"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class CiteOccurrence(NamedTuple):
    key: str
    line: int        # 1-based source line number
    raw: str         # full \cite{...} token as it appears in source


@dataclass
class ParsedTex:
    """Intermediate structure holding everything extracted from one .tex file."""
    source_lines: list[str]              # original lines (1-indexed via [i-1])
    paper_id: str = ""
    title_raw: str = ""
    author_raw: str = ""
    documentclass_opts: str = ""         # options string from \documentclass[...]{jacow}
    template_version: str = ""           # e.g. "2.3" from comment "% v 2.3  ..."
    uses_biblatex: bool = False
    cite_occurrences: list[CiteOccurrence] = field(default_factory=list)
    bibitems: list[tuple[str, str]] = field(default_factory=list)  # (key, raw_text)
    has_bibliography_section: bool = False
    bibliography_env: str = ""           # "thebibliography", "bibtex", or "biblatex"
    figure_labels: list[str] = field(default_factory=list)
    table_labels: list[str] = field(default_factory=list)
    # Character spans of the \title{} / \author{} arguments in the raw source.
    # Edit generators need these so author- and title-level rules can never
    # touch body text.
    title_span: tuple[int, int] | None = None
    author_span: tuple[int, int] | None = None
    # Narrower spans covering only the *text* an edit may touch: the title
    # without its \thanks tail, and the author names without affiliations,
    # emails or footnotes.  Edit generators use these, never the full argument.
    title_text_span: tuple[int, int] | None = None
    author_names_span: tuple[int, int] | None = None
    affiliations: list[str] = field(default_factory=list)


# JACoW author blocks put affiliations either after a "\\" break or inline,
# after the last name.  These tokens mark the start of an affiliation.
_AFFILIATION_CUE_RE = re.compile(
    r"\b(?:University|Universit[a-zé]+|Institute|Institut|Laborator(?:y|ies)|Lab|"
    r"National|Center|Centre|College|School|Department|Dept|Division|Facility|"
    r"Academy|Academia|Research|Technolog(?:y|ies)|Corporation|Company|Ltd|Inc|GmbH|"
    r"CERN|DESY|KEK|SLAC|Fermilab|CEA|CNRS|INFN|JINR|PSI|ESRF|ESS|ORNL|BNL|ANL|LBNL|"
    r"LANL|JLab|TRIUMF|RIKEN|IHEP|MAX\s*IV|Diamond|Elettra|ALBA|SOLEIL|Sirius)\b",
    re.IGNORECASE,
)

# "Initials Surname" — the JACoW convention.  Allows compound and particled
# surnames ("van der Meer", "Le Duff", "O'Shea", "Garcia-Lopez").
# "Initials Surname", where the surname may itself contain nobiliary or
# patronymic particles anywhere in the sequence — "van der Meer",
# "Hoffstaetter de Torquat", "Le Duff", "O'Shea", "Garcia-Lopez".
_NAME_PARTICLE = (
    r"(?:de|del|den|der|di|du|da|das|dos|la|las|le|les|van|von|vander|ter|ten|"
    r"el|al|bin|ibn|abu|mac|mc|st|of|y|e|i)"
)
_JACOW_NAME_RE = re.compile(
    r"^(?:[A-Z]\.[\s\-]*)+"
    r"(?:" + _NAME_PARTICLE + r"[\s\-])*"
    r"[A-Z][\w'\u2019\-]*"
    r"(?:[\s\-](?:" + _NAME_PARTICLE + r"|[A-Z][\w'\u2019\-]*))*$",
    re.UNICODE,
)


def _strip_comment(line: str) -> str:
    """Remove trailing LaTeX comment from a single line (respects \\%)."""
    result = re.sub(r'(?<!\\)%.*', '', line)
    return result


def _blank_comment(line: str) -> str:
    """Blank a LaTeX comment **without changing the line's length**.

    Offsets matter: :attr:`ParsedTex.title_span` and
    :attr:`ParsedTex.author_span` are handed to the edit generators, which use
    them to index into the *raw* source.  Deleting comment text shifts every
    later character, which silently pointed the title and author spans at
    unrelated bytes (the ``\\documentclass`` option block, in practice).
    """
    def _pad(match: re.Match) -> str:
        return " " * len(match.group(0))

    return re.sub(r'(?<!\\)%.*', _pad, line)


def _extract_braced(text: str, pos: int) -> tuple[str, int]:
    """Extract balanced-brace content starting at *pos* (which must be '{').

    Returns ``(content, end_pos)`` where *end_pos* is the index after the closing
    brace.  Handles nested braces and escaped braces ``\\{`` / ``\\}``.
    """
    if pos >= len(text) or text[pos] != '{':
        return "", pos
    depth = 0
    buf: list[str] = []
    i = pos
    while i < len(text):
        ch = text[i]
        if i > 0 and text[i - 1] == '\\':
            buf.append(ch)
            i += 1
            continue
        if ch == '{':
            depth += 1
            if depth > 1:
                buf.append(ch)
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return ''.join(buf), i + 1
            else:
                buf.append(ch)
        else:
            buf.append(ch)
        i += 1
    return ''.join(buf), i


def _trim_span(source: str, span: tuple[int, int], markers: tuple[str, ...]) -> tuple[int, int]:
    """Shorten *span* to stop before the first of *markers*."""
    start, end = span
    region = source[start:end]
    cut = len(region)
    for marker in markers:
        found = re.search(marker, region)
        if found:
            cut = min(cut, found.start())
    return (start, start + cut)


def _blank_groups(text: str, commands: tuple[str, ...]) -> str:
    """Replace ``\\cmd{...}`` groups with spaces, preserving every offset."""
    result = text
    for command in commands:
        pattern = re.compile(r"\\" + command + r"\s*\{[^{}]*\}")
        result = pattern.sub(lambda m: " " * len(m.group(0)), result)
    return result


def _author_names_span(source: str, span: tuple[int, int]) -> tuple[int, int]:
    r"""Span covering only the author *names* inside an ``\author{}`` argument.

    Stops at the first ``\\`` line break and at the first affiliation cue, so a
    name-level edit can never reach "Los Alamos National Laboratory" (which the
    initials rule would otherwise offer to shorten to "L. Alamos") or an email
    address inside ``\thanks{}``.
    """
    start, end = span
    region = source[start:end]
    cut = len(region)
    brk = region.find("\\\\")
    if brk >= 0:
        cut = min(cut, brk)
    # Blank footnote/thanks groups (length-preserving) before looking for an
    # affiliation cue: an email like "kaemingk@lanl.gov" contains "LANL", which
    # would otherwise truncate the author list after the first name.
    searchable = _blank_groups(region[:cut], ("thanks", "footnote", "email", "orcid"))
    cue = _AFFILIATION_CUE_RE.search(searchable)
    if cue:
        # Back up to the separator before the cue so a trailing ", " is excluded.
        boundary = region.rfind(",", 0, cue.start())
        cut = boundary if boundary > 0 else cue.start()
    return (start, start + cut)


def _find_command_arg(text: str, cmd: str) -> str:
    """Return the content of the first ``\\cmd{...}`` found in *text*."""
    pat = re.compile(r'\\' + re.escape(cmd) + r'\s*(\{)', re.DOTALL)
    m = pat.search(text)
    if not m:
        return ""
    content, _ = _extract_braced(text, m.start(1))
    return content.strip()


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_latex(tex_path: Path) -> Paper:
    """Parse *tex_path* and return a populated :class:`~src.models.Paper`."""
    source = tex_path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()

    pt = ParsedTex(source_lines=lines)
    pt.paper_id = tex_path.stem

    # ------------------------------------------------------------------
    # 1. Template version from first few comment lines  "% v 2.3  ..."
    # ------------------------------------------------------------------
    for ln in lines[:15]:
        m = re.match(r'^\s*%\s+v\s+(\d+\.\d+)', ln)
        if m:
            pt.template_version = m.group(1)
            break

    # ------------------------------------------------------------------
    # 2. \documentclass options
    # ------------------------------------------------------------------
    dc_m = re.search(r'\\documentclass\s*\[([^\]]*)\]\s*\{jacow\}', source, re.DOTALL)
    if dc_m:
        pt.documentclass_opts = dc_m.group(1)
        # Strip % comments from options before checking — e.g. "%biblatex,"
        # must not be treated as an active option.
        opts_active = re.sub(r'%[^\n]*', '', pt.documentclass_opts)
        if re.search(r'\bbiblatex\b', opts_active):
            pt.uses_biblatex = True

    # \addbibresource outside a documentclass option is NOT a reliable signal:
    # JACoW templates include it inside \ifboolexpr{bool{jacowbiblatex}}{...}
    # even when the biblatex option is commented out. So we do not use it here.

    # ------------------------------------------------------------------
    # 3. Title and author (search in uncommented source)
    # ------------------------------------------------------------------
    # Length-preserving so that character offsets in `stripped` are also valid
    # offsets in `source`.
    stripped = '\n'.join(_blank_comment(ln) for ln in lines)
    stripped_lines = [_strip_comment(ln) for ln in lines]

    title_m = re.search(r'\\title\s*(\{)', stripped, re.DOTALL)
    if title_m:
        content, title_end = _extract_braced(stripped, title_m.start(1))
        # Span of the argument itself (inside the braces), in raw-source
        # coordinates.  `stripped` only blanks comments, so offsets match.
        pt.title_span = (title_m.start(1) + 1, title_end - 1)
        pt.title_text_span = _trim_span(stripped, pt.title_span, (r"\\thanks", r"\\footnote"))
        # Remove \thanks{...} for the clean title
        clean = re.sub(r'\\thanks\s*\{[^}]*\}', '', content)
        pt.title_raw = re.sub(r'\s+', ' ', clean).strip()

    author_m = re.search(r'\\author\s*(\{)', stripped, re.DOTALL)
    if author_m:
        content, author_end = _extract_braced(stripped, author_m.start(1))
        pt.author_raw = re.sub(r'\s+', ' ', content).strip()
        pt.author_span = (author_m.start(1) + 1, author_end - 1)
        pt.author_names_span = _author_names_span(stripped, pt.author_span)

    # ------------------------------------------------------------------
    # 4. \cite occurrences — walk all lines tracking line numbers
    # ------------------------------------------------------------------
    # Pattern catches \cite, \cite*, \citep, \citet, etc.
    cite_pat = re.compile(
        r'\\cite[a-z*]*'           # command
        r'(?:\[[^\]]*\])?'         # optional [note]
        r'\s*\{([^}]+)\}',         # {key1,key2,...}
        re.DOTALL,
    )
    for lineno, raw_line in enumerate(lines, start=1):
        clean_line = _strip_comment(raw_line)
        for cm in cite_pat.finditer(clean_line):
            keys_raw = cm.group(1)
            for k in re.split(r'\s*,\s*', keys_raw):
                k = k.strip()
                if k:
                    pt.cite_occurrences.append(
                        CiteOccurrence(key=k, line=lineno, raw=cm.group(0))
                    )

    # ------------------------------------------------------------------
    # 5. Bibliography mode — documentclass biblatex option is authoritative.
    #    Many JACoW templates include a \thebibliography fallback inside
    #    \ifboolexpr{bool{jacowbiblatex}}{\printbibliography}{...\bibitem...}
    #    That fallback must NOT be parsed as the real reference list when
    #    biblatex is active.
    # ------------------------------------------------------------------
    if pt.uses_biblatex:
        pt.bibliography_env = "biblatex"
        pt.has_bibliography_section = True   # \printbibliography is implied

    elif re.search(r'\\bibliography\s*\{', stripped):
        # Classic BibTeX: \bibliographystyle{...} + \bibliography{file}
        pt.bibliography_env = "bibtex"
        pt.has_bibliography_section = True

    elif re.search(r'\\begin\{thebibliography\}', stripped):
        pt.bibliography_env = "thebibliography"
        pt.has_bibliography_section = True
        # Extract from thebibliography environment
        bib_m = re.search(
            r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',
            stripped, re.DOTALL
        )
        if bib_m:
            bib_block = bib_m.group(0)
            # Split on \bibitem{key}
            item_pat = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}')
            positions = [(m.start(), m.end(), m.group(1)) for m in item_pat.finditer(bib_block)]
            for idx, (start, end, key) in enumerate(positions):
                next_start = positions[idx + 1][0] if idx + 1 < len(positions) else len(bib_block)
                raw_text = bib_block[end:next_start].strip()
                pt.bibitems.append((key.strip(), raw_text))

    # ------------------------------------------------------------------
    # 6. Figure / table labels (for Phase-2 checks)
    # ------------------------------------------------------------------
    label_pat = re.compile(r'\\label\s*\{([^}]+)\}')
    for m in label_pat.finditer(stripped):
        lbl = m.group(1).strip()
        if lbl.startswith('fig:') or lbl.startswith('figure:'):
            pt.figure_labels.append(lbl)
        elif lbl.startswith('tab:') or lbl.startswith('table:'):
            pt.table_labels.append(lbl)

    # ------------------------------------------------------------------
    # Build Paper model
    # ------------------------------------------------------------------
    # Build citation_order: keys in order of first appearance
    seen: dict[str, int] = {}     # key → assigned citation number (1-based)
    citation_order: list[str] = []
    for occ in pt.cite_occurrences:
        if occ.key not in seen:
            seen[occ.key] = len(citation_order) + 1
            citation_order.append(occ.key)

    # Build Reference objects from \bibitem (manual bib)
    references: list[Reference] = []
    for n, (key, raw) in enumerate(pt.bibitems, start=1):
        ref_type = _infer_bibitem_type(raw)
        references.append(Reference(
            n=n,
            key=key,
            ref_type=ref_type,
            raw_text=raw,
        ))

    # Parse author list from \author{} block
    authors, pt.affiliations = parse_author_block(pt.author_raw)

    paper = Paper(
        paper_id=pt.paper_id,
        source_path=tex_path,
        title=pt.title_raw,
        authors=authors,
        references=references,
        citation_order=citation_order,
    )
    # Attach parser metadata as extra attributes for use by checks
    paper.__dict__['_pt'] = pt
    return paper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_bibitem_type(raw: str) -> str:
    """Heuristically classify a \\bibitem entry's type from its raw text."""
    lower = raw.lower()
    if re.search(r'presented at|this conference|unpublished', lower):
        return "proceedings_unpublished"
    if re.search(r'in proc\.|proc\.\s+\w', lower):
        return "proceedings"
    if re.search(r'phys\. rev|j\. phys|nucl\. instrum|ieee trans', lower):
        return "journal"
    if re.search(r'ph\.?d\.?\s+thesis|master.s?\s+thesis', lower):
        return "thesis"
    if re.search(r'rep\.|technical report|tech\. rep\.', lower):
        return "report"
    if re.search(r'\\url\{http|https?://', lower):
        return "online"
    if re.search(r'arxiv', lower):
        return "arxiv"
    return "unknown"


def _strip_author_decorations(text: str) -> str:
    r"""Remove affiliation markers and footnotes from an \author{} block.

    Runs **before** any splitting.  This is the fix for the single largest
    source of false positives in the previous version: the block was split on
    commas first, so ``S. Kongtawong\textsuperscript{1,2}`` became the two
    "authors" ``S. Kongtawong\textsuperscript{1`` and ``2}``, and every real
    name that carried a superscript failed the name pattern because
    ``K. Ha\textsuperscript{1}`` flattened to ``K. Ha1``.
    """
    # Superscript affiliation markers, in every spelling JACoW templates use.
    text = re.sub(r"\\textsuperscript\s*\{[^{}]*\}", "", text)
    text = re.sub(r"\\textsuperscript\s*\\?[\w*\u2020\u2021]", "", text)
    text = re.sub(r"\$\s*\^?\s*\{[^{}]*\}\s*\$", "", text)   # $^{1,2}$
    text = re.sub(r"\^\s*\{[^{}]*\}", "", text)               # ^{1,2}
    text = re.sub(r"\^\s*\\?[\w*\u2020\u2021]", "", text)     # ^1  ^\dagger
    # Footnotes / thanks / emails.
    for cmd in ("thanks", "footnote", "footnotemark", "email", "orcid", "altaffilmark"):
        text = re.sub(r"\\" + cmd + r"\s*\{[^{}]*\}", "", text)
        text = re.sub(r"\\" + cmd + r"\b", "", text)
    # Footnote symbols left bare.
    text = re.sub(r"[*\u2020\u2021\u00a7\u00b6#]+", "", text)
    # A LaTeX non-breaking space between initials and surname is correct JACoW
    # style ("E.~Hamwi"), so it must read as a space rather than as markup.
    text = text.replace("~", " ")
    # Residual empty groups and stray markup.
    text = re.sub(r"\{\s*\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+\s*", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


def _split_author_names(text: str) -> list[str]:
    """Split a decorated-and-cleaned author string into individual names."""
    # "A, B and C" / "A, B, and C" / "A and B"
    text = re.sub(r"\s*,?\s+and\s+", ", ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*;\s*", ", ", text)
    parts = [part.strip(" ,;.") for part in text.split(",")]
    return [part for part in parts if part]


def parse_author_block(author_raw: str) -> tuple[list[str], list[str]]:
    r"""Split an ``\author{}`` block into ``(author_names, affiliations)``.

    Everything from the first affiliation cue onwards is treated as
    affiliation text, whether it followed a ``\\`` break or not.  That keeps
    ``Brookhaven National Laboratory``, ``Upton``, ``NY`` and ``USA`` out of the
    author list — 11 of the 38 author findings in the sample corpus were
    address fragments reported as badly formatted names.
    """
    if not author_raw:
        return [], []

    cleaned = _strip_author_decorations(author_raw)
    # A "\\" break separates names from affiliations in the JACoW template;
    # _strip_author_decorations has already collapsed the command, so split on
    # the marker we insert first.
    segments = re.split(r"\\\\", author_raw)
    name_text = _strip_author_decorations(segments[0]) if segments else cleaned
    affiliation_text = " ".join(
        _strip_author_decorations(segment) for segment in segments[1:]
    )

    names: list[str] = []
    affiliations: list[str] = []
    for candidate in _split_author_names(name_text):
        if _AFFILIATION_CUE_RE.search(candidate) or affiliations:
            # Once affiliation text starts, everything after it on the same
            # segment is address, not names.
            affiliations.append(candidate)
            continue
        names.append(candidate)

    if affiliation_text:
        affiliations.extend(_split_author_names(affiliation_text))

    return names, affiliations


def is_jacow_author_name(name: str) -> bool:
    """True when *name* already follows the ``Initials Surname`` convention."""
    cleaned = _strip_author_decorations(name)
    if not cleaned:
        return True  # nothing to judge — do not report
    return bool(_JACOW_NAME_RE.match(cleaned))


def _parse_author_block(author_raw: str) -> list[str]:
    """Backwards-compatible wrapper returning author names only."""
    return parse_author_block(author_raw)[0]
