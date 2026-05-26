# JACoW Conference Paper AI Agent

An agentic pre-screening tool that checks and corrects JACoW/IPAC conference paper submissions, replacing or assisting a human editor.  
Supports **local LLMs** (Ollama / LM Studio) and **commercial APIs** (OpenAI, Anthropic) via a common OpenAI-compatible interface.

---

## What it does

Given a submission folder, the tool writes an `aiagent_prescreen/` subfolder containing:

| File | Description |
|------|-------------|
| `report.json` | Machine-readable findings (check ID, severity, line, original, suggested) |
| `report.md` | Human-readable Markdown report for the editor |
| `<ID>_edited.tex` | Source with all **safe auto-fixes** applied |
| `changes.patch` | Unified diff of every change made |
| `llm_suggestions.md` | LLM-generated hints for items requiring human judgment |

### Priority 1 — References (highest value)

- Citation ordering: first-occurrence numbers must be ascending throughout the paper.
- Bracket normalization: `[1][2]` → `[1, 2]`, spaces, ranges.
- Citation/reference linkage: every `\cite{}` must resolve; every entry must be cited.
- Annex B format validation per reference type (proceedings, journal, arXiv, book, thesis …).
- Author list rules: commas, `et al.`, initials.
- DOI: presence, `doi:` prefix format, single-token constraint.

### Priority 2 — Formatting

- Title: ALL CAPS in `\title{}`, no trailing punctuation.
- Authors: `Initials Surname` format, email footnote on corresponding author.
- Figures: sequential numbering, in-text reference before appearance, caption format.
- Tables: sequential numbering, caption above, in-text reference before appearance.
- Number–unit: non-breaking space between value and SI unit (`10~MeV`), correct case.

---

## Quick start

```bash
# Single paper folder
uv run python main.py prescreen paper_examples/MOP019-revision-27544_author

# All papers in a submissions directory
uv run python main.py prescreen-all paper_examples/

# With LLM suggestions (requires a running Ollama or API key)
uv run python main.py prescreen paper_examples/MOP019-revision-27544_author \
  --llm --model llama3 --base-url http://localhost:11434/v1
```

---

## Configuration

Create a `.env` file (or set environment variables):

```
LLM_ENABLED=false
LLM_BASE_URL=http://localhost:11434/v1   # or https://api.openai.com/v1
LLM_MODEL=llama3
LLM_API_KEY=ollama                       # use your key for commercial APIs
CROSSREF_EMAIL=you@example.com           # for polite CrossRef DOI lookups
```

---

## Project layout

```
src/
├── models.py              # Pydantic: Finding, Reference, Paper
├── parser/
│   ├── latex_parser.py    # .tex → Paper model
│   └── bib_parser.py      # .bib → list[Reference]
├── checks/
│   ├── reference_checks.py   # Priority-1 checks
│   └── formatting_checks.py  # Priority-2 checks
├── autofix/
│   └── safe_fixes.py      # Deterministic, no-LLM fixes
├── llm/
│   ├── client.py          # OpenAI-compatible backend
│   └── prompts.py         # Prompt templates
├── workflow/
│   └── prescreen.py       # End-to-end workflow for one folder
└── output/
    ├── report.py           # report.json + report.md
    └── diff.py             # changes.patch
```

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the full design, data models, check catalogue, phased roadmap, and testing strategy.

---

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | MVP: citation ordering + bracket fixes + report | planned |
| 2 | Full Annex B format checks + formatting checks + batch mode | planned |
| 3 | LLM suggestions: DOI lookup, sentence case, ISO 4 abbreviations | planned |
| 4 | PDF-level checks, Indico integration, green/yellow/red judge | planned |
