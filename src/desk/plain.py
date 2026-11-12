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
    "FMT-REF-03": Explanation(
        "Reference left as written",
        "A JACoW-style rewrite was computed but would have lost or changed "
        "information with no authoritative source behind it, so the reference "
        "is unchanged. The note says what would have been lost; fix it by hand "
        "if the formatting needs it.",
        owner=EDITOR,
    ),
    "FMT-REF-02": Explanation(
        "Reference punctuation",
        "DOI form, 'et al.' punctuation, the comma before 'and', quotation "
        "marks and dashes were put in JACoW form; nothing else in the "
        "reference changed.",
        fixed="reference punctuation and DOI form",
        owner=TOOL,
    ),
    "REF-INT-01": Explanation(
        "DOI belongs to another paper",
        "The DOI in this reference resolves to a different publication, so "
        "either the DOI or the rest of the reference is wrong.",
        ask="Please check the DOI in this reference: it points to a different paper.",
        owner=AUTHOR,
    ),
    "REF-INT-02": Explanation(
        "Reference not found anywhere",
        "Several indexes were searched and none has this reference. It may be "
        "mistyped, unindexed, or not exist; check it by hand.",
        owner=EDITOR,
    ),
    "REF-INT-03": Explanation(
        "Reference not confirmed",
        "The reference was not found in Crossref, DataCite or the JACoW "
        "proceedings. This is common for reports, talks, strategy inputs, "
        "preprints and older papers, and is not a fault.",
        owner=TOOL,
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

    "AUTH-01": Explanation(
        "Comma before the last author",
        "With three or more authors JACoW puts a comma before the final "
        "'and' — 'A, B, and C'.",
        owner=TOOL,
        fixed="the comma before the last author in a reference",
    ),
    "TITLE-01": Explanation(
        "Reference title in Title Case",
        "The title looks title-cased. JACoW reference titles are sentence "
        "case: only the first word and proper nouns keep capitals.",
        owner=EDITOR,
    ),
    "PROC-REQ-01": Explanation(
        "Proceedings reference has no venue",
        "A proceedings reference names the conference — 'in Proc. IPAC'23' — "
        "so a reader can find the volume.",
        owner=AUTHOR,
        ask=(
            "Please write proceedings references in the JACoW form: "
            "in Proc. CONF'YY, City, Country, Month Year, pp. N-M."
        ),
    ),
    "PROC-REQ-02": Explanation(
        "Proceedings reference has no year",
        "A proceedings reference needs the year of the conference.",
        owner=AUTHOR,
        ask="Please add the conference year to this proceedings reference.",
    ),
    "PROC-REQ-03": Explanation(
        "Proceedings reference has no pages or DOI",
        "A proceedings reference needs either page numbers or a DOI, so the "
        "paper can actually be located.",
        owner=AUTHOR,
        ask=(
            "Please add page numbers (pp. N-M) or a DOI to this proceedings "
            "reference."
        ),
    ),
    "CITE-ORDER-01": Explanation(
        "Citations out of order in the text",
        "Reference numbers must count up in the order the text first cites "
        "them. Reordering the reference list usually fixes it.",
        owner=EDITOR,
    ),
    "CITE-TEXT-02": Explanation(
        "Citations out of order in the text",
        "Reference numbers must count up in the order the text first cites "
        "them. In a Word document the numbers are typed by hand, so this has "
        "to be corrected in the text and the list together.",
        owner=AUTHOR,
        ask=(
            "Please renumber the citations and the reference list so the "
            "numbers count up in the order the text first cites them."
        ),
    ),
    "DOI-REQ-01": Explanation(
        "Reference has no DOI",
        "JACoW asks for a DOI on papers that have one. Where a DOI was found "
        "for you it is shown; otherwise it needs looking up.",
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
        "Body text must fit within the conference's page limit; only the "
        "reference list may run onto the following page.",
        ask=(
            "Please shorten the paper so the body text fits within the page limit; only the reference list may run onto the following page."
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
    "WORD-TITLE-01": Explanation(
        "Title not in capitals",
        "The paper title is set in capitals, keeping the case of units and "
        "names such as GeV or SwissFEL.",
        owner=EDITOR,
    ),
    "WORD-AUTH-02": Explanation(
        "'and' in the author list",
        "Author names are separated by commas only.",
        owner=EDITOR,
    ),
    "WORD-UNIT-01": Explanation(
        "Space before a unit",
        "A value and its unit are joined by a non-breaking space so they never "
        "split across lines.",
        owner=EDITOR,
    ),
    "WORD-UNIT-02": Explanation(
        "Unit symbol case",
        "Units use the standard symbol and case, such as MeV or GHz.",
        owner=EDITOR,
    ),
    "WORD-PARA-01": Explanation(
        "First-line indent",
        "Body paragraphs start with a 0.33 cm first-line indent; a direct override set it to something else.",
        owner=EDITOR,
    ),
    "WORD-PARA-02": Explanation(
        "Widow/orphan control",
        "Widow/orphan control keeps a paragraph from leaving a single line at the top or bottom of a column.",
        owner=EDITOR,
    ),
    "WORD-PARA-03": Explanation(
        "Body text in the wrong style",
        "Body text uses the body-text style: 10 pt, justified, first line indented 0.33 cm.",
        owner=EDITOR,
    ),
    "WORD-PARA-04": Explanation(
        "Body text font size",
        "Body text is 10 pt; a direct font size overrides the style.",
        owner=EDITOR,
    ),
    "WORD-HEAD-03": Explanation(
        "Heading separated from its text",
        "A heading is kept with the next paragraph, so a column break never falls between them.",
        owner=EDITOR,
    ),
    "WORD-HEAD-04": Explanation(
        "Third-level heading on its own line",
        "Third-level headings are 10 pt bold and run into the paragraph text, followed by an em space.",
        owner=EDITOR,
    ),
    "WORD-HEAD-05": Explanation(
        "Subsection heading format",
        "Subsection headings are 12 pt italic and left aligned.",
        owner=EDITOR,
    ),
    "WORD-LAYOUT-01": Explanation(
        "Page layout",
        "The page is 595 by 792 pt with JACoW margins and two columns of 82.5 mm.",
        owner=AUTHOR,
    ),
    "WORD-FONT-01": Explanation(
        "Font not allowed",
        "Only Times New Roman, Symbol and Liberation Mono (for DOIs and URLs) are used.",
        owner=AUTHOR,
    ),
    "WORD-FONT-02": Explanation(
        "Body font size",
        "Body text is 10 pt.",
        owner=EDITOR,
    ),
    "WORD-FONT-03": Explanation(
        "Fonts not embedded",
        "Fonts are embedded in the Word file (Options, Save, Embed fonts in the file).",
        owner=AUTHOR,
    ),
    "WORD-LINK-01": Explanation(
        "Web address hyperlinked",
        "Only DOIs are hyperlinked; other web addresses are plain text.",
        owner=EDITOR,
    ),
    "WORD-LINK-02": Explanation(
        "DOI not hyperlinked",
        "Every DOI carries a hyperlink.",
        owner=EDITOR,
    ),
    "WORD-PAGENUM-01": Explanation(
        "Page numbers present",
        "Papers carry no page numbers; they are added in the proceedings.",
        owner=EDITOR,
    ),
    "WORD-FOOTNOTE-01": Explanation(
        "Word footnotes used",
        "Footnotes go in a text box at the bottom of the column, never Word's footnote feature.",
        owner=AUTHOR,
    ),
    "WORD-REFSPACE-01": Explanation(
        "Reference line spacing",
        "References use line spacing of exactly 10.4 pt.",
        owner=EDITOR,
    ),
    "WORD-TITLE-03": Explanation(
        "Title not in capitals",
        "The title is 14 pt bold uppercase.",
        owner=EDITOR,
    ),
    "WORD-AUDIT-01": Explanation(
        "Document check",
        "A document-level check from the JACoW formatting audit; see the note.",
        owner=TOOL,
    ),
    "WORD-HEAD-01": Explanation(
        "Numbered heading",
        "JACoW section and subsection headings are not numbered.",
        owner=EDITOR,
    ),
    "WORD-HEAD-02": Explanation(
        "Subsection heading case",
        "Subsection headings use Title Case: principal words capitalised.",
        owner=EDITOR,
    ),
    "WORD-STYLE-01": Explanation(
        "Body text in a heading style",
        "A paragraph of ordinary text carries a heading style, so it is laid "
        "out as a heading. Give it the body-text style.",
        owner=EDITOR,
    ),
    "WORD-CAP-01": Explanation(
        "Caption label",
        "Captions start 'Figure 1:' or 'Table 1:', with a colon after the number.",
        owner=EDITOR,
    ),
    "WORD-CAP-02": Explanation(
        "Figure caption full stop",
        "A figure caption ends with a full stop.",
        owner=EDITOR,
    ),
    "WORD-CAP-03": Explanation(
        "Table caption full stop",
        "A table caption written as a heading has no full stop at the end.",
        owner=EDITOR,
    ),
    "TXT-ACR-01": Explanation(
        "Acronym not expanded",
        "Every acronym is written out in full the first time it is used, in the "
        "abstract and again in the body.",
        ask=("Please expand each acronym the first time it is used, in the abstract "
             "and in the main text."),
        owner=AUTHOR,
    ),
    "TXT-ABS-01": Explanation(
        "Citation in the abstract",
        "The abstract must stand alone, so it may not cite references.",
        ask="Please remove the reference citation from the abstract.",
        owner=AUTHOR,
    ),
    "TXT-CITE-01": Explanation(
        "Citations in separate brackets",
        "Several citations go in one bracket, as in [1, 2], with ranges such "
        "as [1-3] where they apply.",
        owner=EDITOR,
    ),
    "TXT-TAB-01": Explanation(
        "'Tab.' abbreviation",
        "A table reference is always written in full, as 'Table 1'.",
        owner=EDITOR,
    ),
    "TXT-FIG-01": Explanation(
        "'Fig.' at the start of a sentence",
        "Use 'Fig. 1' within a sentence, but write 'Figure 1' when it begins one.",
        owner=EDITOR,
    ),
    "TXT-EQ-01": Explanation(
        "Equation reference",
        "Within a sentence an equation is cited as 'Eq. (1)', with the number "
        "in parentheses.",
        owner=EDITOR,
    ),
    "REF-FORM-01": Explanation(
        "Unpublished paper cited as published",
        "A paper that was presented but never published has no proceedings, so "
        "it is cited as 'presented at', without 'in Proc.'.",
        owner=EDITOR,
    ),
    "REF-FORM-02": Explanation(
        "Journal named for a submitted paper",
        "For a paper submitted but not yet accepted, the journal is not named: "
        "'submitted for publication'.",
        owner=EDITOR,
    ),
    "PDF-00": Explanation(
        "PDF not checked",
        "The author's PDF could not be read, so its page size, margins, fonts "
        "and links were not checked.",
        owner=TOOL,
    ),
    "PDF-SIZE-01": Explanation(
        "Wrong page size",
        "JACoW papers are 595 by 792 points; A4 and US Letter pages are both "
        "the wrong size.",
        ask=("Please produce the PDF from the JACoW template, whose page size is "
             "595 by 792 points (20.99 by 27.94 cm)."),
        owner=AUTHOR,
    ),
    "PDF-MARGIN-01": Explanation(
        "Content in the margins",
        "Text or images reach into the page margins, which must stay clear.",
        ask=("Please keep all text and figures inside the JACoW margins: 19 mm at "
             "the top and bottom and 20 mm at the sides."),
        owner=AUTHOR,
    ),
    "PDF-PAGENUM-01": Explanation(
        "Page numbers present",
        "Page numbers are added when the proceedings are produced, so the "
        "paper must not carry its own.",
        ask="Please remove the page numbers from the paper.",
        owner=AUTHOR,
    ),
    "PDF-FONT-01": Explanation(
        "Font not embedded",
        "Every font must be embedded in the PDF, including those inside "
        "figures, or the paper may not display or print correctly.",
        ask=("Please embed all fonts when producing the PDF (in Word: Options, "
             "Save, Embed fonts in the file), including the fonts in figures."),
        owner=AUTHOR,
    ),
    "PDF-FONT-02": Explanation(
        "Bitmap font",
        "A bitmap (Type 3) font displays and prints poorly; it usually comes "
        "from a figure or an old LaTeX setup.",
        ask=("Please regenerate the affected figures or PDF so that they use "
             "outline (Type 1 or TrueType) fonts."),
        owner=AUTHOR,
    ),
    "PDF-DOI-01": Explanation(
        "DOI split across lines",
        "A DOI must stay on one line so that it can be read and copied whole.",
        ask=("Please keep each DOI on a single line, starting it on a new line "
             "where necessary."),
        owner=AUTHOR,
    ),
    "PDF-LINK-01": Explanation(
        "Web address hyperlinked",
        "Only DOIs may be hyperlinked; other web addresses may appear as plain "
        "text but must not be links.",
        ask="Please remove the hyperlinks from web addresses that are not DOIs.",
        owner=AUTHOR,
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

    # ---- the Appendix B reference engine (src.annexb) ---------------------
    "REF-MISSING": Explanation(
        "Reference is missing a required part",
        "Appendix B's layout for this kind of reference needs a part the reference "
        "does not give, and no registry had it. It is named, never invented.",
        ask="Please complete this reference: a part Appendix B requires is missing.",
        owner=AUTHOR,
    ),
    "REF-KIND": Explanation(
        "Kind of reference not recognised",
        "The desk could not tell which of Appendix B's 16 kinds this reference is, "
        "so it is left as written. Edit it on the References tab.",
        owner=EDITOR,
    ),
    "REF-DROPPED": Explanation(
        "Words with no place in the layout",
        "Some words of the reference have no place in Appendix B's layout for its "
        "kind, so the rewrite leaves them out. Check nothing that matters was lost.",
        owner=EDITOR,
    ),
    "REF-DOI-WRONG": Explanation(
        "DOI does not match the reference",
        "The DOI written in the reference resolves to something else or not at all, "
        "and no correct one was found.",
        ask="Please check the DOI in this reference: it does not resolve to the cited work.",
        owner=AUTHOR,
    ),
    "REF-DOI-POSSIBLE": Explanation(
        "Possible DOI found",
        "A registry has a DOI that probably belongs to this reference, but not every "
        "detail matched, so it was not added. Check it before using it.",
        owner=EDITOR,
    ),
    "REF-TITLE-CASE": Explanation(
        "Title capitals need a look",
        "The title was put in sentence case, but some words may be names or acronyms "
        "whose capitals should stay.",
        owner=EDITOR,
    ),
    "REF-JOURNAL": Explanation(
        "Journal name",
        "The journal's abbreviation came from a source other than Annex C (or the "
        "name was corrected for a typo). Check it reads right.",
        owner=EDITOR,
    ),
    "BIB-ANNEXB-01": Explanation(
        "Reference entry set for the JACoW style",
        "The .bib entry's fields were set so that the JACoW bibliography style prints "
        "the reference in Appendix B's layout.",
        fixed="the bibliography entries, now set so they print in JACoW style",
        owner=EDITOR,
    ),
    "BIB-LAYOUT": Explanation(
        "Limit of the JACoW bibliography style",
        "The JACoW bibliography style cannot print this kind of reference exactly as "
        "Appendix B shows it. Nothing to do unless it matters for this paper.",
        owner=TOOL,
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
