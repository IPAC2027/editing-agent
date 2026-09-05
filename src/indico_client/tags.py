"""JACoW's editorial tag vocabulary, and how the agent's checks map onto it.

Every JACoW editor already classifies each correction they make, by hand, from
a fixed list of codes — ``TC12`` for a badly formatted unit, ``TC14`` for a DOI
added to a reference, ``FC06`` for a source that will not compile. The list is
per event, but it is stable across conferences because it is the community's
own taxonomy of what goes wrong with a paper.

That changes what this agent should write into Indico. An earlier design
invented its own triage tags (CLEAN / DECIDE / MUST-FIX) and put them in the
same column. That was wrong twice over: the column is a *record of corrections
made*, not a status, and a parallel vocabulary would dilute one that already
means something to every editor in the collaboration.

So the agent proposes codes from this list instead, and the editor confirms
them exactly as they confirm an edit — filling in a form they currently type by
hand, rather than adding a column they have to learn.

Two honest limits are encoded here as data:

* :data:`CHECK_TO_TAG` maps only where the agent's evidence really is that tag.
  A check with no entry proposes nothing. Silence is correct; a plausible guess
  is not, because a wrong tag is a wrong statement about what the editor did.
* :data:`OUT_OF_REACH` names every code the agent can never propose, with the
  reason. Most need the rendered PDF or a human eye. Three do not, and are
  marked ``not implemented`` — they are the roadmap this vocabulary hands us.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The families, in the order JACoW lists them.
FAMILIES = {
    "FC": "Files and compilation",
    "FP": "Fonts",
    "MP": "Miscellaneous",
    "TC": "Typesetting and formatting",
    "UT": "Template usage",
    "QA": "Quality assurance (set by the editing service)",
    "PRC": "Processed (set by the editing service)",
}


@dataclass(frozen=True)
class TagSpec:
    """One code in the vocabulary, as the conference defines it."""

    code: str
    title: str
    colour: str

    @property
    def family(self) -> str:
        return "PRC" if self.code == "PRC" else self.code[:2]


#: The vocabulary as HIAT2025 defines it. Titles are trimmed for reading; the
#: authoritative text is whatever ``GET /editing/api/tags`` returns for the
#: event being worked on, which is why :func:`resolve` takes the live list.
VOCABULARY: dict[str, TagSpec] = {
    t.code: t for t in [
        TagSpec("FC00", "General problems with files", "red"),
        TagSpec("FC01", "Source, PDF or supporting file missing; file wrongly named", "red"),
        TagSpec("FC02", "Problem with pictures", "red"),
        TagSpec("FC03", "BibTeX: wrong reference type, bib field or content; missing field", "red"),
        TagSpec("FC04", "Multiple or unusable files", "red"),
        TagSpec("FC05", "Bad EPS/PS/PDF", "red"),
        TagSpec("FC06", "LaTeX error: not compilable, package missing, labels multiply defined", "red"),
        TagSpec("FC10", "Full page image, no text", "red"),
        TagSpec("FP00", "General problems with fonts", "orange"),
        TagSpec("FP01", "Font problems (wrong or missing, Type3/bitmap, too many)", "orange"),
        TagSpec("FP02", "Font problems (missing character, unknown glyph or encoding)", "orange"),
        TagSpec("MP00", "Miscellaneous problems", "yellow"),
        TagSpec("MP01", "Status set to RED to enable re-upload", "yellow"),
        TagSpec("MP02", "Spelling corrections", "yellow"),
        TagSpec("MP03", "Too many pages, blank pages", "yellow"),
        TagSpec("MP04", "Comments to the author / editor in chief", "yellow"),
        TagSpec("TC00", "General problems related to formatting", "violet"),
        TagSpec("TC01", "Incorrect title, authors, affiliation formatting", "violet"),
        TagSpec("TC02", "Text formatting incorrect (paragraphs, headings, number/unit split over lines)", "violet"),
        TagSpec("TC03", "Table formatting incorrect", "violet"),
        TagSpec("TC04", "Figure formatting incorrect (margins, caption)", "violet"),
        TagSpec("TC05", "Footnote formatting incorrect", "violet"),
        TagSpec("TC06", "Reference or reference formatting incorrect", "violet"),
        TagSpec("TC07", "Figure/Table/Equation/Reference numbers not in sequence", "violet"),
        TagSpec("TC08", "Figure/Table/Reference not referenced in text or missing", "violet"),
        TagSpec("TC09", "Equation/Eq., Figure/Fig., Table wrongly used in text", "violet"),
        TagSpec("TC10", "Graphics problem (too small, resolution, text not readable)", "violet"),
        TagSpec("TC11", "Equation formatting incorrect", "violet"),
        TagSpec("TC12", "Badly formatted units (italic, spacing, mu italicised)", "violet"),
        TagSpec("TC14", "Reference formatting: missing info, DOI/URL added or corrected", "violet"),
        TagSpec("UT00", "General problems with template usage", "pink"),
        TagSpec("UT01", "Template not used or altered; wrong column widths; old template", "pink"),
        TagSpec("UT02", "A4 on US or US on A4", "pink"),
        TagSpec("QA01", "QA approved", "green"),
        TagSpec("QA02", "QA pending", "yellow"),
        TagSpec("QA03", "QA failed", "red"),
        TagSpec("PRC", "Processed", "brown"),
    ]
}

#: Codes the editing service owns. The agent must never write these: they are
#: the QA gate's own state, and forging it would tell an editor that a paper
#: passed a check that never ran.
SERVICE_OWNED = frozenset({"QA01", "QA02", "QA03", "PRC"})


#: check id -> tag code. Only where the agent's evidence *is* that tag.
CHECK_TO_TAG: dict[str, str] = {
    # Units --------------------------------------------------------------
    "FMT-UNIT-01": "TC12",   # missing non-breaking space
    "FMT-UNIT-02": "TC12",   # wrong capitalisation

    # Title, authors, affiliation ---------------------------------------
    "FMT-TITLE-02": "TC01",
    "FMT-AUTH-01": "TC01",

    # References: formatting ---------------------------------------------
    "FMT-REF-01": "TC06",
    "FMT-TITLE-03": "TC06",
    "TITLE-01": "TC06",
    "AUTH-01": "TC06",
    "AUTH-02": "TC06",
    "REF-PAGES-01": "TC06",
    "REF-NUM-01": "TC06",
    "REF-SEC-01": "TC06",
    "REF-NUM-02": "TC06",
    "CITE-BRACKET-01": "TC06",
    "CITE-SPACE-01": "TC06",
    "JACOW-CLS-03": "TC06",

    # References: numbering and linkage ----------------------------------
    "CITE-ORDER-01": "TC07",
    "CITE-TEXT-02": "TC07",
    "CITE-LINK-01": "TC08",

    # References: DOIs ----------------------------------------------------
    "DOI-FMT-01": "TC14",
    "DOI-FMT-02": "TC14",
    "DOI-FMT-03": "TC14",
    "DOI-REQ-01": "TC14",
    "URL-AS-DOI-01": "TC14",
    "PROC-REQ-01": "TC14",
    "PROC-REQ-02": "TC14",
    "PROC-REQ-03": "TC14",
    "JACOW-CLS-02": "TC14",

    # Files and build ------------------------------------------------------
    "BIB-EDIT-01": "FC03",
    "BIB-PARSE-01": "FC03",
    "BIB-MISSING-01": "FC01",
    "FIG-MISSING-01": "FC01",
    "FIG-ARCHIVE-01": "FC04",
    "BUILD-FAIL": "FC06",

    # Everything else -------------------------------------------------------
    "PAGE-LIMIT-01": "MP03",
    "JACOW-CLS-01": "UT01",
}


#: Codes the agent cannot propose, and why. Kept as data so the coverage claim
#: is checked by a test rather than asserted in a README that drifts.
OUT_OF_REACH: dict[str, str] = {
    "FC00": "a catch-all an editor chooses, not a check",
    "FC02": "needs the rendered image in the PDF",
    "FC05": "needs the distilled PDF",
    "FC10": "needs the rendered page",
    "FP00": "needs the PDF's font table",
    "FP01": "needs the PDF's font table",
    "FP02": "needs the PDF's font table",
    "MP00": "a catch-all an editor chooses, not a check",
    "MP01": "a workflow action, not a property of the paper",
    "MP02": "spelling is deliberately out of scope",
    "MP04": "an editor's own message",
    "TC00": "a catch-all an editor chooses, not a check",
    "TC02": "needs the rendered page for paragraphs, headings, indentation and "
            "column widths. Its one deterministic part — a number and its unit "
            "split over a line break — is fixed by the non-breaking space edit, "
            "which is tagged TC12 because that code names the unit itself",
    "TC03": "needs the rendered table",
    "TC04": "needs the rendered figure and its caption box",
    "TC05": "needs the rendered footnote position",
    "TC07": "not implemented: only citation order is checked, not figure, "
            "table or equation numbering",
    "TC08": "not implemented for figures and tables: only unresolved citations "
            "are found, not 'never referenced in the text'",
    "TC09": "not implemented: Fig./Eq./Table abbreviation and capitalisation in "
            "running text is deterministic and worth building",
    "TC10": "needs the rendered graphic",
    "TC11": "needs the rendered equation",
    "UT00": "a catch-all an editor chooses, not a check",
    "UT02": "needs the page geometry of the PDF",
}

#: The three above that need no PDF and no judgement — the roadmap this
#: vocabulary hands us, in the order the tag usage suggests.
BUILDABLE_NEXT = ("TC09", "TC07", "TC08")


def tag_codes_for(check_ids) -> list[str]:
    """The codes to propose for a set of check ids, in vocabulary order.

    Deduplicated, because five unit fixes are one ``TC12`` on the paper — an
    editor tags what was wrong, once, not once per occurrence.
    """
    codes = {CHECK_TO_TAG[c] for c in check_ids if c in CHECK_TO_TAG}
    return sorted(codes, key=lambda c: list(VOCABULARY).index(c))


def resolve(codes, live_tags) -> tuple[list[int], list[str]]:
    """Turn codes into this event's tag ids. Returns ``(ids, missing_codes)``.

    The vocabulary is per event: a conference may not define every code, and
    HIAT2025 also carries a duplicated ``TC_01``–``TC_04`` set with different
    colours. So codes are always resolved against what the event actually has,
    and anything absent is reported rather than invented.
    """
    by_code = {t["code"]: t["id"] for t in live_tags}
    ids, missing = [], []
    for code in codes:
        if code in SERVICE_OWNED:
            continue  # never ours to write
        if code in by_code:
            ids.append(by_code[code])
        else:
            missing.append(code)
    return ids, missing
