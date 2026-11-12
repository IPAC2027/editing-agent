# References in Appendix B's exact layout (`src/annexb`)

Every reference is rewritten in the exact layout of Appendix B of the JACoW style
guide (v2026-02-23): the same fields, in the same order, with the same words and
punctuation as Appendix B's own examples. This replaced the earlier engine (the
reference formatter's rewrite plus about fifty patching rules in `src/refcheck`),
which could correct punctuation but could not rebuild a reference into the layout.

## Two paths, one engine

| Source | What is changed | How |
|---|---|---|
| `\bibitem` (LaTeX) and Word | the reference's **text** | rewritten from Appendix B's template; LaTeX gets `\emph{Proc.\ IPAC'23}`, `\emph{journal}`, `vol.~114`, `\doi{…}`; Word gets a tracked change |
| `.bib` (biblatex) | the entry's **fields** | set so that `jacow.bbx` (`\documentclass[biblatex]{jacow}`) prints Appendix B's layout, checked by compiling with the class |

Both read a reference into the same fields, sort it into the same 16 kinds, and
normalise and complete it by the same steps. Every rewrite is the editor's decision
(suggest), with what changed and where each new value came from.

```
text or .bib entry
  └─ read into fields                 parse.py (text) / bib.py (BibTeX)
      └─ which of the 16 kinds        classify.py
          └─ JACoW's forms             engine.normalise: initials, sentence case, ISO 4 journal,
              │                          IPAC’23, Oct., Menlo Park, CA, USA
              └─ complete              complete.py: refs.jacow.org, JACoW conference list,
                  │                      Crossref, DataCite, abbrevIso, laboratories' places
                  └─ write              categories.py (text) / bib.target (fields for jacow.bbx)
```

## The 16 kinds (Appendix B's headings)

| # | Kind | Appendix B's example |
|---|---|---|
| 1 | Conference proceedings | A. Alpha and B. T. Beta, “An overview of modern control systems”, in Proc. ICALEPCS’23, Cape Town, South Africa, Oct. 2023, pp. 57-59. doi:10.18429/JACoW-ICALEPCS2023-PAPERID |
| 2 | Unpublished paper from a previous conference | A. Alpha, “An interesting talk but paper not submitted”, presented at IPAC’14, Dresden, Germany, Jun. 2014, paper MOP057, unpublished. |
| 3 | Paper at the current conference | …, presented at IPAC’25, Taipei, Taiwan, Jun. 2025, paper MOAB01, this conference. |
| 4 | Periodical | A. Alpha et al., “Low dose irradiation impact on modern silicon detectors”, Nucl. Instrum. Methods Phys. Res. A, vol. 773, pp. 1-7, 2015. doi:10.1016/j.nima.2014.11.022 |
| 5 | Accepted for publication | J. B. Good, “Title …”, Phys. Rev. Lett., to be published. |
| 6 | Submitted for publication | G. D. Read, “Title of paper”, submitted for publication. |
| 7 | arXiv preprint | A. Alpha, “Title of arXiv preprint”, Jan. 2025. doi:10.48550/arXiv.2501.10602 |
| 8 | Online source | EPICS, https://www.epics-controls.org |
| 9 | Book, or a chapter | A. Alpha, Title of Book. Cambridge, MA, USA: MIT Press, 1986. |
| 10 | Internal report | A. Alpha et al., “Title of report”, CERN, Geneva, Switzerland, Rep. CERN-2012-333, Oct. 2012. |
| 11 | Technical report | SLS-2 Conceptional Design Report, A. Streun, Ed., Paul Scherrer Institute, Villigen, Switzerland, Rep. 17-03, Dec. 2017. https://… |
| 12 | Thesis | A. Student, “Title of thesis”, Ph.D. thesis, Phys. Dept., Karlsruher Institut für Technologie, Karlsruhe, Germany, 2014. |
| 13 | Handbook | Motorola Semiconductor Handbook, Motorola Semiconductor Products Inc., Phoenix, AZ, USA, Nov. 2021, https://… |
| 14 | Reference, manual | IEEE Editorial Style Manual for Authors, IEEE Periodicals, Piscataway, NJ, USA, Mar. 2025. https://… |
| 15 | Patent | A. N. Inventor, “Title of patent”, U.S. Patent 9 123 456, Jan. 20, 2016. |
| 16 | Unpublished work, private communication | P. Neptune, “Title of paper”, unpublished. / P. Uranus, private communication, Jun. 2015. |

All 33 of Appendix B's examples are tests (`tests/data/annexb_examples.py`): each must be
read as its kind and come out exactly as printed. Three printed examples have typos the
layout itself rules out ("Aug.-Sep", "Aug", "May."); they are corrected there.

Each kind has the fields its layout cannot do without (`categories.CATEGORIES[...].required`).
One that no source could give is left out of the text and named on the card ("Pages
missing: Appendix B needs it and no source gave it"); nothing is invented. Words of the
reference that the layout has no room for (a proceedings volume, "IEEE Cat. No.", a
non-DOI web address after a DOI, "github") are left out and named too.

## Normalising

- **Authors** (Table 2): initials and family name ("Zampetakis, M." → "M. Zampetakis",
  "MJ Hogan" → "M. J. Hogan", "Andrey V. Mishin" → "A. V. Mishin"); one, two ("and"),
  three to six (", and"), more than six ("et al."); "et al." with six or fewer real
  authors is written out from the record.
- **Title**: in “…”, comma after the quote, sentence case with names and acronyms kept
  (the formatter's sentence case; possessives such as "Green's" keep their capital; with a
  local model, the words it is unsure of are decided word by word).
- **Journal**: ISO 4. Annex C first (full name, abbreviation, or the usual variants
  "PRAB", "Phys. Rev. ST Accel. Beams", "NIM A", "JINST"), then Annex C with a typo
  (small and unambiguous only), then abbrevIso (the ISO 4 tool Appendix B cites, [13]),
  then JabRef's lists, then the journal's short title in Crossref. Where Annex C as printed
  is not ISO 4 ("App. Phys. Lett." for "Appl. Phys. Lett.", "Phys. Plasma", "IEEE Trans.
  Magnetics", "J. Superconductivity", "Opt. Communic."), ISO 4 wins, since the guide makes
  ISO 4 mandatory (`journals.ANNEX_C_ERRATA`; delete a line to follow Annex C as printed).
- **Conference**: the label Appendix B uses ("IPAC 2021", "IPAC2021", "Linac’24", "PAC99",
  "6th International Particle Accelerator Conference" in 2015 → IPAC’15), in the short
  form "in Proc. IPAC’21".
- **Date, place, pages**: "Oct.", "Sep."; "Chicago, IL, USA" (a state written out becomes
  its code; "Sacramento, CA" gets "USA"); "pp. 57-59", "p. 050511".
- **DOI**: `doi:10.…`, last, in its registered capitals; checked, corrected, found (see the
  DOI section). An arXiv identifier gives the DOI, month and year.
- Cyrillic letters typed for Latin ones ("РАС2003", "рр.") are read as Latin.

## Completing

- **JACoW papers**: refs.jacow.org (JACoW's own reference database) gives the full author
  list, pages, place, month, paper ID and DOI; failing that, the JACoW conference list
  (311 conferences) gives place and month, and every paper since 2015 (and IPAC2014) has
  the DOI 10.18429/JACoW-<CONF><YEAR>-<ID>, checked with DataCite.
- **Journal articles**: the DOI's Crossref record gives volume, pages, year, a missing
  title, the full author list and the journal's short title.
- **Reports and theses**: the laboratory's place (CERN → Geneva, Switzerland; Fermilab →
  Batavia, IL, USA; `places.INSTITUTIONS`).
- A registry value fills a gap; it replaces the author's own only when the record is
  certainly the same paper (the DOI matched, or the title alike and the conference or
  journal the same), and the card says so: "pages corrected from refs.jacow.org: 861-865 →
  878-882".

## The local model reads; it never writes

When the rules cannot tell a reference's kind, cannot find its title or authors, or leave
words they cannot place, the local model (`LLM_ENABLED=true`, Ollama by default) is asked
one thing: which piece of the reference is which field, and which kind it is
(`reader.py`). Every value it gives must be copied exactly from the reference, checked
character by character; an answer that fails is sent back once with the reasons. The
fields then go through the same normalising, registries and template, so the text the
editor sees is always written by the template, never by the model. The model can point
at words; it cannot add one.

## BibTeX: what `jacow.bbx` needs

Checked by compiling one entry per kind with `\documentclass[biblatex]{jacow}`:

| Kind | Entry | Fields |
|---|---|---|
| conference | `@inproceedings` | booktitle = `Proc. IPAC'23`, **venue** = `City, Country`, **eventdate** = `2023-05`, pages, doi (else paper = ID). With `address`/`month` the date prints after the pages; `volume` prints after the proceedings |
| previous / current conference | `@atevent` / `@thisevent` | eventtitle = `IPAC'14`, venue, eventdate, paper |
| journal | `@article` | journal (or the entry's `journaltitle`) = ISO 4 (a differing `shortjournal` would print instead), volume, number, pages, date, doi |
| accepted / submitted | `@submittedto` / `@submitted` | journal / none |
| arXiv | `@article` with no journal | date = `2025-01`, doi = `10.48550/arXiv.<id>` |
| online | `@online` | title = `{{EPICS}}`, url, no date |
| book / chapter | `@book` / `@inbook` | edition as `titleaddon`; booktitle, editor |
| report | `@techreport` with a number, `@report` without (no lone "Rep.") | institution, address, number, date |
| thesis | `@phdthesis` / `@mastersthesis` | school = `{Dept., University}` |
| handbook / manual | `@manual` | title braced, organization, location, date |

`jacow.bbx` writes every title in sentence case, so the words that keep their capitals are
braced (`{Oak Ridge National Laboratory}`, `{SwissFEL}`); a title it already sentence-cases
correctly is left alone. It mis-prints run-together initials ("Holmes, J.A." → "J.
Holmes", "Kutsaev, SV" → "SV. Kutsaev"), Vancouver order and braced whole names, so such an
author list is rewritten "Holmes, J. A.". Three names and "and others" would print all
three before "et al.", so the entry keeps the first author and "others". Each changed entry
is one edit, kept as written apart from the fields that change. Known limits of
`jacow.bbx`: a technical report's title is quoted, a patent's day is not printed, an
article number such as P10008 gets no "p.". TeX Live's biber fails to unpack itself on
some Macs (`lipo`); `bib.render_with_jacow` then unpacks its arm64 binary into the cache,
and the desk's PDF builds (`latex_build`) use the same binary.

## On the desk

Preparing a paper writes `references.json`: one record per reference (a `\bibitem`, a
Word reference or a `.bib` entry) with the text as written, the Appendix B result, the
kind, what is missing, the problems, where values came from, and the ids of the edits
inside it. The desk's References tab shows each record as written beside its result, green
(rewritten, nothing missing), red (something only the editor or author can supply) or grey
(already right). The editor accepts, keeps, or writes the reference themselves
(`ReviewState.ref_texts`, which replaces the whole reference). `.bib` edits are decided
there too (ids `B…`); finishing writes `<name>_final.bib` and builds the PDF with it.

A `\bibitem` rewrite is one decision: narrower fixes inside the same reference (a DOI's
form, a page dash) are left out of the edit set, because the rewrite already contains them
and letting them win the overlap used to throw the rewrite away.

## Why references could not be fixed before, and where the limits are now

The earlier engine patched the author's text: about fifty rules each fixed one local
thing, and each fix went through a damage check (`check_rewrite`) that refused anything it
could not account for. That kept references safe, but:

1. **It could not rebuild a reference.** Moving the date before the pages, writing "in
   Proc. IPAC’21" for "Proceedings of IPAC 2021", turning "Phys. Rev. ST Accel. Beams 2,
   114202 (1999)" into "…, vol. 2, p. 114202, 1999": each needs the reference rewritten
   from its fields, which patches cannot do and the damage check often refused.
2. **It had no idea of the 16 kinds**, so it could not say what was missing (a
   conference's place and month, a report's institution).
3. **It did not complete a reference**: refs.jacow.org, the conference list and the DOI
   records were used to check, not to fill the layout.
4. **The model was asked to rewrite whole references**, and an answer such as
   "J. Qiang, …, 2018, (submitted…), 2025" could pass every check.

Measured on NAPAC'25 (2265 references as the authors wrote them, real registries, no
model): 152 (7%) were already exactly in Appendix B's layout. The new engine writes 1760
(78%) complete, with every field Appendix B requires:

| Kind | References | Complete |
|---|---|---|
| journal | 1061 | 94% |
| conference | 563 | 82% |
| online | 135 | 96% |
| arXiv | 66 | 88% |
| report | 123 | 33% |
| conference talk (past, current) | 64 | 52% |
| book / chapter | 66 | 11% |
| thesis | 17 | 18% |
| kind not read by the rules | 124 | — |

What is still missing, and why:

- **Facts no registry has.** A report's number, a book's publisher city (it changes with
  the edition, and most books have no DOI), a laboratory not in the list, a non-JACoW
  conference's place and month when it has no DOI. These are named for the editor;
  filling them would be inventing.
- **References the rules cannot read** (5%): no quotes, a title running into the journal,
  a missing quote mark, two references in one. The local model reads these, and the
  template writes them.
- **Mistakes in the reference itself**: a title that is not the paper's, a wrong year, an
  author list that disagrees with the record. The registry's value is shown; the editor
  decides.

BibTeX, NAPAC'25's 52 biblatex papers (1149 entries), offline: after the fields are set,
874 entries print exactly Appendix B's text when compiled with the JACoW class (80% of the
1093 that compile; one paper's `.bib` does not compile even as submitted).

## Where it is

| Module | Does |
|---|---|
| `src/annexb/categories.py` | the 16 kinds, their required fields, their templates (plain text and LaTeX) |
| `src/annexb/parse.py` | text → fields (masked reading: identifiers, title, authors, kind words, conference, numbers, place, date) |
| `src/annexb/names.py` | author lists in any form → initials and family names |
| `src/annexb/classify.py` | the kind; leftover words to the field the kind has room for |
| `src/annexb/journals.py` | ISO 4 journal names (Annex C, abbrevIso, JabRef, Crossref) |
| `src/annexb/conferences.py` | conference labels, the JACoW conference list, refs.jacow.org |
| `src/annexb/places.py` | countries, states, laboratories' places |
| `src/annexb/complete.py` | the registries (refs.jacow.org, Crossref, DataCite, DOI checks) |
| `src/annexb/reader.py` | the local model's reading, checked |
| `src/annexb/engine.py` | the path for one reference; what changed, what is missing |
| `src/annexb/bib.py` | BibTeX entries: read, fields for `jacow.bbx`, the edits, compiling to check |

`src/references.py` (`screen_reference`) is the adapter the Word path, the `\bibitem` path
and the desk's "Check a reference list" page call. `src/refcheck/doi.py` is kept and used
(below); the rest of `src/refcheck` (the patching rules) is no longer on any path.

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
  - DataCite's search of JACoW's prefix (10.18429);
  - for a DOI that does not exist (or is another paper's), its **near spellings**, what a
    web search would turn up: a dot left out (`PhysRevSTAB.2114202` →
    `PhysRevSTAB.2.114202`), a digit wrong, dropped or swapped against the reference's own
    volume, page and year, a mistyped prefix (`10.1130/PhysRev…` → `10.1103/…`), a doubled
    dot, a letter O for a zero. At most 24 are asked of doi.org, in parallel, and one is
    taken only if it exists and its record agrees with the reference (the title, or the
    volume and page, or the first author, year and volume or page) and no other near
    spelling fits as well. With nothing in the reference to check against (a bare DOI) the
    only near spelling that exists is offered as a possible DOI, never taken.
  - The volume and page are read after the journal's name with or without a title
    (`Phys. Rev. ST Accel. Beams 2, 114202 (1999)`), so a title-less journal reference can
    be checked too.
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

With near spellings, the volume and page read without a title, and Crossref paced (at most
5 requests a second, a "429 Too Many Requests" waited out and asked again):

| Case | Result |
|---|---|
| 260 references the editor gave a DOI | 150 found + 17 possible = 167 the editor's DOI (64%); 5 possible and 7 found differ; 81 none |
| 15 DOIs the editor corrected | unchanged: 9 the editor's DOI |
| 150 DOIs author and editor agree on | unchanged: 147 confirmed, 3 real errors corrected (`PhysRevSTAB.2114202` among them: the editor kept it) |
| 150 references with no DOI on either side | 45 found, 1 possible |

Before pacing, a fast run lost a dozen DOIs to Crossref's 429 answers without saying so.
