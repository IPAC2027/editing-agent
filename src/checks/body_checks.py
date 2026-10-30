"""Body-text and reference-form checks shared by Word and LaTeX (TXT-*, REF-FORM-*).

Rules from the Style Guide (Figures, Tables, and Equations; Abstract) and
Annex B that neither path checked before:

- TXT-ABS-01     the abstract contains a citation
- TXT-CITE-01    "[1], [2]" — several citations go in one bracket, "[1, 2]"
- TXT-TAB-01     "Tab. 1" — a table reference is never abbreviated
- TXT-FIG-01     "Fig. 1" at the start of a sentence — write "Figure 1"
- TXT-EQ-01      "Eq. 1" / "equation 1" mid-sentence — write "Eq. (1)"
- REF-FORM-01    an unpublished paper cited as "in Proc. …"
- REF-FORM-02    a submitted paper that names the journal

All are findings with a suggestion, never automatic edits: the matches are
textual, and a human should see each one in context.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from src.models import Finding, Severity

# ---------------------------------------------------------------------------
# Normalising LaTeX so one set of patterns serves both sources
# ---------------------------------------------------------------------------

_LATEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_EQREF_RE = re.compile(r"\\eqref\{[^}]*\}")
_REF_RE = re.compile(r"\\(?:ref|cref|autoref)\{[^}]*\}")


def latex_to_text(source: str) -> str:
    """Just enough LaTeX flattening for the callout patterns below."""
    text = _LATEX_COMMENT_RE.sub("", source)
    text = _EQREF_RE.sub("(0)", text)
    text = _REF_RE.sub("0", text)
    return text.replace("~", " ")


def latex_abstract(source: str) -> str | None:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", source, re.DOTALL)
    return match.group(1) if match else None


def latex_body(source: str) -> str:
    """Text between \\begin{document} and the bibliography."""
    start = source.find("\\begin{document}")
    body = source[start:] if start >= 0 else source
    for marker in ("\\begin{thebibliography}", "\\printbibliography", "\\bibliography{"):
        cut = body.find(marker)
        if cut >= 0:
            body = body[:cut]
    return body


# ---------------------------------------------------------------------------
# Word paragraphs
# ---------------------------------------------------------------------------

def word_paragraphs(doc_path: Path) -> tuple[list[str], str | None]:
    """Body paragraphs before REFERENCES, and the abstract if one is labelled."""
    import docx  # python-docx

    texts = [p.text.strip() for p in docx.Document(str(doc_path)).paragraphs]
    body: list[str] = []
    for text in texts:
        if re.fullmatch(r"REFERENCES?", text.strip(), re.IGNORECASE):
            break
        body.append(text)

    abstract_parts: list[str] = []
    in_abstract = False
    for text in body:
        if re.fullmatch(r"abstract", text, re.IGNORECASE):
            in_abstract = True
            continue
        if in_abstract:
            if not text:
                continue
            if _looks_like_heading(text):
                break
            abstract_parts.append(text)
    return body, (" ".join(abstract_parts) if abstract_parts else None)


def _looks_like_heading(text: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", text)
    return bool(letters) and len(text) < 80 and letters.isupper()


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,\u2013-]\s*\d+)*\s*\]|\\cite[a-z]*\{")
_TAB_RE = re.compile(r"\bTab\.\s*(\d+)")
_ADJACENT_CITES_RE = re.compile(r"\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\](?:\s*,?\s*\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\])+")
_FIG_START_RE = re.compile(r"(?:^|[.!?]\s+)(Figs?\.\s*\d+)")
_EQ_NO_PARENS_RE = re.compile(r"\b(Eqs?\.|eqs?\.)\s*(\d+)\b(?!\s*\))")
_EQUATION_MID_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b([Ee]quation)\s*\(?(\d+)\)?")


def check_body_text(paragraphs: Iterable[str], abstract: str | None) -> list[Finding]:
    findings: list[Finding] = []

    if abstract and _CITATION_RE.search(abstract):
        findings.append(Finding(
            check_id="TXT-ABS-01", severity=Severity.WARNING,
            message=("The abstract contains a citation. The abstract stands alone and "
                     "must not cite references."),
            original=_CITATION_RE.search(abstract).group(0),
        ))

    seen: set[tuple[str, str]] = set()

    def add(check_id: str, original: str, suggested: str, message: str) -> None:
        if (check_id, original) in seen:
            return
        seen.add((check_id, original))
        findings.append(Finding(check_id=check_id, severity=Severity.WARNING,
                                original=original, suggested=suggested, message=message))

    for paragraph in paragraphs:
        for match in _ADJACENT_CITES_RE.finditer(paragraph):
            numbers = re.findall(r"\[([^\]]+)\]", match.group(0))
            merged = "[" + ", ".join(n.strip() for n in numbers) + "]"
            add("TXT-CITE-01", match.group(0), merged,
                f"'{match.group(0)}': several citations go in one bracket, e.g. {merged}.")
        for match in _TAB_RE.finditer(paragraph):
            add("TXT-TAB-01", match.group(0), f"Table {match.group(1)}",
                f"'{match.group(0)}': a table reference is never abbreviated.")
        for match in _FIG_START_RE.finditer(paragraph):
            callout = match.group(1)
            full = re.sub(r"^Figs?\.", lambda m: "Figures" if m.group(0) == "Figs." else "Figure",
                          callout)
            add("TXT-FIG-01", callout, full,
                f"'{callout}' starts a sentence; write 'Figure' in full there.")
        for match in _EQ_NO_PARENS_RE.finditer(paragraph):
            add("TXT-EQ-01", match.group(0), f"{match.group(1)} ({match.group(2)})",
                f"'{match.group(0)}': equation numbers are cited in parentheses, e.g. Eq. (1).")
        for match in _EQUATION_MID_RE.finditer(paragraph):
            start = match.start()
            if start == 0 or re.search(r"[.!?]\s*$", paragraph[:start]):
                continue
            add("TXT-EQ-01", match.group(0), f"Eq. ({match.group(2)})",
                f"'{match.group(0)}' is mid-sentence; write 'Eq. ({match.group(2)})'.")
    return findings


_UNPUBLISHED_PROC_RE = re.compile(r"\bin\s+(?:\\emph\{|\\textit\{)?Proc\.", re.IGNORECASE)
_SUBMITTED_TO_RE = re.compile(r"submitted\s+to\s+(?!publication)(\S.*?)(?:[.,]\s*$|$)",
                              re.IGNORECASE)


def check_reference_forms(references: Iterable[tuple[int, str]], *,
                          attach_to_reference: bool = True) -> list[Finding]:
    """Annex B forms for unpublished and submitted papers.

    *references* is ``(number, raw text)`` pairs from either source.  The Word
    path files findings by reference number in ``Finding.line``; the LaTeX
    path uses that field for source lines, so it passes
    ``attach_to_reference=False``.
    """
    findings: list[Finding] = []
    for number, raw in references:
        if re.search(r"\bunpublished\b", raw, re.IGNORECASE) and _UNPUBLISHED_PROC_RE.search(raw):
            findings.append(Finding(
                check_id="REF-FORM-01", severity=Severity.WARNING,
                line=number if attach_to_reference else None,
                original=raw[:160],
                message=(f"Reference [{number}] is marked unpublished but cited 'in Proc.'. "
                         "An unpublished paper has no proceedings: write 'presented at "
                         "IPAC'14, Dresden, Germany, Jun. 2014, paper MOP057, unpublished.'"),
            ))
        match = _SUBMITTED_TO_RE.search(raw)
        if match:
            findings.append(Finding(
                check_id="REF-FORM-02", severity=Severity.WARNING,
                line=number if attach_to_reference else None,
                original=match.group(0).strip(), suggested="submitted for publication.",
                message=(f"Reference [{number}] names the journal a paper was submitted to. "
                         "For a submitted (not yet accepted) paper the journal is not named: "
                         "'submitted for publication.'"),
            ))
    return findings
