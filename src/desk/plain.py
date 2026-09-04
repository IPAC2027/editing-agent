"""Plain English for everything the agent reports.

The review desk is used by editors, not programmers. A check ID like
``FMT-UNIT-02`` and a message like "Use the standard case for the SI unit
abbreviation" tell a developer what happened; they do not tell an editor what
they are being asked to decide.

Every check therefore has three things here:

``label``
    What changed, as a noun phrase, in four or five words. This is the heading
    on the card.
``why``
    One sentence saying why JACoW cares. No jargon, no check IDs.
``owner``
    Who has to act: the ``tool`` has already done it, the ``editor`` must
    decide, or only the ``author`` can supply what is missing. This is what
    lets the desk sort work into "your decisions" and "send back to the
    author".

Anything without an entry falls back to the raw message, so an unmapped check
degrades to slightly worse prose rather than to a blank card.
"""

from __future__ import annotations

from dataclasses import dataclass

TOOL = "tool"
EDITOR = "editor"
AUTHOR = "author"

_OWNER_LABELS = {
    TOOL: "Already done",
    EDITOR: "Your decision",
    AUTHOR: "Back to the author",
}


@dataclass(frozen=True)
class Explanation:
    label: str
    why: str
    owner: str = EDITOR
    fixed: str = ""
    """How to say "we did this for you" in a letter to the author.

    The card heading is a noun phrase built for scanning ("Space between
    number and unit"); a letter needs a fragment that reads aloud ("the spacing
    between numbers and their units"). Falls back to the lower-cased label,
    which is passable but not good.
    """

    ask: str = ""
    """How to ask the author to fix it.

    Without this the letter falls back to the raw check message, which is
    written for a developer and reads like it.
    """

    @property
    def owner_label(self) -> str:
        return _OWNER_LABELS.get(self.owner, self.owner)

    def fixed_phrase(self) -> str:
        return self.fixed or (self.label[0].lower() + self.label[1:] if self.label else "")

    def ask_phrase(self) -> str:
        return self.ask or self.why


EXPLANATIONS: dict[str, Explanation] = {
    # ---- presentation the tool handles on its own ----------------------
    "FMT-UNIT-01": Explanation(
        "Space between number and unit",
        "JACoW needs a non-breaking space here so a value and its unit never "
        "end up split across two lines.",
        fixed=(
            "the spacing between numbers and their units"
        ),
        owner=TOOL,
    ),
    "DOI-FMT-01": Explanation(
        "DOI written the JACoW way",
        "DOIs are printed as doi:10.xxxx/yyyy — lowercase, no space after the "
        "colon.",
        fixed=(
            "the way DOIs are written"
        ),
        owner=TOOL,
    ),
    "DOI-FMT-02": Explanation(
        "DOI link turned into a DOI",
        "A DOI wrapped in a web-link command prints as a bare URL. Written as "
        "a DOI it prints in the house style and stays clickable.",
        fixed=(
            "DOI links, which are now written as DOIs"
        ),
        owner=TOOL,
    ),
    "DOI-FMT-03": Explanation(
        "DOI field tidied",
        "The reference file should hold the bare DOI; the template builds the "
        "link itself.",
        fixed=(
            "the DOI fields in the reference file"
        ),
        owner=TOOL,
    ),
    "REF-PAGES-01": Explanation(
        "Page range dash",
        "A page range uses an en dash, which the reference file writes as two "
        "hyphens.",
        fixed=(
            "the dashes in page ranges"
        ),
        owner=TOOL,
    ),
    "CITE-BRACKET-01": Explanation(
        "Citations merged into one bracket",
        "Two citations next to each other belong in a single bracket, as "
        "[1, 2].",
        fixed=(
            "citations that sat in separate brackets"
        ),
        owner=TOOL,
    ),
    "CITE-SPACE-01": Explanation(
        "Spacing inside a citation",
        "Citation brackets carry no padding, and a comma inside one is "
        "followed by a single space.",
        fixed=(
            "the spacing inside citation brackets"
        ),
        owner=TOOL,
    ),
    "AUTH-02": Explanation(
        "'et al.' punctuation",
        "It is written 'et al.' — no full stop after 'et', one after 'al'.",
        fixed=(
            "the punctuation of 'et al.'"
        ),
        owner=TOOL,
    ),

    # ---- decisions for the editor --------------------------------------
    "FMT-UNIT-02": Explanation(
        "Capitals in a unit",
        "The unit looks mistyped. Check it is the quantity the author meant "
        "before accepting — changing a capital can change the value by a "
        "factor of a million.",
        fixed=(
            "the capitals in a unit abbreviation"
        ),
        owner=EDITOR,
    ),
    "FMT-AUTH-01": Explanation(
        "Author's given name in full",
        "JACoW lists authors as initials and surname. Reject this if the first "
        "word is not actually a given name.",
        fixed=(
            "author names, now given as initials and surname"
        ),
        owner=EDITOR,
    ),
    "FMT-TITLE-02": Explanation(
        "Full stop at the end of the title",
        "A JACoW title carries no punctuation at the end.",
        fixed=(
            "the punctuation at the end of the title"
        ),
        owner=EDITOR,
    ),
    "FMT-TITLE-03": Explanation(
        "Reference title in sentence case",
        "Reference titles are sentence case: only the first word and proper "
        "nouns keep capitals. Reject if any of these words is a name.",
        fixed=(
            "reference titles, now in sentence case"
        ),
        owner=EDITOR,
    ),
    "FMT-REF-01": Explanation(
        "Reference reformatted to house style",
        "The reference has been rewritten to the JACoW layout. Every number, "
        "DOI, word and capital in the original was checked to still be there.",
        fixed=(
            "the layout of references, now in JACoW style"
        ),
        owner=EDITOR,
    ),
    "REF-NUM-02": Explanation(
        "Reference list reordered",
        "Reference numbers must count up in the order the paper first cites "
        "them. Only the order changes — no reference text is touched, and the "
        "numbers in the text update themselves.",
        fixed=(
            "the order of the reference list, so the numbers count up with first citation"
        ),
        owner=EDITOR,
    ),
    "URL-AS-DOI-01": Explanation(
        "Web link where a DOI belongs",
        "JACoW prefers a DOI to a URL, because links rot and DOIs do not.",
        fixed=(
            "web links replaced with DOIs where one exists"
        ),
        owner=EDITOR,
    ),

    # ---- things only the author can fix --------------------------------
    "FIG-MISSING-01": Explanation(
        "A figure file is missing",
        "The paper asks for an image that is not in the submission, so it "
        "cannot be built as sent.",
        ask=(
            "Please include the missing image file, or correct the file name in the source, so the paper can be built."
        ),
        owner=AUTHOR,
    ),
    "FIG-ARCHIVE-01": Explanation(
        "Figures are inside a zip file",
        "The images exist but are packed in an archive. Unpack it before "
        "building; the paper itself is fine.",
        owner=EDITOR,
    ),
    "BIB-MISSING-01": Explanation(
        "A reference file is missing",
        "The paper points at a bibliography file that is not in the "
        "submission, usually because it was renamed.",
        ask=(
            "Please include the bibliography file the paper refers to, or correct its name in the source."
        ),
        owner=AUTHOR,
    ),
    "BIB-PARSE-01": Explanation(
        "A reference file could not be read",
        "The bibliography file has a syntax error, so its entries were not "
        "checked.",
        ask=(
            "Please fix the syntax error in the bibliography file so its entries can be read."
        ),
        owner=AUTHOR,
    ),
    "CITE-LINK-01": Explanation(
        "A citation has no reference",
        "The text cites something that is not in the reference list.",
        ask=(
            "Please add the missing reference, or remove the citation to it."
        ),
        owner=AUTHOR,
    ),
    "REF-SEC-01": Explanation(
        "No reference list found",
        "The paper has no bibliography section at all.",
        ask=(
            "Please add a reference section."
        ),
        owner=AUTHOR,
    ),
    "REF-NUM-01": Explanation(
        "Reference list is empty",
        "The bibliography section exists but contains no entries.",
        ask=(
            "Please add the reference entries; the section is currently empty."
        ),
        owner=AUTHOR,
    ),
    "PAGE-LIMIT-01": Explanation(
        "Over the page limit",
        "Body text must fit in three pages; only the reference list may run "
        "onto page four.",
        ask=(
            "Please shorten the paper so the body text fits in three pages; only the reference list may run onto page four."
        ),
        owner=AUTHOR,
    ),
    "BUILD-FAIL": Explanation(
        "The paper does not compile",
        "The submission has a LaTeX error, so no PDF can be produced from it.",
        ask=(
            "Please fix the LaTeX error so the paper compiles, and resubmit."
        ),
        owner=AUTHOR,
    ),
    "JACOW-CLS-02": Explanation(
        "Reference style will hide DOIs",
        "The bibliography style in use does not print DOI fields, so the DOIs "
        "in the reference file will not appear in the PDF.",
        ask=(
            "Please switch to BibLaTeX, or to another bibliography style that prints DOI fields, so the DOIs in your references appear in the PDF."
        ),
        owner=AUTHOR,
    ),

    "JACOW-CLS-03": Explanation(
        "Reference list written by hand",
        "Valid, but BibLaTeX formats references more consistently. Noted for "
        "the record; nothing to fix.",
        owner=TOOL,
    ),

    # ---- notes, for the record only ------------------------------------
    "JACOW-CLS-01": Explanation(
        "Template version",
        "Noted for the record. The template version is the same for everyone "
        "at a conference and is not something to fix per paper.",
        owner=TOOL,
    ),
    "DOI-MISSING-01": Explanation(
        "DOIs not looked up",
        "Some references have no DOI. Whether one exists could not be checked "
        "on this run.",
        owner=EDITOR,
    ),
    "BIB-EDIT-01": Explanation(
        "Reference file also tidied",
        "Presentation fixes were made in the bibliography file as well as the "
        "paper.",
        owner=TOOL,
    ),
    "BUILD-OK": Explanation(
        "The paper compiles",
        "The edited paper was built successfully, so none of the automatic "
        "changes broke it.",
        owner=TOOL,
    ),
    "BUILD-SKIP": Explanation(
        "Not compiled",
        "No LaTeX installation was found, so the edited paper was not built.",
        owner=TOOL,
    ),
    "EDIT-OVERLAP-01": Explanation(
        "Overlapping suggestions merged",
        "Two suggestions covered the same text; the narrower one was kept.",
        owner=TOOL,
    ),
    "WORD-TRACK-00": Explanation(
        "Corrections written as tracked changes",
        "The Word file carries each correction as a tracked change.",
        owner=TOOL,
    ),
    "WORD-TRACK-01": Explanation(
        "A correction needs doing by hand",
        "This one could not be written as a tracked change, so it has to be "
        "applied in Word manually.",
        owner=EDITOR,
    ),
    "WORD-TRACK-02": Explanation(
        "Tracked changes could not be written",
        "The corrections are listed here but the Word file could not be "
        "produced.",
        owner=EDITOR,
    ),
    "LLM-REVIEW-01": Explanation(
        "Optional model review",
        "An advisory second opinion. Nothing here has been applied.",
        owner=EDITOR,
    ),
    "LLM-SUPPRESS-01": Explanation(
        "Some findings were hidden",
        "A model judged these to be false alarms and hid them.",
        owner=EDITOR,
    ),
    "EDITOR-NOTE": Explanation(
        "Your note",
        "Something you spotted yourself.",
        owner=EDITOR,
    ),
    "EDITOR-EDIT": Explanation(
        "Your edit",
        "A change you made by hand.",
        owner=EDITOR,
    ),
}

_FALLBACK = Explanation(
    "Needs a look",
    "The agent flagged this but has no plain-English description for it yet.",
    EDITOR,
)


def explain(check_id: str) -> Explanation:
    return EXPLANATIONS.get(check_id, _FALLBACK)


def label(check_id: str) -> str:
    return explain(check_id).label


def owner(check_id: str, severity: str = "warning") -> str:
    """Who has to act, taking severity into account.

    Some checks report at two severities under one id — the bibliography-style
    check is informational when it is only a preference, and an error when it
    will actually hide DOIs from the printed PDF. An informational finding is
    never put in front of an author, whatever its check says.
    """
    resolved = explain(check_id).owner
    if severity == "info" and resolved == AUTHOR:
        return TOOL
    return resolved


# ---------------------------------------------------------------------------
# Severity, in words an editor uses
# ---------------------------------------------------------------------------

SEVERITY_WORDS = {
    "error": "Must fix",
    "warning": "Worth a look",
    "info": "For the record",
}


def severity_word(severity: str) -> str:
    return SEVERITY_WORDS.get(severity, severity)


# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

STATUS_WORDS = {
    "new": "Not started",
    "in_review": "In progress",
    "done": "Finished",
    "needs_author": "Waiting on author",
}


def status_word(status: str) -> str:
    return STATUS_WORDS.get(status, status)


# ---------------------------------------------------------------------------
# Readable titles
# ---------------------------------------------------------------------------

import re as _re

_TITLE_CLEANERS = (
    (_re.compile(r"\\thanks\s*\{[^{}]*\}"), ""),
    (_re.compile(r"\\footnote\s*\{[^{}]*\}"), ""),
    (_re.compile(r"\\NoCaseChange\s*\{([^{}]*)\}"), r"\1"),
    (_re.compile(r"\\text(?:it|bf|rm|sf|tt|sc)\s*\{([^{}]*)\}"), r"\1"),
    (_re.compile(r"\\(?:mathrm|mathit|mathbf|ensuremath)\s*\{([^{}]*)\}"), r"\1"),
    (_re.compile(r"\\\\"), " "),
    (_re.compile(r"\$[^$]*\$"), " "),
    (_re.compile(r"\\[a-zA-Z@]+\*?"), " "),
    (_re.compile(r"[{}~]"), " "),
)


def readable_title(title: str) -> str:
    """A LaTeX title as a person would read it aloud.

    Titles arrive with markup in them — ``\\NoCaseChange{GeV}``, a ``\\thanks``
    footnote, a stray ``\\\\`` line break, inline maths. Showing that raw in a
    worklist makes the one column an editor scans hardest the least readable
    thing on the page.
    """
    text = title or ""
    for pattern, replacement in _TITLE_CLEANERS:
        text = pattern.sub(replacement, text)
    return " ".join(text.split()).strip(" ,;:")
