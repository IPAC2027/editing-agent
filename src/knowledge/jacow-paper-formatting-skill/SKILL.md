---
name: jacow-paper-formatting
description: Format, check, or write JACoW (Joint Accelerator Conferences Website) conference papers in Microsoft Word, following the official JACoW MS Word style guide. Use whenever the user mentions JACoW, IPAC, LINAC, ICALEPCS, FLS, NAPAC, ICAP, Cyclotrons or other accelerator conference proceedings papers, JACoW templates, author/affiliation formatting, IEEE-style references with DOIs for proceedings, ISO 4 journal abbreviations, or asks to audit a .docx against JACoW rules - even if they do not say "style guide".
---

# JACoW paper formatting

Source: "Style Guide for JACoW Conference Papers" (MS Word edition). Authoritative templates live at https://www.jacow.org; individual conferences set page limits and submission method.

## Workflow

1. Identify the task: (a) format/restyle a draft, (b) audit an existing .docx, (c) reformat a reference list, (d) format the author/affiliation block.
2. Read only the reference file(s) the task needs:
   - Page, fonts, headings, figures, tables, equations, units, footnotes, style table -> `references/layout-and-styles.md`
   - Title, authors, affiliations, collaborations -> `references/authors-affiliations.md`
   - Reference list entries (proceedings, journals, arXiv, books, reports...) -> `references/references-ieee.md`
   - Journal abbreviation lookup -> `references/journal-abbreviations.md`
   - Final pre-submission pass -> `references/checklist.md`
3. For .docx input, run `python scripts/audit_jacow_docx.py paper.docx` first. It reports page size, margins, columns, fonts, font sizes, body justification, the 0.33 cm first-line indent, widow/orphan control, page-number fields and DOI hyperlinks. It cannot judge everything (caption placement, actual column-top/bottom stranded lines, text boxes), so still apply the checklist by eye.
4. When editing a .docx, also follow the `docx` skill (unzip/edit XML or docx-js). Prefer starting from the official JACoW template when the user can supply it: it already carries the correct styles and the footnote text box.
5. Report what was changed and list anything that needs the author's decision (missing DOIs, uncited references, ambiguous author order).

## Core spec at a glance

| Item | Rule |
|---|---|
| Page | 595 x 792 pt (20.99 x 27.94 cm); margins top/bottom 19 mm, left/right 20 mm |
| Body | Single spacing, 2 columns of 82.5 mm, 5.3 mm gutter, 10 pt Times New Roman, justified, first-line indent 0.33 cm |
| Fonts | Times/Times New Roman and Symbol only; Liberation Mono 8 pt for DOIs/URLs |
| Title | 14 pt bold UPPERCASE, centered, full page width (lowercase letters only where needed, e.g. Au, GeV, SwissFEL) |
| Authors | 12 pt upper/lowercase, centered, full page width |
| Section heading | 12 pt bold UPPERCASE, centered, not numbered |
| Subsection heading | 12 pt italic, Title Case, left aligned, not numbered |
| Third-level heading | 10 pt bold, run-in, Em Space after |
| Figure caption | below figure, 10 pt, "Figure N:" ; table caption above table |
| References | numbered in order of citation, 9 pt, line spacing exactly 10.4 pt, IEEE style |
| Footnotes | text box at bottom of column, 8 pt, never Word's footnote feature |
| Page numbers | none |

## Rules that are easy to get wrong

- Abstract: stand-alone, no citations, acronyms expanded on first use (also again in the main text).
- Never use Word's built-in footnotes; title/author footnotes use symbols (*, dagger, double dagger, section, pilcrow) and appear only at the bottom of column 1 on page 1. Body footnotes use 1, 2, 3 in the column where they are cited.
- Full-width figures/tables go at the top or bottom of a page, in their own continuous section (one-column) so text flow stays top-to-bottom.
- "Fig. 1" mid-sentence, "Figure 1" at sentence start; "Table 1" is never abbreviated; "Eq. (1)" mid-sentence, "Equation (1)" at start. Do not start a sentence with an abbreviation or number.
- Units upright, non-breaking space before the unit (3 keV), singular in hyphenated compound adjectives (3.8-metre long undulator).
- Citations: square brackets, ascending order, grouped [2, 3], ranges [1-3, 10]. Every reference must be cited.
- DOI hyperlink required (colour Blue, Accent 1, 25% darker, Liberation Mono 8 pt). Plain URLs are NOT hyperlinked and are used only when no DOI exists.
- Reference titles use sentence case; journal names use ISO 4 abbreviations; more than 6 authors -> "et al.".
- No column break between a heading and its paragraph; no single orphan/widow lines at column tops/bottoms.
- Conclusion precedes ACKNOWLEDGEMENTS, APPENDIX, REFERENCES. Appendices should generally be avoided.
- PDF: embed fonts ("Embed fonts in file" in Word Save options); if using Acrobat PDFMaker, enable "Add Links" so DOI links survive.

## Known quirks in the source guide

- List indentation appears as 0.3 cm in the text but 0.33 cm in Table 2; use 0.33 cm left / 0.36 cm hanging (the Table 2 value) unless the conference template says otherwise.
- The guide's own references use abbreviations such as "Phys. Rev. Accel. Beams"; always cross-check against `references/journal-abbreviations.md` or the ISO 4 sources it cites.
- If the official template and this skill disagree, the template for the specific conference wins.
