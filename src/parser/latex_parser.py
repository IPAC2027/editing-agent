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


def _strip_comment(line: str) -> str:
    """Remove trailing LaTeX comment from a single line (respects \\%)."""
    result = re.sub(r'(?<!\\)%.*', '', line)
    return result


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
    stripped_lines = [_strip_comment(ln) for ln in lines]
    stripped = '\n'.join(stripped_lines)

    title_m = re.search(r'\\title\s*(\{)', stripped, re.DOTALL)
    if title_m:
        content, _ = _extract_braced(stripped, title_m.start(1))
        # Remove \thanks{...} for the clean title
        clean = re.sub(r'\\thanks\s*\{[^}]*\}', '', content)
        pt.title_raw = re.sub(r'\s+', ' ', clean).strip()

    author_m = re.search(r'\\author\s*(\{)', stripped, re.DOTALL)
    if author_m:
        content, _ = _extract_braced(stripped, author_m.start(1))
        pt.author_raw = re.sub(r'\s+', ' ', content).strip()

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
    authors = _parse_author_block(pt.author_raw)

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


def _parse_author_block(author_raw: str) -> list[str]:
    """Extract a flat list of author name strings from the \\author{} content."""
    if not author_raw:
        return []
    # Remove \thanks{...}, affiliation lines separated by \\
    text = re.sub(r'\\thanks\s*\{[^}]*\}', '', author_raw)
    # Split on \\ (line break) — second part is usually affiliations
    parts = re.split(r'\\\\', text)
    if not parts:
        return []
    name_part = parts[0].strip()
    # Names separated by commas; last may have affiliation appended after the list
    names = [n.strip() for n in re.split(r',', name_part) if n.strip()]
    return names
