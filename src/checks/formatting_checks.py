"""Deterministic LaTeX formatting checks for JACoW submissions."""

from __future__ import annotations

import re

from src.models import Finding, Paper, Severity
from src.parser.latex_parser import is_jacow_author_name


# Unit tables moved to src.autofix.latex_edits, where the ambiguity handling
# lives.  Re-exported here for backwards compatibility only.
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
    r"""FMT-TITLE-02: the title must not end with punctuation.

    ``jacow.cls`` uppercases title text at rendering time, so intentional
    lowercase is expressed with ``\NoCaseChange{...}`` and source case alone is
    not a deterministic error.
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
    """FMT-AUTH-01: author names must use the ``Initials Surname`` convention.

    Reported as **one finding for the paper**, listing every name that needs
    changing, rather than one finding per name.  The previous version emitted
    one warning per author with the same message and the same line number: on
    the sample corpus that was 38 warnings, of which 32 were affiliation
    fragments or parser debris and the remaining 6 said the same thing seven
    times over.

    Affiliation text is no longer part of ``paper.authors`` at all — see
    :func:`src.parser.latex_parser.parse_author_block` — so this check now sees
    names only.
    """
    if not paper.authors:
        return

    source = _source_text(paper)
    line = _line_for(source, r"\author")

    offenders = [
        author for author in paper.authors
        if not is_jacow_author_name(author)
    ]
    if not offenders:
        return

    listed = ", ".join(f"'{name}'" for name in offenders[:8])
    if len(offenders) > 8:
        listed += f", and {len(offenders) - 8} more"
    _add(
        paper,
        "FMT-AUTH-01",
        Severity.WARNING,
        f"{len(offenders)} of {len(paper.authors)} author names are not in JACoW "
        f"'Initials Surname' form: {listed}. Abbreviate given names to initials.",
        line=line,
        original=", ".join(offenders),
    )


def check_number_unit_format(paper: Paper) -> None:
    """Deprecated: number/unit spacing and case are now *edits*, not findings.

    JACoW number-unit spacing is the highest-volume nit in the corpus (231
    instances across 34 papers) and it is completely safe to apply, so it is
    handled by :func:`src.autofix.latex_edits.unit_edits` at
    :attr:`~src.edits.Tier.AUTO` instead of being reported 231 times for the
    editor to fix by hand.  This function is kept as a no-op so existing
    callers and tests keep working.
    """
    return None


def run_all(paper: Paper) -> None:
    """Run deterministic title and author checks in-place."""
    check_title_format(paper)
    check_author_format(paper)
