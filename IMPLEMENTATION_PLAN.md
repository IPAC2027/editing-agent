# JACoW Conference Paper AI Agent — Implementation Plan

## 1. Goal

Replace or assist a JACoW/IPAC paper editor with an agentic tool that:

1. **Pre-screens each submitted paper automatically** and writes all findings plus a corrected source file into a per-paper `aiagent_prescreen/` subfolder.
2. **Operates fully offline** with a local LLM (Ollama / LM Studio) or with commercial APIs (OpenAI, Anthropic, etc.) via a common OpenAI-compatible interface.
3. Gives the editor a **traffic-light summary** (green / yellow / red) and a structured diff so they can accept or reject each suggestion individually.

---

## 2. Submission Folder Convention

```
<PaperID>-revision-<N>_author/
├── Source_Files/          # .tex (required)
├── Supporting_files_for_papers/   # images (.png, .jpg, .pdf)
├── PDF/                   # compiled PDF
└── BibTeX_file_only_for_LaTeX_papers/   # .bib  (optional)
```

Output written alongside the above:

```
<PaperID>-revision-<N>_author/
└── aiagent_prescreen/
    ├── report.json        # machine-readable findings
    ├── report.md          # human-readable findings (Markdown, editor-friendly)
    ├── <PaperID>_edited.tex   # source with safe auto-fixes applied
    ├── changes.patch      # unified diff vs. original .tex
    └── llm_suggestions.md # LLM-generated hints for human-required items
```

---

## 3. Priority-1 — Reference Checks and Corrections

This is the **most important** module. Errors here affect every reader.

### 3.1 In-text citation checks

| Check ID      | Description |
|---------------|-------------|
| CITE-ORDER-01 | Citation numbers must appear in **ascending order** through the paper body. First occurrence of a new key must be ≥ highest seen so far. |
| CITE-BRACKET-01 | Multiple adjacent cites must be merged: `[1][2]` → `[1, 2]`. |
| CITE-BRACKET-02 | Ranges must use hyphen: `[1, 2, 3, 4]` → `[1–4]`. |
| CITE-SPACE-01 | Normalize spaces inside brackets: `[ 3 ]` → `[3]`. |
| CITE-LINK-01 | Every `\cite{key}` must map to a bibliography entry. |
| CITE-LINK-02 | Every bibliography entry must be cited at least once (warning). |

### 3.2 Reference-list structural checks

| Check ID      | Description |
|---------------|-------------|
| REF-SEC-01    | A section titled `REFERENCES` must exist. |
| REF-NUM-01    | Each entry must begin with `[n]`. |
| REF-NUM-02    | Numbers must be consecutive starting at 1. |
| REF-NUM-03    | When re-ordering, renumber both the list and all in-text citations atomically. |

### 3.3 Reference-entry format checks (per Annex B)

Each entry is first **classified** (proceedings, journal, arXiv, book, thesis, online …) then validated against its template:

| Check ID      | Description |
|---------------|-------------|
| AUTH-01       | ≥3 authors require a penultimate comma. |
| AUTH-02       | >6 authors → use `et al.` |
| AUTH-FMT-01   | Author initials before surname: `A. T. Alpha`. |
| TITLE-01      | Paper titles must be **sentence case** (first word + proper nouns capitalised). Flag if obviously Title Case. |
| PROC-REQ-01   | Proceedings ref must include `in Proc. CONF'YY`. |
| PROC-REQ-02   | Must include venue city, country, month/year. |
| PROC-REQ-03   | Must include page numbers `pp. XX–YY`. |
| JOUR-REQ-01   | Journal ref must have volume, optional issue, pages/article number. |
| DOI-REQ-01    | If a DOI is present/known, it must be appended as `doi:10.xxxxx`. |
| DOI-FMT-01    | DOI must be a single token (no whitespace). |
| URL-RULE-01   | URLs must not be hyperlinked; use monospaced font cue in source. |
| ABBR-01       | Journal names should use ISO 4 abbreviations (flag if spelled out). |

### 3.4 Safe auto-fixes (applied automatically, no LLM needed)

- Normalise citation brackets and spacing.
- Merge consecutive single-key cites into one bracket.
- Fix `DOI 10.x` / `doi 10.x` → `doi:10.x`.
- Normalise `et al.` capitalisation/punctuation.
- Trim trailing/leading whitespace from reference entries.

### 3.5 LLM-assisted suggestions (written to `llm_suggestions.md`, never auto-applied)

- Suggest correct DOI for a reference where it's missing (via CrossRef API lookup, then LLM confirmation).
- Suggest corrected sentence-case title.
- Suggest correct ISO 4 journal abbreviation.
- Flag and propose fix for clearly wrong venue/year/pages.

---

## 4. Priority-2 — Formatting Checks

### 4.1 Title

| Check ID      | Description |
|---------------|-------------|
| FMT-TITLE-01  | Paper title must be ALL CAPS in the JACoW `\title{}` block (JACoW template renders it in all-caps, but the source must also be all-caps). |
| FMT-TITLE-02  | No trailing punctuation on the title. |
| FMT-TITLE-03  | Footnotes in title (`\thanks{}`) must be present if funding acknowledgement is needed. |

### 4.2 Authors

| Check ID      | Description |
|---------------|-------------|
| FMT-AUTH-01   | Author name format in `\author{}`: First/Middle initials then surname. |
| FMT-AUTH-02   | `\thanks{}` email footnote should be on the corresponding author only. |
| FMT-AUTH-03   | Affiliation format: `Institution, City, Country`. |

### 4.3 Figures

| Check ID      | Description |
|---------------|-------------|
| FMT-FIG-01    | Figures must be referenced in text before they appear (`\ref{fig:X}` or `Fig. N`). |
| FMT-FIG-02    | Figure numbers must be sequential starting at 1. |
| FMT-FIG-03    | Caption format: `Figure N: <sentence case description ending with period>`. |
| FMT-FIG-04    | All figures referenced in text must have a corresponding `\label{}` in a `figure` environment. |

### 4.4 Tables

| Check ID      | Description |
|---------------|-------------|
| FMT-TBL-01    | Tables must be referenced in text before they appear. |
| FMT-TBL-02    | Table numbers sequential starting at 1. |
| FMT-TBL-03    | Caption format: `Table N: <description>` (caption **above** table in JACoW style). |
| FMT-TBL-04    | Column headers should be centred/capitalised per template. |

### 4.5 Number–Unit formatting

| Check ID      | Description |
|---------------|-------------|
| FMT-UNIT-01   | A non-breaking space (`~` in LaTeX) must separate a number from its unit: `10~MeV`, not `10MeV` or `10 MeV`. |
| FMT-UNIT-02   | SI unit abbreviations must be correct (case-sensitive): `MHz` not `mhz`, `eV` not `ev`. |
| FMT-UNIT-03   | Ranges: `10–100~MeV` with en-dash, not hyphen. |

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI  (Typer)                         │
│   prescreen  |  prescreen-all  |  report  |  export-skills  │
└────────────────────────┬────────────────────────────────────┘
                         │
          ┌──────────────▼───────────────┐
          │     Workflow Orchestrator     │
          │   src/workflow/prescreen.py   │
          └──┬──────────┬────────────────┘
             │          │
   ┌──────────▼──┐  ┌───▼──────────┐
   │   Parser    │  │  Check Engine │
   │  src/parser │  │  src/checks   │
   │  ─────────  │  │  ──────────── │
   │ latex_parser│  │ reference_    │
   │ bib_parser  │  │   checks.py   │
   └──────────┬──┘  │ formatting_   │
              │     │   checks.py   │
              │     └───────┬───────┘
              │             │
         ┌────▼─────────────▼────┐
         │      Data Models       │
         │  src/models.py         │
         │  (Pydantic)            │
         └────────────┬──────────┘
                      │
          ┌───────────▼───────────┐
          │     Auto-Fix Engine   │
          │  src/autofix/         │
          │  safe_fixes.py        │
          └───────────┬───────────┘
                      │
          ┌───────────▼───────────┐
          │      LLM Client       │
          │  src/llm/client.py    │  ←── local (Ollama) or
          │  src/llm/prompts.py   │      commercial (OpenAI API)
          └───────────┬───────────┘
                      │
          ┌───────────▼───────────┐
          │     Output Writer     │
          │  src/output/          │
          │  report.py  diff.py   │
          └───────────────────────┘
```

### 5.1 Key design decisions

- **LLM abstraction**: All LLM calls go through `src/llm/client.py` which speaks the OpenAI REST API (`/v1/chat/completions`). Set `LLM_BASE_URL=http://localhost:11434/v1` for Ollama, or `LLM_BASE_URL=https://api.openai.com/v1` for OpenAI. Model name is configured via `LLM_MODEL`.
- **Deterministic first**: The check engine is purely regex/AST-based. The LLM is only invoked for human-required suggestions. This makes the tool fast, reproducible, and usable without any API key.
- **Safe-fix discipline**: Only the fixes listed in §3.4 are applied automatically. All other changes are written to `llm_suggestions.md` for the editor to approve.
- **LaTeX source is the ground truth**: The `.tex` file is parsed and modified. The PDF is only used for page-size and font-embedding checks (Phase 4).

---

## 6. Package Structure

```
aiagent/
├── main.py                        # CLI entry point (Typer)
├── pyproject.toml
├── IMPLEMENTATION_PLAN.md
├── jacow_reference_rules_appendixB.md
├── src/
│   ├── __init__.py
│   ├── models.py                  # Pydantic models: Finding, Reference, Paper
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── latex_parser.py        # Parse .tex → Paper model
│   │   └── bib_parser.py          # Parse .bib → list[Reference]
│   ├── checks/
│   │   ├── __init__.py
│   │   ├── reference_checks.py    # All Priority-1 checks
│   │   └── formatting_checks.py   # All Priority-2 checks
│   ├── autofix/
│   │   ├── __init__.py
│   │   └── safe_fixes.py          # Safe deterministic fixes on .tex source
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py              # OpenAI-compatible LLM backend
│   │   └── prompts.py             # Prompt templates per check type
│   ├── workflow/
│   │   ├── __init__.py
│   │   └── prescreen.py           # End-to-end prescreen for one paper folder
│   └── output/
│       ├── __init__.py
│       ├── report.py              # Write report.json and report.md
│       └── diff.py                # Write changes.patch (unified diff)
└── paper_examples/                # Sample submissions for development/testing
    ├── MOP019-revision-27544_author/
    └── FRAD03-revision-27519_author/
```

---

## 7. Data Models (Pydantic)

```python
class Severity(str, Enum):
    ERROR   = "error"    # must fix before acceptance
    WARNING = "warning"  # should fix, editor decides
    INFO    = "info"     # FYI, no action required

class Finding(BaseModel):
    check_id: str           # e.g. "CITE-ORDER-01"
    severity: Severity
    line:     int | None    # source line number
    original: str | None    # original text snippet
    suggested: str | None   # suggested replacement (safe-fix or LLM)
    message:  str           # human-readable explanation
    auto_fixed: bool = False

class Reference(BaseModel):
    n:              int
    key:            str         # BibTeX key or [n] label
    ref_type:       str         # proceedings|journal|arxiv|...
    authors:        list[str]
    title:          str
    container_title: str | None
    venue_location: str | None
    date:           str | None
    volume:         str | None
    issue:          str | None
    pages:          str | None
    doi:            str | None
    url:            str | None
    paper_id:       str | None
    notes:          list[str]
    raw_text:       str         # original formatted string

class Paper(BaseModel):
    paper_id:       str
    source_path:    Path
    title:          str
    authors:        list[str]
    references:     list[Reference]
    citation_order: list[str]   # BibTeX keys in order of first appearance
    findings:       list[Finding] = []
```

---

## 8. Phased Roadmap

### Phase 1 — MVP (deterministic, no LLM required) ✦ highest ROI

- [ ] `src/parser/latex_parser.py`: extract citations, bibitem/bibliography, title, authors, figure labels, table labels.
- [ ] `src/parser/bib_parser.py`: parse `.bib` into `Reference` objects.
- [ ] `src/checks/reference_checks.py`: CITE-ORDER-01, CITE-BRACKET-01/02, CITE-LINK-01/02, REF-SEC-01, REF-NUM-01/02.
- [ ] `src/autofix/safe_fixes.py`: bracket normalization, DOI prefix normalization.
- [ ] `src/output/report.py`: `report.json` + `report.md`.
- [ ] `src/output/diff.py`: `changes.patch`.
- [ ] `src/workflow/prescreen.py`: glue for one paper folder.
- [ ] `main.py`: `prescreen <folder>` command.

### Phase 2 — Full format checking

- [ ] Annex B per-type field validation (PROC-REQ-*, JOUR-REQ-*, DOI-REQ-*, AUTH-*, TITLE-*).
- [ ] Formatting checks: FMT-TITLE-*, FMT-AUTH-*, FMT-FIG-*, FMT-TBL-*, FMT-UNIT-*.
- [ ] `prescreen-all <submissions_dir>` batch command.
- [ ] HTML report option for editor dashboard.

### Phase 3 — LLM-augmented suggestions

- [ ] `src/llm/client.py`: OpenAI-compatible client with local/commercial toggle.
- [ ] DOI lookup via CrossRef API + LLM confirmation.
- [ ] Sentence-case title correction prompt.
- [ ] ISO 4 journal abbreviation lookup (using https://github.com/marcinwrochna/abbrevIso).
- [ ] Missing metadata suggestions (venue, year, pages) written to `llm_suggestions.md`.

### Phase 4 — PDF-level checks + workflow integration

- [ ] PDF page-size check (595×792 pt, JACoW standard).
- [ ] Font embedding check (all fonts must be embedded).
- [ ] Margin / text area check.
- [ ] Indico/JACoW API integration: fetch paper list, upload prescreen report.
- [ ] `judge` command: emit green/yellow/red recommendation.
- [ ] `qa` command: second-pass quality assurance check.

---

## 9. CLI Reference

```
uv run python main.py prescreen <paper_folder>
    Pre-screen a single submission folder.
    Options:
      --llm / --no-llm        Enable/disable LLM suggestions [default: --no-llm]
      --model TEXT            LLM model name [env: LLM_MODEL]
      --base-url TEXT         LLM base URL  [env: LLM_BASE_URL]
      --out-dir TEXT          Override output directory [default: <folder>/aiagent_prescreen]

uv run python main.py prescreen-all <submissions_dir>
    Batch prescreen all paper folders under submissions_dir.
    Options: same as prescreen, plus --workers INT (parallel workers)

uv run python main.py report <paper_folder>
    Re-render the report from an existing prescreen run.

uv run python main.py export-skills
    Dump skill_cards.json for editor-knowledge export.
```

---

## 10. Configuration

All settings can be provided via environment variables or a `.env` file:

| Variable        | Default                        | Description |
|-----------------|--------------------------------|-------------|
| `LLM_ENABLED`   | `false`                        | Enable LLM suggestions |
| `LLM_BASE_URL`  | `http://localhost:11434/v1`    | OpenAI-compatible endpoint |
| `LLM_MODEL`     | `llama3`                       | Model name |
| `LLM_API_KEY`   | `ollama`                       | API key (`ollama` for local) |
| `CROSSREF_EMAIL`| (empty)                        | Polite pool email for CrossRef DOI lookup |

---

## 11. Dependencies (pyproject.toml)

| Package        | Purpose |
|----------------|---------|
| `typer`        | CLI framework |
| `rich`         | Terminal output, progress bars |
| `pydantic`     | Data models |
| `pylatexenc`   | LaTeX tokenizer / parser |
| `bibtexparser` | `.bib` file parser |
| `openai`       | LLM client (OpenAI-compatible) |
| `httpx`        | Async HTTP for CrossRef lookups |
| `python-dotenv`| `.env` config loading |
| `pytest`       | Testing |

---

## 12. Testing Strategy

- **Unit tests** for each check in `tests/test_reference_checks.py` and `tests/test_formatting_checks.py` — covering both valid inputs and each error condition.
- **Integration tests** using the two paper examples (`MOP019`, `FRAD03`) as fixtures.
- **LLM tests** mocked via `respx` (no real API calls in CI).
- Run with: `uv run pytest -v`
