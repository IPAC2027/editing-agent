# JACoW Reference Rules for AI Agents (Annex B)

Source: *JACoW MS Word Style Guide*, **ANNEX B** (IEEE reference style as applied to JACoW papers).  
This file is intended as an **agent-operational rule set** for linting and minimally correcting references.

---

## 0) Scope and non-goals

**In scope**
- Linting and fixing **reference-list entries** and **in-text citations** to conform with JACoW’s Annex B rules.

**Out of scope**
- Inventing missing bibliographic metadata (authors, year, pages, DOI, etc.).  
  If metadata is missing, the agent should **flag** the entry and (optionally) request a lookup step.

---

## 1) Global requirements

### 1.1 References section and numbering
- References must be **numbered** and appear in a section titled **REFERENCES**.
- In-text citations must be in **square brackets** (e.g., `[2]`).
- In-text citation numbers must appear in **ascending order**.
- Multiple citations must appear **in the same bracket**: `[3, 4]`.
- Ranges use hyphen: `[1-4, 10]`.

### 1.2 Fonts, sizing, and spacing (Word-oriented)
- Reference entries: **Times New Roman, 9 pt**.
- DOI and URL strings: **Liberation Mono, 8 pt** (monospaced).
- Reference line spacing: **exactly 10.4 pt** (not “single”).

### 1.3 DOI / URL policy
- If a DOI exists, it should be appended at the end as: `doi:<DOI>`.
- DOI should remain **on one line** (do not break it across lines).
- A hyperlink to the DOI is **encouraged** (Word/PDF workflow note: “Add Links” must be enabled when generating PDF).
- A URL may be included if no DOI is available; **do not add a hyperlink** for the URL.

### 1.4 Hanging indent and alignment
- References use a **hanging indent** layout so the bracketed reference number aligns and subsequent lines indent.
- Indentation values depend on whether references in a column exceed single digits:

**If number of references in a column ≤ 9**
- Left indent: 0.00 cm
- Hanging indent: 0.52 cm

**If number of references in a column ≥ 10**
- Refs. 1–9: left indent 0.16 cm; hanging indent 0.52 cm
- Refs. 10+: left indent 0.00 cm; hanging indent 0.68 cm

---

## 2) Author and title formatting

### 2.1 Author list punctuation rules
- Pay attention to commas and “and”.
- For **three or more authors**, include a comma after the penultimate author.
- **et al.** is preferred when the number of authors is **greater than six**.

**Canonical author formats**
- 1 author: `A. T. Alpha,`
- 2 authors: `A. T. Alpha and B. Beta,`
- 3–6 authors: `A. T. Alpha, B. Beta, and J.-P. Gamma,`
- >6 authors: `A. T. Alpha et al.,`
- >6 but two primary authors emphasized: `A. T. Alpha, B. Beta, et al.,`

### 2.2 Paper title case
- Paper titles in references are written in **sentence case**:
  - Only the first word is capitalized by default.
  - Proper nouns and acronyms keep capitals.


### 2.3 Abbrieviation rule
- Use https://github.com/marcinwrochna/abbrevIso to retract correct abbrievation for each journal.
---

## 3) Reference-type templates (Annex B)

> Agents should: (a) classify the reference type; (b) validate required fields; (c) format to the template; (d) append DOI/URL rules.

### 3.1 Paper published in conference proceedings (JACoW)
**Template**
`[n] <Authors>, “<paper title in sentence case>”, in <Proc. CONF’YY>, <City>, <Country>, <Mon. YYYY>, pp. <pp-pp>. doi:<DOI>`

**Rules**
- Proceedings title: **title case in italics** with standard abbreviations (e.g., `in Proc. IPAC’24`).
- Include venue location and month/year.
- Page numbers are **mandatory**.
- DOI is strongly emphasized; paper ID may be included if no DOI exists.

### 3.2 Unpublished paper from a previous conference (talk given, not published)
**Template**
`[n] <Authors>, “<talk title>”, presented at <CONF’YY>, <City>, <Country>, <Mon. YYYY>, paper <ID>, unpublished.`

**Rules**
- Conference name appears in **normal** font (not “in Proc.”).

### 3.3 Paper presented at the current conference
**Template**
`[n] <Authors>, “<talk title>”, presented at <CONF’YY>, <City>, <Country>, <Mon. YYYY>, paper <ID>, this conference.`

### 3.4 Published in a periodical (journal)
**Template**
`[n] <Authors>, “<paper title in sentence case>”, <Journal Abbrev.>, vol. <V>, no. <N>, p./pp. <page or article>, <Mon. YYYY>. doi:<DOI>`

**Rules**
- If journals are paginated by volume, issue number is **not mandatory**.
- Month of publication is optional.
- Use **ISO 4** abbreviations for journal titles.

### 3.5 Accepted for publication
**Template**
`[n] <Authors>, “<paper title>”, <Journal Abbrev.>, to be published.`

### 3.6 Submitted for publication
**Template**
`[n] <Authors>, “<paper title>”, submitted for publication.`  
**Rule**: Periodical name does **not** appear.

### 3.7 arXiv preprint
**Template**
`[n] <Authors>, “<preprint title>”, <Mon. YYYY>, arXiv:<id> [<category>]. doi:<DOI-if-provided>`

### 3.8 Online source
**Template**
`[n] <Org/Project>, <URL>`

**Rule**: URL should not be hyperlinked; monospaced font is used for URL.

### 3.9 Chapter in a book
**Template**
`[n] <Authors>, “<chapter title>”, in <Book Title>, <Editor>, Ed. <City>, <State>, <Country>: <Publisher>, <Year>, pp. <pp-pp>.`

### 3.10 Book
**Template**
`[n] <Author>, <Book Title>. <City>, <State>, <Country>: <Publisher>, <Year>.`

### 3.11 Internal report
**Template**
`[n] <Authors>, “<report title>”, <Institution>, <City>, <Country>, Rep. <Report-No.>, <Mon. YYYY>.`

### 3.12 Technical report (possibly with editor)
**Template**
`[n] <Authors>, <Report Title>, <Editor>, Ed., <Institution>, <City>, <Country>, Rep. <Report-No.>, <Mon. YYYY>, <URL-if-any>`

### 3.13 Thesis
**Template**
`[n] <Author>, “<thesis title>”, Ph.D. thesis, <Dept.>, <University>, <City>, <Country>, <Year>.`

### 3.14 Handbook
**Template**
`[n] <Handbook Name>, <Edition>, <Company>, <Country>, <Mon. YYYY>, pp. <pp-pp>, <URL>`

### 3.15 Manual
**Template**
`[n] <Manual Title>, <Organization>, <City>, <State>, <Country>, <Mon. YYYY>, pp. <pp-pp>, <URL>`

### 3.16 Patent
**Template**
`[n] <Inventor>, “<patent title>”, <Patent Authority and No.>, <Mon. DD, YYYY>.`

### 3.17 Unpublished work and private communication
- Unpublished:
  - `[n] <Author>, “<title>”, unpublished.`
- Private communication:
  - `[n] <Author>, private communication, <Mon. YYYY>.`

---

## 4) Linter checks (agent-operational)

### 4.1 Structural checks
- **REF-SEC-01**: References section exists and is titled `REFERENCES`.
- **REF-NUM-01**: Each reference entry begins with `[\d+]`.
- **REF-NUM-02**: Reference numbers are consecutive, starting at 1.
- **CITE-TEXT-01**: In-text citations use square brackets.
- **CITE-TEXT-02**: In-text citation numbers are ascending through the manuscript.
- **CITE-LINK-01**: Every in-text citation has a corresponding reference entry; no orphans.
- **CITE-LINK-02**: Every reference entry is cited at least once (optional warning).

### 4.2 Content completeness checks (by type)
- **PROC-REQ-01**: Proceedings ref must include `in Proc.` + conference acronym/year.
- **PROC-REQ-02**: Proceedings ref must include location + month/year.
- **PROC-REQ-03**: Proceedings ref must include page numbers.
- **DOI-REQ-01**: If DOI is known/present in source, append `doi:` at end.
- **DOI-FMT-01**: DOI must be single-line; no whitespace inside.
- **URL-RULE-01**: If URL used, ensure not hyperlinked.

### 4.3 Formatting checks
- **AUTH-01**: Penultimate comma for ≥3 authors.
- **AUTH-02**: Use `et al.` when authors > 6.
- **TITLE-01**: Paper title is sentence case (heuristic check; flag if obviously Title Case).
- **LAYOUT-01**: Hanging indent scheme matches reference-count regime (≤9 vs ≥10).
- **FONT-01**: DOI/URL rendered monospaced (Word style-level check, if available).
- **SPACE-01**: References use exactly 10.4 pt line spacing (Word style-level check, if available).

---

## 5) Safe auto-fixes vs. human-required actions

### 5.1 Safe auto-fixes (apply automatically)
- Normalize citation bracket formatting: `(... [ 3 ])` → `...[3]`.
- Merge adjacent citations into one bracket if syntactically safe: `[3][4]` → `[3, 4]`.
- Ensure consistent `doi:` prefix casing and colon: `DOI 10.x` → `doi:10.x`.
- Strip hyperlink formatting from URLs; keep visible URL text.
- Normalize spacing around commas in multi-citations: `[3,4]` → `[3, 4]`.

### 5.2 Human-required actions (never invent)
- Adding missing authors, year, pages, venue, report numbers, DOI, arXiv ID, etc.
- Choosing between multiple plausible matches.
- Converting a non-standard citation to a different publication without evidence.

---

## 6) Minimal data model for agents

Agents should convert each reference to structured fields before formatting:

```json
{
  "n": 12,
  "type": "proceedings|journal|arxiv|book|chapter|report|thesis|online|patent|unpublished|private_comm",
  "authors": ["A. Alpha", "B. Beta"],
  "title": "…",
  "container_title": "Proc. IPAC’23",
  "journal_abbrev": "Phys. Rev. Lett.",
  "venue_location": "Venice, Italy",
  "date": "May 2023",
  "volume": "114",
  "issue": "5",
  "pages": "57-59",
  "article_number": "050511",
  "report_number": "CERN-2012-333",
  "publisher": "Wiley",
  "city": "New York, NY, USA",
  "doi": "10.18429/JACoW-…",
  "url": "https://…",
  "paper_id": "MOAB01",
  "notes": ["unpublished", "this conference"]
}
```

---

## 7) Practical implementation notes (Word pipeline)

- Use a Word-aware parser to detect hyperlinks and remove them for URLs while preserving text.
- Treat DOIs as atomic tokens; enforce “no line breaks” by non-breaking formatting or post-layout checks.
- When renumbering references, update both reference list and in-text citations deterministically.

---

## 8) Source pointer

These rules are extracted from **ANNEX B** of the JACoW MS Word Style Guide (IEEE reference style as applied to JACoW).  
