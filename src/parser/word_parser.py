"""Word (.docx) document parser — extract references and citation context.

Uses python-docx to read paragraphs from the document, locate the REFERENCES
section, and extract numbered reference entries.  In-text citation numbers are
also harvested from body paragraphs so ordering checks can be applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import docx  # python-docx
    from docx.oxml.ns import qn
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "python-docx is required for Word parsing. "
        "Install with: uv add python-docx"
    ) from exc


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WordReference:
    """One numbered reference entry extracted from a Word document."""
    n: int                          # reference number [n]
    raw_text: str                   # full raw text of the entry (tab/newline cleaned)
    # Parsed fields (best-effort)
    authors: list[str] = field(default_factory=list)
    title: str = ""
    doi: str = ""
    url: str = ""
    ref_type: str = "unknown"       # proceedings|journal|arxiv|book|misc|...
    # Where this entry lives in the document.  Needed to write Word tracked
    # changes, which are expressed against paragraph content: an entry that
    # spills over more than one paragraph cannot be revised as a single
    # paragraph rewrite, and is reported instead of guessed at.
    paragraph_index: int = -1
    paragraph_count: int = 1
    # The paragraph's text exactly as python-docx reports it, tabs and all.
    # ``raw_text`` is cleaned (tabs collapsed, non-breaking spaces normalised),
    # which is right for parsing and wrong for writing revisions: a tracked
    # change must be expressed against the document's real characters.
    paragraph_text: str = ""


@dataclass
class InTextCitation:
    """One in-text citation occurrence from a body paragraph."""
    number: int
    paragraph_index: int            # 0-based paragraph index in the document


@dataclass
class ParsedWord:
    """Result of parsing a Word submission."""
    paper_id: str
    doc_path: Path
    title: str = ""
    has_references_section: bool = False
    references: list[WordReference] = field(default_factory=list)
    citations: list[InTextCitation] = field(default_factory=list)
    # Raw paragraph texts for the reference section (before parsing)
    ref_paragraphs: list[tuple[int, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches the opening bracket-number of a reference: [1], [12], etc.
_REF_NUM_RE = re.compile(r'^\[(\d+)\][\t\s]*(.*)$', re.DOTALL)

# Matches in-text citations like [1], [1,2], [1-3], [1, 2, 3]
_CITE_RE = re.compile(r'\[(\d[\d,;\s\-–]+)\]')

# DOI patterns in raw text
_DOI_RE = re.compile(r'doi\s*:?\s*(10\.\S+)', re.IGNORECASE)
_DOI_ORG_RE = re.compile(r'https?://(?:dx\.)?doi\.org/(10\.\S+)', re.IGNORECASE)

# URL pattern (rough)
_URL_RE = re.compile(r'https?://\S+', re.IGNORECASE)

# Author list ends before the first quote/comma-space-quote that introduces title
_TITLE_RE = re.compile(r'["\u201c](.*?)["\u201d,]')

# JACoW reference paragraph styles (various naming conventions in templates)
_REF_STYLES = {
    "jacow_reference when <= 9 refs",
    "jacow_reference #1-9 when >= 10 refs",
    "jacow_reference #10 onwards",
    "jacow_reference when < 10 refs",
    "jacow_reference",
    "reference",
}


def _is_ref_style(style_name: str) -> bool:
    return style_name.lower() in _REF_STYLES


def _is_ref_paragraph(style_name: str, text: str) -> bool:
    """Return True if this paragraph looks like a reference entry."""
    if _is_ref_style(style_name):
        return True
    # Fallback: text starts with [n] pattern even if style is wrong
    return bool(_REF_NUM_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_word(doc_path: Path) -> ParsedWord:
    """Parse *doc_path* (a .docx file) and return a :class:`ParsedWord`."""
    paper_id = doc_path.stem.split(".")[0].upper()
    result = ParsedWord(paper_id=paper_id, doc_path=doc_path)

    doc = docx.Document(str(doc_path))
    paragraphs = doc.paragraphs

    # --- Pass 1: locate REFERENCES section and extract title ---
    ref_section_idx: int | None = None
    for i, para in enumerate(paragraphs):
        style = para.style.name if para.style else ""
        txt = para.text.strip()

        # Capture paper title (first non-empty paragraph that is the title style)
        if not result.title and style.lower() in {
            "jacow_paper title", "title", "jacow_title"
        } and txt:
            result.title = txt

        # Detect REFERENCES heading
        if txt.upper() == "REFERENCES" or (
            "section" in style.lower() and txt.upper() == "REFERENCES"
        ):
            result.has_references_section = True
            ref_section_idx = i

    # --- Pass 2: extract in-text citations from body paragraphs ---
    body_end = ref_section_idx if ref_section_idx is not None else len(paragraphs)
    for i in range(body_end):
        para = paragraphs[i]
        style = para.style.name if para.style else ""
        txt = para.text
        # Skip headings, titles, captions
        style_l = style.lower()
        if any(k in style_l for k in ("heading", "title", "caption", "abstract")):
            continue
        for m in _CITE_RE.finditer(txt):
            # expand comma/range notation
            for num in _expand_citation_range(m.group(1)):
                result.citations.append(InTextCitation(number=num, paragraph_index=i))

    # --- Pass 3: extract reference entries ---
    if ref_section_idx is None:
        return result  # no references section found

    raw_ref_lines: list[tuple[int, str]] = []  # (para_idx, text)
    para_counts: list[int] = []                # paragraphs merged into each entry
    for i in range(ref_section_idx + 1, len(paragraphs)):
        para = paragraphs[i]
        txt = para.text.strip()
        if not txt:
            continue
        style = para.style.name if para.style else ""

        # A new section heading after REFERENCES means we've left the section
        style_l = style.lower()
        if "section heading" in style_l or "heading" in style_l:
            break

        if _is_ref_paragraph(style, txt):
            raw_ref_lines.append((i, txt))
            para_counts.append(1)
            result.ref_paragraphs.append((i, txt))
        elif raw_ref_lines:
            # Continuation of previous reference (no [n] prefix, same section)
            # Only if the last item doesn't end with period or we're still in refs
            prev_idx, prev_txt = raw_ref_lines[-1]
            raw_ref_lines[-1] = (prev_idx, prev_txt + " " + txt)
            para_counts[-1] += 1
            result.ref_paragraphs[-1] = (prev_idx, prev_txt + " " + txt)

    # --- Pass 4: parse each reference entry ---
    for (para_idx, raw), count in zip(raw_ref_lines, para_counts):
        ref = _parse_reference_entry(raw)
        if ref is not None:
            ref.paragraph_index = para_idx
            ref.paragraph_count = count
            ref.paragraph_text = paragraphs[para_idx].text
            result.references.append(ref)

    return result


# ---------------------------------------------------------------------------
# Reference entry parser
# ---------------------------------------------------------------------------

def _parse_reference_entry(raw: str) -> WordReference | None:
    """Parse a single raw reference string into a :class:`WordReference`."""
    raw = raw.replace("\t", " ").replace("\xa0", " ")
    # Normalise non-breaking spaces and zero-width chars
    raw = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', raw)

    m = _REF_NUM_RE.match(raw.strip())
    if not m:
        return None

    n = int(m.group(1))
    body = m.group(2).strip()

    ref = WordReference(n=n, raw_text=body)

    # Extract DOI
    doi_m = _DOI_RE.search(body)
    if doi_m:
        ref.doi = doi_m.group(1).rstrip('.,)')
    else:
        doi_org_m = _DOI_ORG_RE.search(body)
        if doi_org_m:
            ref.doi = doi_org_m.group(1).rstrip('.,)')

    # Extract URL (if no DOI URL)
    url_m = _URL_RE.search(body)
    if url_m and "doi.org" not in url_m.group(0).lower():
        ref.url = url_m.group(0).rstrip('.,)')

    # Extract title (text inside first set of double-quotes)
    title_m = _TITLE_RE.search(body)
    if title_m:
        ref.title = title_m.group(1).strip()

    # Extract authors (text before the first quoted title or before first comma+space)
    if title_m:
        author_part = body[: title_m.start()].strip().rstrip(",").strip()
    else:
        # No quoted title — everything before first period-terminated segment
        author_part = body.split(".")[0] if "." in body else ""

    if author_part:
        ref.authors = _parse_author_list(author_part)

    # Classify reference type
    ref.ref_type = _classify_ref_type(body)

    return ref


def _parse_author_list(author_str: str) -> list[str]:
    """Split an author string into individual authors."""
    # Normalise 'et al' variants
    author_str = re.sub(r'\bet\s+al\.?', 'et al.', author_str, flags=re.IGNORECASE)
    # Split on 'and' and commas, but be careful with initials (A. B. Smith)
    # Strategy: split on ' and ' first, then split on ', '
    parts: list[str] = []
    for segment in re.split(r'\s+and\s+', author_str, flags=re.IGNORECASE):
        for sub in re.split(r',\s*(?=[A-Z])', segment):
            sub = sub.strip().rstrip(",").strip()
            if sub:
                parts.append(sub)
    return parts


def _classify_ref_type(body: str) -> str:
    """Heuristic reference type classification."""
    body_l = body.lower()
    if re.search(r'\bproc\b|\bin proc\b|proceedings', body_l):
        return "proceedings"
    if re.search(r'\barxiv\b', body_l):
        return "arxiv"
    if re.search(r'\bph\.?d\.?\s+thesis\b|\bthesis\b|\bdissertation\b', body_l):
        return "thesis"
    if re.search(r'\brep\.\s*\d|\btechnical report\b|\btech\.?\s*rep\b', body_l):
        return "report"
    if re.search(r'\bvol\.\s*\d|\bno\.\s*\d|\bpp\.\s*\d|\bjournal\b', body_l):
        return "journal"
    if re.search(r'\bunpublished\b', body_l):
        return "unpublished"
    if re.search(r'\bprivate communication\b', body_l):
        return "private_comm"
    if re.search(r'\bpatent\b', body_l):
        return "patent"
    if re.search(r'https?://', body_l):
        return "online"
    return "misc"


def _expand_citation_range(raw: str) -> list[int]:
    """Expand a citation range string like '1, 3-5' into [1, 3, 4, 5]."""
    nums: list[int] = []
    for part in re.split(r'[,;]', raw):
        part = part.strip()
        range_m = re.match(r'^(\d+)\s*[-–]\s*(\d+)$', part)
        if range_m:
            a, b = int(range_m.group(1)), int(range_m.group(2))
            nums.extend(range(a, b + 1))
        elif re.match(r'^\d+$', part):
            nums.append(int(part))
    return nums
