"""Deterministic LaTeX formatting checks for JACoW submissions."""

from __future__ import annotations

import re

from src.models import Finding, Paper, Severity


_CANONICAL_UNITS = {
    "eV", "keV", "MeV", "GeV", "TeV", "Hz", "kHz", "MHz", "GHz", "THz",
    "m", "cm", "mm", "um", "nm", "s", "ms", "us", "ns", "ps", "A", "mA",
    "uA", "V", "mV", "kV", "MV", "GV", "W", "mW", "kW", "MW", "T", "mT",
    "K", "Pa", "kPa", "MPa", "bar", "rad", "mrad", "sr", "Gy", "Bq", "C",
    "kg", "g", "mg", "mol", "cd", "lm", "lx", "ohm", "Ω", "%",
}
_UNIT_BY_LOWER = {unit.lower(): unit for unit in _CANONICAL_UNITS}
_NUMBER_UNIT_RE = re.compile(
    r"(?<![\\\w])"
    r"(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?P<separator>~|\\,|[ \t]+)"
    r"(?P<unit>[A-Za-zµΩ%]+)(?![A-Za-z])"
)
_AUTHOR_RE = re.compile(
    r"^(?:[A-Z]\.\s*)+"
    r"(?:(?:de|del|den|der|di|du|la|le|van|von)\s+)?"
    r"[A-Z][A-Za-z'’\-]*(?:[ \-][A-Z][A-Za-z'’\-]*)*$"
)


def _source_text(paper: Paper) -> str:
    try:
        return paper.source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        parsed = paper.__dict__.get("_pt")
        return "\n".join(parsed.source_lines) if parsed else ""


def _line_for(source: str, needle: str) -> int | None:
    offset = source.find(needle)
    return source.count("\n", 0, offset) + 1 if offset >= 0 else None


def _plain_tex(text: str) -> str:
    text = re.sub(r"\$[^$]*\$", "", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^]]*\])?", "", text)
    return re.sub(r"[{}]", "", text).strip()


def _add(
    paper: Paper,
    check_id: str,
    severity: Severity,
    message: str,
    *,
    line: int | None = None,
    original: str | None = None,
    suggested: str | None = None,
) -> None:
    paper.findings.append(Finding(
        check_id=check_id,
        severity=severity,
        line=line,
        original=original,
        suggested=suggested,
        message=message,
    ))


def check_title_format(paper: Paper) -> None:
    """FMT-TITLE-02: title must not end with punctuation.

    ``jacow.cls`` uppercases title text at rendering time. Intentional lowercase
    tokens are handled by ``\\NoCaseChange{...}``, so source-case alone is not a
    deterministic error.
    """
    title = paper.title.strip()
    if not title:
        return

    source = _source_text(paper)
    line = _line_for(source, r"\title")
    visible_title = _plain_tex(title)
    if visible_title.rstrip().endswith((".", ",", ";", ":", "!", "?")):
        _add(
            paper,
            "FMT-TITLE-02",
            Severity.WARNING,
            r"The text in \title{} must not end with punctuation.",
            line=line,
            original=title,
            suggested=title.rstrip(".,;:!?"),
        )


def check_author_format(paper: Paper) -> None:
    """FMT-AUTH-01: author names must use the ``Initials Surname`` convention."""
    if not paper.authors:
        return

    source = _source_text(paper)
    line = _line_for(source, r"\author")
    for author in paper.authors:
        visible_author = _plain_tex(author)
        if not visible_author or _AUTHOR_RE.fullmatch(visible_author):
            continue
        _add(
            paper,
            "FMT-AUTH-01",
            Severity.WARNING,
            "Author names should use initials followed by surname, for example 'A. B. Surname'.",
            line=line,
            original=author,
        )


def check_number_unit_format(paper: Paper) -> None:
    """FMT-UNIT-01/02: enforce non-breaking spacing and recognised SI-unit case."""
    source = _source_text(paper)
    for lineno, source_line in enumerate(source.splitlines(), start=1):
        line = re.sub(r"(?<!\\)%.*", "", source_line)
        for match in _NUMBER_UNIT_RE.finditer(line):
            unit = match.group("unit")
            canonical_unit = _UNIT_BY_LOWER.get(unit.lower())
            if not canonical_unit:
                continue

            number = match.group("number")
            separator = match.group("separator")
            replacement = f"{number}~{canonical_unit}"
            if separator not in {"~", r"\,"}:
                _add(
                    paper,
                    "FMT-UNIT-01",
                    Severity.WARNING,
                    "Use a non-breaking space between a number and its unit.",
                    line=lineno,
                    original=match.group(0),
                    suggested=replacement,
                )
            if unit != canonical_unit:
                _add(
                    paper,
                    "FMT-UNIT-02",
                    Severity.WARNING,
                    "Use the standard case for the SI unit abbreviation.",
                    line=lineno,
                    original=match.group(0),
                    suggested=replacement,
                )


def run_all(paper: Paper) -> None:
    """Run deterministic title, author, and number-unit checks in-place."""
    check_title_format(paper)
    check_author_format(paper)
    check_number_unit_format(paper)
