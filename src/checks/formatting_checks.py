"""Priority-2 formatting checks.

Each public function accepts a ``Paper`` and appends ``Finding`` objects to
``paper.findings``.

Checks implemented here
-----------------------
FMT-TITLE-01    \\title{} text is ALL CAPS.
FMT-TITLE-02    No trailing punctuation on title.
FMT-AUTH-01     Author names follow "Initials Surname" convention.
FMT-AUTH-02     Email \\thanks{} on corresponding author only.
FMT-FIG-01      Every figure is referenced in text before it appears.
FMT-FIG-02      Figure numbers are sequential starting at 1.
FMT-FIG-03      Figure caption format: "Figure N: <sentence>."
FMT-FIG-04      Every \\ref{fig:X} resolves to a \\label{fig:X}.
FMT-TBL-01      Every table is referenced in text before it appears.
FMT-TBL-02      Table numbers are sequential starting at 1.
FMT-TBL-03      Table caption format: "Table N: <description>." (above table).
FMT-UNIT-01     Non-breaking space between number and unit (LaTeX ~).
FMT-UNIT-02     SI unit abbreviations are correctly cased.
FMT-UNIT-03     Numeric ranges use en-dash, not hyphen.
"""

from __future__ import annotations

from src.models import Paper


def check_title_format(paper: Paper) -> None:
    """FMT-TITLE-01/02."""
    raise NotImplementedError


def check_author_format(paper: Paper) -> None:
    """FMT-AUTH-01/02."""
    raise NotImplementedError


def check_figure_format(paper: Paper) -> None:
    """FMT-FIG-01/02/03/04."""
    raise NotImplementedError


def check_table_format(paper: Paper) -> None:
    """FMT-TBL-01/02/03."""
    raise NotImplementedError


def check_number_unit_format(paper: Paper) -> None:
    """FMT-UNIT-01/02/03."""
    raise NotImplementedError


def run_all(paper: Paper) -> None:
    """Run every formatting check against *paper*, appending findings in-place."""
    check_title_format(paper)
    check_author_format(paper)
    check_figure_format(paper)
    check_table_format(paper)
    check_number_unit_format(paper)
