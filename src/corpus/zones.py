"""Where in a paper a correction lives — because editors are not equally strict.

Editors apply the house style unevenly, and the unevenness is systematic rather
than random. From the people who do the work:

* **Front matter and references — strict.** Title, authors, affiliations and the
  bibliography are enforced close to the letter, and different editors do
  roughly the same thing.
* **Figures and tables — less strict.** Corrected when noticed, and what gets
  noticed varies.
* **Running text — not strict, and the most variable of all.** Two editors given
  the same paragraph will not make the same changes.

That single fact decides how every confirmation rate in this project must be
read, so it is encoded here rather than left in someone's head.

In a strict zone, agreement is achievable: if the editors did not make a change
the agent proposed, that is worth investigating, and a high rate is real
evidence a check could be trusted to apply itself.

In a loose zone, agreement is not achievable by anyone. A check that proposes
183 non-breaking spaces and sees 88 of them made has not failed — it is
operating where the editors themselves disagree. Its confirmation rate measures
editorial appetite, not correctness, and using it to demote a check would
delete something useful for no reason.
"""

from __future__ import annotations

import re

#: Zones, ordered from strictest to loosest.
FRONT = "front matter"
REFERENCES = "references"
FLOATS = "figures and tables"
BODY = "running text"
DOCUMENT = "whole document"

ZONES = (FRONT, REFERENCES, FLOATS, BODY, DOCUMENT)

#: How much a confirmation rate in this zone is worth as evidence.
STRICTNESS = {
    FRONT: "strict",
    REFERENCES: "strict",
    FLOATS: "variable",
    BODY: "loose — editors differ",
    DOCUMENT: "n/a",
}

#: A rate below this in a *strict* zone is worth a human's attention. In a loose
#: zone no threshold applies, because there is no agreement to fall short of.
CONCERN_BELOW = 0.5


CHECK_ZONE: dict[str, str] = {
    # Front matter — the paper's own title, authors, affiliations.
    "FMT-TITLE-02": FRONT,
    "FMT-AUTH-01": FRONT,
    "TITLE-01": FRONT,

    # References, and the citation apparatus that points at them. Citations sit
    # physically in running text but belong to the reference machinery, and the
    # editors treat them with the same strictness.
    "FMT-REF-01": REFERENCES,
    "FMT-TITLE-03": REFERENCES,
    "AUTH-01": REFERENCES,
    "AUTH-02": REFERENCES,
    "REF-PAGES-01": REFERENCES,
    "REF-NUM-01": REFERENCES,
    "REF-NUM-02": REFERENCES,
    "REF-SEC-01": REFERENCES,
    "CITE-BRACKET-01": REFERENCES,
    "CITE-SPACE-01": REFERENCES,
    "CITE-ORDER-01": REFERENCES,
    "CITE-TEXT-02": REFERENCES,
    "CITE-LINK-01": REFERENCES,
    "DOI-FMT-01": REFERENCES,
    "DOI-FMT-02": REFERENCES,
    "DOI-FMT-03": REFERENCES,
    "DOI-REQ-01": REFERENCES,
    "DOI-MISSING-01": REFERENCES,
    "URL-AS-DOI-01": REFERENCES,
    "PROC-REQ-01": REFERENCES,
    "PROC-REQ-02": REFERENCES,
    "PROC-REQ-03": REFERENCES,
    "BIB-EDIT-01": REFERENCES,
    "BIB-MISSING-01": REFERENCES,
    "BIB-PARSE-01": REFERENCES,

    # Figures and tables.
    "FIG-MISSING-01": FLOATS,
    "FIG-ARCHIVE-01": FLOATS,

    # Running text — the loose zone.
    "FMT-UNIT-01": BODY,
    "FMT-UNIT-02": BODY,

    # Properties of the file as a whole.
    "JACOW-CLS-01": DOCUMENT,
    "JACOW-CLS-02": DOCUMENT,
    "JACOW-CLS-03": DOCUMENT,
    "BUILD-FAIL": DOCUMENT,
    "BUILD-OK": DOCUMENT,
    "BUILD-SKIP": DOCUMENT,
    "PAGE-LIMIT-01": DOCUMENT,
}


def zone_of_check(check_id: str) -> str:
    return CHECK_ZONE.get(check_id, BODY)


_FRONT_RE = re.compile(
    r"\\(?:title|author|affiliation|thanks|email|orcid|maketitle|inst)\b|"
    r"\\textsuperscript\{\d", re.IGNORECASE)
_REFS_RE = re.compile(
    r"\\(?:bibitem|cite|doi|bibliography|url)\b|"
    r"\bdoi\s*:|\bin\s+Proc\.|\bpp?\.\s*\d|\bvol\.|\bet\s+al\b|arXiv",
    re.IGNORECASE)
_FLOAT_RE = re.compile(
    r"\\(?:caption|includegraphics|begin\{(?:figure|table|tabular)|"
    r"end\{(?:figure|table|tabular)|hline|toprule|midrule|multicolumn)\b|"
    r"^\s*(?:Figure|Fig\.|Table)\s+\d", re.IGNORECASE)
_PREAMBLE_RE = re.compile(r"\\(?:documentclass|usepackage|newcommand|input|def)\b")


def zone_of_text(text: str) -> str:
    """Which zone a piece of source belongs to.

    Order matters. A reference containing ``\\url`` also contains a caption-like
    word often enough that references have to win, and front matter has to be
    tested before references because an author block can carry a ``\\thanks``
    with a URL in it.
    """
    blob = text or ""
    if _PREAMBLE_RE.search(blob):
        return DOCUMENT
    if _FRONT_RE.search(blob):
        return FRONT
    if _REFS_RE.search(blob):
        return REFERENCES
    if _FLOAT_RE.search(blob):
        return FLOATS
    return BODY


def zone_of_hunk(hunk) -> str:
    """Classify an editorial correction by the text around it."""
    return zone_of_text(f"{hunk.context} {hunk.before} {hunk.after}")


def reading(zone: str, rate: float, proposals: int) -> str:
    """What a confirmation rate in this zone actually licenses you to say."""
    if proposals < 5:
        return "too few to say"
    if zone in (BODY, FLOATS):
        return ("editors vary here — the rate measures their appetite, "
                "not our correctness")
    if rate >= 0.9:
        return "strong: a strict zone, and they agree"
    if rate >= CONCERN_BELOW:
        return "mixed, in a zone where agreement is expected"
    return "low in a strict zone — investigate"
