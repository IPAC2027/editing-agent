"""References in the exact layout of Appendix B of the JACoW style guide.

The engine reads a reference into fields, decides which of Appendix B's 16
kinds it is, completes what the layout needs from refs.jacow.org, the JACoW
conference list, Crossref, DataCite and abbrevIso, and writes it from that
kind's template: :func:`format_reference` for a ``\\bibitem`` or a Word
reference (the text is rewritten), :func:`src.annexb.bib.bib_edits` for a
``.bib`` file (the fields are corrected so that ``jacow.bbx`` prints the same
layout).
"""

from src.annexb.categories import CATEGORIES, HEADINGS, render
from src.annexb.engine import format_reference
from src.annexb.model import Name, Outcome, Problem, Ref

__all__ = ["format_reference", "CATEGORIES", "HEADINGS", "render", "Name", "Outcome",
           "Problem", "Ref"]
