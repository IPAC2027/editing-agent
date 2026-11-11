# The JACoW reference rules

`src/refcheck` checks every reference in three stages: the **rules** find and
fix what they can, a **difficulty description** says what is left, why, and
who can fix it, and the **local model** fixes what is meant for it, with its
answer checked again by the rules and by `check_rewrite`. This page lists the
rules.

Sources: JACoW Annex B (the reference examples of the template), the JACoW
*Formatting references* and *DOIs for arXiv* pages
(ipac-docs.jacow.org/Paper/Writing/general/), and the Editor Quality Matrix
(ipac-docs.jacow.org/PaperEditing/Editing/TemplateReview/).

**Fix**:
- **auto**: a presentation change, applied without asking.
- **suggest**: changes content (moves, adds or removes words, or adds a value
  from a lookup), so the editor decides.
- **model**: needs judgement; the local model may fix it.
- **editor**: needs a fact nobody has, or a decision only the author can make.

Every fix, whoever makes it, must pass `check_rewrite` against the author's
text, told exactly what that fix may change.

## DOIs, arXiv, URLs

| Code | Rule | Fix |
|---|---|---|
| REF-DOI-URL | A DOI written as `https://doi.org/…` is written `doi:10.…` | auto |
| REF-DOI-FORM | `DOI: 10.…`, `doi 10.…`, `doi://10.…` or a bare `10.…` is written `doi:10.…` | auto |
| REF-DOI-TWICE | The same DOI given twice: the second goes | auto |
| REF-DOI-SEP | The DOI follows a full stop: `…, pp. 57-59. doi:…` | auto |
| REF-DOI-END | No full stop after the DOI | auto |
| REF-DOI-LAST | Something follows the DOI; the DOI comes last | model |
| REF-DOI-INCOMPLETE | A JACoW DOI with no paper ID (`10.18429/JACoW-HIAT2025`) | suggest with refs.jacow.org's DOI, else editor |
| REF-DOI-OTHER-CONF | The JACoW DOI names another conference than the text (HIAT'25 with an IPAC'24 DOI) | editor |
| REF-DOI-FORM (spelling) | What clings to a DOI goes: `\vskip3mm`, a trailing `\\` or `:`, `,journal`, `%2F`; `10,1103/…` is `10.1103/…` | auto |
| REF-DOI-WRONG | The DOI does not exist (`10.1103/PhysRevSTAB.2114202`, `10.1080/00295450.2021`), or is another paper's, and a registry gives the right one for this reference (`src/refcheck/doi.py`) | suggest, with the reason and source |
| REF-DOI-POSSIBLE | No DOI fits strictly, but a looser search's closest record does (titles 75% alike, at most one difference): offered as "Possible DOI, check it", with what differs and any other close records | suggest, never automatic |
| REF-DOI-UNRESOLVED | The DOI does not exist, or is another paper's, and no registry gives one that fits | editor |
| REF-DOI-MISSING | No DOI, and a lookup verified one; it takes the place of a web address. Never for a talk, a manuscript or a private communication; a JACoW DOI only if it names the conference the text names; an arXiv DOI only for a paper cited as arXiv | suggest, source named |
| REF-ARXIV-DOI | An arXiv paper gets `doi:10.48550/arXiv.<id>` (derived from the identifier, version dropped) | suggest |
| REF-ARXIV-URL | `https://arxiv.org/abs/<id>` is written `arXiv:<id>` | suggest |
| REF-ARXIV-PREPRINT | "arXiv preprint arXiv:…" is written "arXiv:…" | suggest |
| REF-URL-ONLINE | "[Online]. Available:" is not written | auto |
| REF-URL-DOI | A web address that repeats a DOI given elsewhere goes; a web address that holds the only DOI (`https://link.aps.org/doi/10.1103/…`) becomes `doi:10.1103/…` | auto / suggest |
| REF-URL-JACOW | A JACoW paper's PDF address: removed when there is a DOI, else replaced by its paper ID (`paper TU6RFP048`) | auto / suggest |
| REF-PAPER-ID | With a JACoW DOI, "paper …" is not given | suggest |

## Authors

| Code | Rule | Fix |
|---|---|---|
| REF-ETAL | "et al", "et. al." is written "et al." | auto |
| REF-ETAL-COMMA | No comma before "et al." after one name; a comma after several | auto |
| REF-AUTH-INITIALS | Spaced initials: `P. N. Ostroumov` | auto |
| REF-AUTH-INITIAL | An initial written with a comma or no full stop (`Y, Momozaki`) | suggest |
| REF-AUTH-ORDER | Initials first: `T. Boltz`, not `Boltz, T.` or `Alamprese H.` | suggest |
| REF-AUTH-GIVEN | Initials, not first names: `J. Gonzalez`, not `Javier Gonzalez` | suggest |
| REF-AUTH-AND | Two names: "A and B"; three to six: "A, B, and C"; "and", not "&" | auto |
| REF-AUTH-MANY | More than six authors: the first, then "et al." | suggest |
| REF-AUTH-FORM | The author list is mixed with something else (a year) | model |

The author rules act only when every name in the list looks like a person's
name. A book title or a year among the "authors" stops them, so the list is
never cut down by mistake.

## Title

| Code | Rule | Fix |
|---|---|---|
| REF-TITLE-QUOTES | Curly quotes around the title | auto |
| REF-TITLE-COMMA | The comma after the closing quote; no full stop ending the title; a comma between authors and title | auto |
| REF-TITLE-CAPS / REF-TITLE-CASE | Sentence case: first word, names and acronyms capitalised | suggest when the formatter's sentence case decides every word, else model (word-by-word labels, unanimous) |
| REF-TITLE-NAME | A name keeps its capital (`Gaussian`, `Hamiltonians`) | suggest |
| REF-TITLE-MISSING | No title in quotes where Annex B quotes one (not books or web pages) | model |
| REF-TITLE-NAMES | The quoted "title" holds author names (a garbled rewrite) | model |
| REF-TITLE-HYPHEN | A hyphen left from a line break, with a space after it ("multi- charge") | auto |

## Proceedings

| Code | Rule | Fix |
|---|---|---|
| REF-PROC-FORM | "in Proc. …", not "Proceedings of …" or "Proc. of"; "in" before "Proc."; a JACoW paper named only by its conference gets "in Proc."; a talk is "presented at" a conference, not its proceedings | auto / suggest |
| REF-PROC-LABEL | The conference as JACoW names it: `IPAC'21`, `PAC'09`, `HIAT'25`, not `IPAC2021`, `PAC09`, `HIAT 2025` | auto |
| REF-PROC-NAME | A JACoW paper whose DOI names its conference, written with the long name only: the author's name stays, with "in Proc." and the label added — "in Proc. 12th Int. Particle Acc. Conf. (IPAC’21)", as in Annex B's "(ICAP'18)" | suggest, else model |
| REF-PLACE | A US state written out before "USA" is its postal code (`Newport News, VA, USA`) | suggest |
| REF-PROC-YEAR | The conference's year and the date disagree (`PAC'09`, `May 2010`) | editor |
| REF-MONTH | `Jan.`, `Feb.`, `Mar.`, `Apr.`, `May`, `Jun.`, `Jul.`, `Aug.`, `Sep.`, `Oct.`, `Nov.`, `Dec.`; no comma before the year | auto |
| REF-PAGES | `pp.` for a range, `p.` for one article number; `pp,` is `pp.`; an article number without a space | auto |
| REF-PAGES-RANGE | `pp. 1656` gives one page where a range belongs | suggest with a verified range, else editor |
| REF-PAGES-MISSING | A published JACoW paper, or a journal article, with no pages | suggest with a verified value, else editor |

## Journals

| Code | Rule | Fix |
|---|---|---|
| REF-JOURNAL | JACoW's own abbreviation from Annex C first (`Nucl. Instrum. Methods Phys. Res. A`, `Phys. Rev. Accel. Beams`, `Nat. Photonics`; 158 journals, `src/knowledge/…/journal-abbreviations.md`), else ISO 4 (`Opt. Commun.`); abbreviated words end with a full stop (`Sci. Rep.`); no "in" before the journal | auto / suggest |
| REF-JOURNAL-LAYOUT | "Journal, vol. V, no. N, p. P, Year", not "Journal V, P (Year)" or "16(10):T10002" | suggest |
| REF-JOURNAL-ORDER | Pages before the year | suggest |
| REF-VOLUME | `vol.` and `no.`, with a comma before `vol.` | auto |
| REF-VOLUME-MISSING | A journal article with no volume | suggest with a verified value, else editor |
| REF-YEAR / REF-YEAR-MISSING | The year without brackets; a journal article gives its year | auto / editor |
| REF-FACT-PAGES / REF-FACT-VOLUME | The pages or volume disagree with the record of the reference's own DOI | editor |
| REF-STATUS | "Accepted …" is "to be published"; "in preparation" is not an Annex B status | suggest / editor |

## Everything else

| Code | Rule | Fix |
|---|---|---|
| REF-LATEX | A LaTeX command left in the reference | model |
| REF-LOOKALIKE | Cyrillic letters that look Latin, from copying out of a PDF (`Proc. РАС'О3, рр. 470` → `Proc. PAC'03, pp. 470`) | auto |
| REF-PUNCT | Stray spaces and doubled punctuation | auto |
| REF-REPEATED | The same word twice in a row ("May, May 1996") | auto |
| REF-END | A full stop at the end, except after a DOI or URL | auto |

## What the editor sees

- **A correction card** for each reference changed. The message lists what was
  fixed and by whom (the rules, a lookup with its source, or the local model).
- **REF-CHECK-01** when something is still wrong: one bullet per problem, with
  why it was not fixed and what would settle it, and the difficulty (low:
  layout; medium: judgement; high: a fact or a decision).

The same description, in full, is what the local model is given:
- the problems meant for it;
- the JACoW layout for that kind of reference, and Annex B's own example;
- the verified facts it may use.

## One standard

References follow Annex B in every conference. How strictly it is applied is each
editor's decision: presentation fixes are automatic, everything else is a card the
editor accepts or rejects. The conference label's apostrophe (`IPAC’23`) follows the
desk's house style, as the formatter's does.

## Measured on NAPAC'25

There are 2265 references from 216 papers, each the author's original paired with the
editors' final version (`NAPAC2025/<code>/original` and `current`). Counting single
edits (a word or a punctuation mark changed, added or removed), offline:

| | Editors' edits also made | Edits also made by an editor |
|---|---|---|
| Formatter only (before) | 13.3% | 26.1% |
| Formatter + rules (now) | 26.0% | 30.5% |

About 19% of the editors' edits add facts the author's text does not have (pages, a
volume, a DOI, a month, a place). Those come from refs.jacow.org and Crossref through the
lookups, not from the rules.

Many of the rules' edits that no editor made are Annex B corrections NAPAC's editors did
not enforce: ISO 4 journal names, spaced initials, arXiv DOIs, `“Title”,`.

With lookups on (a random 400 of the pairs), the editors' edits also made rise from 30.8%
to 31.7%, and about 28 more of the editors' added facts are reproduced. The share of our
edits an editor also made falls from 33.6% to 26.2%. That is mostly verified values the
editors did not bother to add (DOIs, months, issue numbers), not errors.

## DOIs: found, checked, corrected

`src/refcheck/doi.py` runs on every reference; lookups are always on (only the test
suite turns them off).
- **Spelling.** What clings to a DOI is removed first, with no lookup.
- **The author's DOI.** It is looked up in Crossref, then DataCite (JACoW and arXiv), then
  doi.org. A DOI that does not exist, or whose record has another title or first author,
  is wrong.
- **The right DOI.** A wrong or missing DOI is looked for by what the reference says:
  - a JACoW DOI built from the reference's conference and paper ID, checked with DataCite;
  - Crossref's bibliographic search;
  - DataCite's search of JACoW's prefix (10.18429).
- **Taking a DOI.** It is taken only when the record agrees on the title (85%, 95% for short
  titles), the first author, the year (±1), and the volume and first page when both give
  them. A journal article is never given a conference paper's DOI, nor the reverse. Two
  records that fit equally (two editions of a book) give no DOI.
- **No answer.** A failed lookup changes nothing.
- **The editor's view.** The card says why the cited DOI was wrong ("does not exist, a typo",
  "another paper's") and where the right one came from. A DOI the formatter's own lookup
  added must pass the same check, or the formatter's rewrite is not used.

Measured on NAPAC'25 with the real registries:

| Case | Result |
|---|---|
| 260 references the editor gave a DOI | 146 the same DOI (56%), 107 none, 7 a different one. Most of those 7 are the editor's slips: a stray `\_`, an unrelated paper, the wrong edition |
| 15 DOIs the editor corrected | 6 corrected to the editor's DOI, 7 flagged as wrong or nonexistent for the editor, 2 missed |
| 150 DOIs author and editor agree on | 147 confirmed; 3 corrected, all real errors both missed (`JACoW-IPAC25-…` does not exist, `JACoW-IPAC2025-…` does) |
| 150 references with no DOI on either side | 43 DOIs added, all in the sample checked correct |

With the looser search added (a possible DOI is always the editor's decision):

| Case | Result |
|---|---|
| 260 references the editor gave a DOI | 146 found + 16 possible = 162 the editor's DOI (62%); 7 possible and 7 found differ; 84 none |
| 15 DOIs the editor corrected | 6 corrected + 3 possible = 9 the editor's DOI; 4 flagged for the editor; 2 missed |
| 150 DOIs author and editor agree on | unchanged: 147 confirmed, 3 real errors corrected |
| 150 references with no DOI on either side | 44 found, 1 possible |
