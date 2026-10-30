"""Checks on the author's PDF (PDF-*), shared by Word and LaTeX submissions.

Every submission arrives with a PDF, whatever it was written in, so these give
Word and LaTeX papers the same baseline screening.  They cover what editors
otherwise check by eye on every paper (Style Guide: General Layout, Fonts,
References, Page Numbers):

- PDF-SIZE-01    page size is the JACoW 595 pt x 792 pt
- PDF-MARGIN-01  text and images stay inside the JACoW margins
- PDF-PAGENUM-01 no page numbers
- PDF-FONT-01    every font is embedded
- PDF-FONT-02    no Type 3 (bitmap) fonts
- PDF-LINK-01    only DOIs are hyperlinked
- PDF-DOI-01     a DOI is split across two lines

A PDF that cannot be read produces one NOT CHECKED finding at INFO severity,
never silence: an unread PDF must not look like a clean one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from src.models import Finding, Severity

MM = 72 / 25.4
JACOW_PAGE = (595.0, 792.0)                      # 20.99 cm x 27.94 cm
JACOW_MARGINS = {"top": 19 * MM, "bottom": 19 * MM, "left": 20 * MM, "right": 20 * MM}
SIZE_TOLERANCE = 3.0       # pt — PDF producers round page sizes differently
MARGIN_TOLERANCE = 2.0     # pt — glyph boxes include a little side bearing

_KNOWN_SIZES = {
    (595.0, 842.0): "A4",
    (612.0, 792.0): "US Letter",
}
_PAGE_NUMBER_RE = re.compile(r"^[\u2013\u2014-]?\s*\d{1,3}\s*[\u2013\u2014-]?$")


def find_author_pdf(folder: Path) -> Path | None:
    """The PDF the author submitted (``PDF/`` in an Indico submission folder)."""
    for directory in (folder / "PDF", folder):
        if directory.is_dir():
            pdfs = sorted(p for p in directory.glob("*.pdf")
                          if p.is_file() and "_edited" not in p.stem
                          and "_final" not in p.stem)
            if pdfs:
                return pdfs[0]
    return None


def run_pdf_checks(pdf_path: Path) -> list[Finding]:
    """Run every PDF check on *pdf_path* and return the findings."""
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        return [_not_checked("the PDF library (pdfplumber) is not installed")]

    findings: list[Finding] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            _check_page_size(pdf.pages, findings)
            _check_margins_and_page_numbers(pdf.pages, findings)
            _check_fonts(pdf.pages, findings)
            _check_links(pdf.pages, findings)
            _check_split_dois(pdf.pages, findings)
    except Exception as exc:  # noqa: BLE001 — a damaged PDF is a finding, not a crash
        return [_not_checked(f"the PDF could not be read ({type(exc).__name__})")]
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _not_checked(why: str) -> Finding:
    return Finding(
        check_id="PDF-00", severity=Severity.INFO,
        message=f"NOT CHECKED — page size, margins, fonts and links were not checked: {why}.",
    )


def _pages_text(numbers: Iterable[int]) -> str:
    numbers = sorted(set(numbers))
    shown = ", ".join(str(n) for n in numbers[:8])
    return ("page " if len(numbers) == 1 else "pages ") + shown + (" …" if len(numbers) > 8 else "")


# ---------------------------------------------------------------------------
# PDF-SIZE-01
# ---------------------------------------------------------------------------

def _check_page_size(pages, findings: list[Finding]) -> None:
    wrong: dict[tuple[float, float], list[int]] = {}
    for number, page in enumerate(pages, start=1):
        size = (round(float(page.width), 1), round(float(page.height), 1))
        if (abs(size[0] - JACOW_PAGE[0]) > SIZE_TOLERANCE
                or abs(size[1] - JACOW_PAGE[1]) > SIZE_TOLERANCE):
            wrong.setdefault(size, []).append(number)
    for size, numbers in wrong.items():
        name = next((label for known, label in _KNOWN_SIZES.items()
                     if abs(known[0] - size[0]) <= SIZE_TOLERANCE
                     and abs(known[1] - size[1]) <= SIZE_TOLERANCE), None)
        described = f"{size[0]:g} × {size[1]:g} pt" + (f" ({name})" if name else "")
        findings.append(Finding(
            check_id="PDF-SIZE-01", severity=Severity.WARNING,
            message=(f"{_pages_text(numbers).capitalize()}: page size is {described}; "
                     "JACoW papers are 595 × 792 pt (20.99 × 27.94 cm)."),
            original=described, suggested="595 × 792 pt",
        ))


# ---------------------------------------------------------------------------
# PDF-MARGIN-01 and PDF-PAGENUM-01
# ---------------------------------------------------------------------------

def _check_margins_and_page_numbers(pages, findings: list[Finding]) -> None:
    margin_pages: dict[str, list[int]] = {}
    number_pages: list[int] = []
    for number, page in enumerate(pages, start=1):
        width, height = float(page.width), float(page.height)
        left = JACOW_MARGINS["left"] - MARGIN_TOLERANCE
        right = width - JACOW_MARGINS["right"] + MARGIN_TOLERANCE
        top = JACOW_MARGINS["top"] - MARGIN_TOLERANCE
        bottom = height - JACOW_MARGINS["bottom"] + MARGIN_TOLERANCE

        outside: list[tuple[str, str]] = []           # (side, text)
        for word in page.extract_words(keep_blank_chars=False) or []:
            sides = _sides_outside(word, left, right, top, bottom)
            if sides:
                outside.append((sides[0], word["text"]))
        for image in page.images or []:
            sides = _sides_outside(image, left, right, top, bottom)
            if sides:
                outside.append((sides[0], "[image]"))

        if not outside:
            continue
        in_head_or_foot = [text for side, text in outside if side in ("top", "bottom")]
        if (in_head_or_foot and len(in_head_or_foot) == len(outside)
                and all(_PAGE_NUMBER_RE.match(text) for text in in_head_or_foot)):
            number_pages.append(number)
            continue
        for side, _ in outside:
            margin_pages.setdefault(side, []).append(number)

    if number_pages:
        findings.append(Finding(
            check_id="PDF-PAGENUM-01", severity=Severity.WARNING,
            message=(f"{_pages_text(number_pages).capitalize()} "
                     f"{'carries' if len(set(number_pages)) == 1 else 'carry'} a page number. "
                     "JACoW papers have no page numbers; they are added when the "
                     "proceedings are produced."),
        ))
    for side, numbers in sorted(margin_pages.items()):
        findings.append(Finding(
            check_id="PDF-MARGIN-01", severity=Severity.WARNING,
            message=(f"{_pages_text(numbers).capitalize()}: text or images extend into "
                     f"the {side} margin. JACoW margins are 19 mm top and bottom and "
                     "20 mm left and right."),
        ))


def _sides_outside(box: dict, left: float, right: float, top: float, bottom: float) -> list[str]:
    sides = []
    if float(box["x0"]) < left:
        sides.append("left")
    if float(box["x1"]) > right:
        sides.append("right")
    if float(box["top"]) < top:
        sides.append("top")
    if float(box["bottom"]) > bottom:
        sides.append("bottom")
    return sides


# ---------------------------------------------------------------------------
# PDF-FONT-01 and PDF-FONT-02
# ---------------------------------------------------------------------------

def _check_fonts(pages, findings: list[Finding]) -> None:
    from pdfminer.pdftypes import resolve1  # pdfplumber depends on pdfminer.six

    not_embedded: dict[str, set[int]] = {}
    type3: dict[str, set[int]] = {}
    for number, page in enumerate(pages, start=1):
        resources = resolve1(page.page_obj.resources) or {}
        # Only fonts that draw glyphs matter: producers often list a default
        # font in the resources that the page never uses.
        used = {str(ch.get("fontname", "")).split("+", 1)[-1] for ch in page.chars}
        for name, font in _fonts(resources, resolve1, seen=set()):
            subtype = _name(font.get("Subtype"))
            if subtype == "Type3":
                type3.setdefault(name, set()).add(number)
                continue
            if name in used and not _is_embedded(font, resolve1):
                not_embedded.setdefault(name, set()).add(number)

    for name, numbers in sorted(not_embedded.items()):
        findings.append(Finding(
            check_id="PDF-FONT-01", severity=Severity.ERROR,
            message=(f"The font {name} is not embedded ({_pages_text(numbers)}). Every font "
                     "must be embedded, including those inside figures."),
            original=name,
        ))
    for name, numbers in sorted(type3.items()):
        findings.append(Finding(
            check_id="PDF-FONT-02", severity=Severity.WARNING,
            message=(f"The font {name} is a Type 3 (bitmap) font ({_pages_text(numbers)}). "
                     "These print and display poorly; regenerate the figure or PDF with "
                     "Type 1 or TrueType fonts."),
            original=name,
        ))


def _fonts(resources, resolve1, *, seen: set[int]):
    """Yield (name, font dict) for a resource dictionary and its Form XObjects.

    Figures embedded as Form XObjects carry their own fonts, and they are the
    commonest source of an unembedded font in an otherwise clean PDF.
    """
    for font in (resolve1(resources.get("Font")) or {}).values():
        font = resolve1(font) or {}
        name = _name(font.get("BaseFont")) or "(unnamed font)"
        name = name.split("+", 1)[-1]                     # drop the subset tag
        yield name, font
    for xobject in (resolve1(resources.get("XObject")) or {}).values():
        stream = resolve1(xobject)
        attrs = getattr(stream, "attrs", None) or {}
        if _name(attrs.get("Subtype")) != "Form" or id(stream) in seen:
            continue
        seen.add(id(stream))
        yield from _fonts(resolve1(attrs.get("Resources")) or {}, resolve1, seen=seen)


def _is_embedded(font: dict, resolve1) -> bool:
    if _name(font.get("Subtype")) == "Type0":
        descendants = resolve1(font.get("DescendantFonts")) or []
        return bool(descendants) and all(
            _is_embedded(resolve1(d) or {}, resolve1) for d in descendants
        )
    descriptor = resolve1(font.get("FontDescriptor")) or {}
    return any(key in descriptor for key in ("FontFile", "FontFile2", "FontFile3"))


def _name(value) -> str:
    if value is None:
        return ""
    text = getattr(value, "name", value)
    if isinstance(text, bytes):
        text = text.decode("latin-1", "replace")
    return str(text).lstrip("/")


# ---------------------------------------------------------------------------
# PDF-LINK-01
# ---------------------------------------------------------------------------

def _check_links(pages, findings: list[Finding]) -> None:
    offending: dict[str, set[int]] = {}
    for number, page in enumerate(pages, start=1):
        for link in page.hyperlinks or []:
            uri = (link.get("uri") or "").strip()
            if not re.match(r"https?://", uri, re.IGNORECASE):
                continue                                  # mailto:, internal links
            if re.match(r"https?://(dx\.)?doi\.org/", uri, re.IGNORECASE):
                continue
            offending.setdefault(uri, set()).add(number)
    for uri, numbers in sorted(offending.items()):
        findings.append(Finding(
            check_id="PDF-LINK-01", severity=Severity.WARNING,
            message=(f"{uri} is hyperlinked ({_pages_text(numbers)}). Only DOIs may carry "
                     "hyperlinks; a URL may be shown as plain text but must not be linked."),
            original=uri,
        ))


# ---------------------------------------------------------------------------
# PDF-DOI-01
# ---------------------------------------------------------------------------

_DOI_AT_LINE_END_RE = re.compile(r"doi:\s*(?P<doi>10\.\S*)?$", re.IGNORECASE)


def _check_split_dois(pages, findings: list[Finding]) -> None:
    """A DOI must stay on one line (Style Guide: References; Annex B).

    Two independent signals, either of which is enough:

    * the same doi.org hyperlink has boxes on two different lines — Word and
      hyperref both emit one link box per line when a link wraps;
    * a line ends in "doi:" alone, or in a DOI with no suffix after the
      slash, or one that ends in a hyphen, full stop or slash.
    """
    split: dict[str, set[int]] = {}
    for number, page in enumerate(pages, start=1):
        tops: dict[str, set[int]] = {}
        for link in page.hyperlinks or []:
            uri = (link.get("uri") or "").strip()
            match = re.match(r"https?://(?:dx\.)?doi\.org/(.+)", uri, re.IGNORECASE)
            if match:
                tops.setdefault(match.group(1), set()).add(round(float(link["top"])))
        for doi, line_tops in tops.items():
            if len(line_tops) > 1:
                split.setdefault(doi, set()).add(number)

        for line in (page.extract_text() or "").splitlines():
            match = _DOI_AT_LINE_END_RE.search(line.rstrip())
            if not match:
                continue
            doi = match.group("doi") or ""
            prefix, _, suffix = doi.partition("/")
            if not doi or not suffix or doi.endswith(("-", ".", "/", "_")):
                split.setdefault(doi or "doi:", set()).add(number)

    for doi, numbers in sorted(split.items()):
        shown = doi if doi != "doi:" else "a DOI"
        findings.append(Finding(
            check_id="PDF-DOI-01", severity=Severity.WARNING, original=doi,
            message=(f"{shown} is split across two lines ({_pages_text(numbers)}). A DOI "
                     "must stay on one line; start it on a new line if necessary."),
        ))
