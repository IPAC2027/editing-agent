# JACoW conference paper pre-screening agent

A pre-screening tool for JACoW/IPAC submissions. It applies the corrections that
are provably safe, offers the rest as individual accept/reject decisions, and
reports what it could not verify instead of guessing.

Designed around one measurable goal: **cost an editor less time than it saves
them.** Every design decision in [`docs/editor_workflow.md`](docs/editor_workflow.md)
follows from that, and the two rules worth stating up front are:

- **An edit that changes nothing cannot be created.** The `Edit` model rejects
  `before == after`, so the report, the patch, the git history and the file on
  disk can never disagree about what happened.
- **A model may classify, segment or verify. It may never author a
  bibliographic fact.** DOIs, years, volumes, page ranges and venues come from
  Crossref, DataCite or refs.jacow.org, and are verified before they are shown.

---

## Quick start

```bash
uv sync

# One submission
uv run python main.py prescreen paper_examples/MOP030-revision-27360_author

# Review the changes that need a decision, then apply them
uv run python main.py review  paper_examples/MOP030-revision-27360_author
uv run python main.py apply   paper_examples/MOP030-revision-27360_author \
    --decisions review_decisions.json

# A whole conference
uv run python main.py prescreen-all paper_examples/ --workers 4
```

A run prints what it did:

```
MOP070 — decisions waiting
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Applied automatically ┃ Awaiting decision ┃ Needs a human ┃ Style points ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│                    11 │                 1 │             0 │            0 │
└───────────────────────┴───────────────────┴───────────────┴──────────────┘
```

## What an editor gets

| File | What it is |
|---|---|
| `review.html` | One accept/reject decision per proposed change. Keyboard: `a` accept, `r` reject, `j`/`k` move. Saves `review_decisions.json`, which `apply` reads. |
| `<ID>_edited.tex` | The source with **only** the automatic tier applied. Adoptable wholesale, sight unseen. |
| `<ID>_edited.pdf` | Proof that the edited source still compiles. |
| `<name>_tracked.docx` | **Word submissions:** the author's document with each correction as a Word revision. Review → Accept / Reject works per change. |
| `edits/E0NN.patch` | Every edit as a standalone diff — `git apply` or `patch` one at a time. |
| `history/` | A git repository: one commit per edit. `git log -p`, `git revert <sha>`. |
| `report.md` | Findings, grouped by who has to act, plus which checks did not run and why. |
| `edits.json` | The machine-readable edit set that `apply` operates on. |

Three ways to accept a subset, all equivalent:

```bash
# from the browser
uv run python main.py apply <folder> --decisions review_decisions.json
# by id
uv run python main.py apply <folder> --accept E004,E007
# with git
cd <folder>/aiagent_prescreen/history && git revert <sha>
```

`apply` verifies every edit against the current source first, so a source the
author has revised since the run produces a clear conflict rather than a
scrambled file. `--in-place` overwrites the author's `.tex`; without it a copy
is written and the original is untouched.

## The three tiers

| Tier | Meaning | Examples |
|---|---|---|
| **auto** | Mechanically reversible, zero judgement, no external fact. Applied without asking. | `10 MeV` → `10~MeV`, `DOI: 10.x` → `doi:10.x`, `\url{doi:…}` → `\doi{…}`, `[1][2]` → `[1, 2]`, `et. al` → `et al.`, BibTeX `pages`/`doi` presentation |
| **suggest** | One accept/reject decision, with a before/after and the rule behind it. | author initials, unit case (`Gev` → `GeV`), title punctuation, reference sentence case, whole-reference reformat, reference-list reordering |
| **flag** | Reported, never fixed — the fix needs a fact the agent cannot verify. | missing DOI, missing figure, unresolved `\cite`, a `.bib` file that does not exist |

On the 34 LaTeX example submissions, per paper: **8.1 automatic changes, 1.0
decisions, 0.2 problems needing a human.**

## What it checks

**References** — citation order and first-appearance numbering; `\cite` ↔ entry
linkage; Annex B layout per reference type; author-list conventions; DOI
presence, prefix form and single-token constraint; arXiv → DOI; URLs where a DOI
belongs. BibLaTeX submissions are first-class: `.bib` fields are edited
directly, which is safer than rewriting LaTeX prose.

**Formatting** — title punctuation and `\NoCaseChange` handling; author names as
`Initials Surname`; non-breaking space and case for SI units; figure and table
files resolving (including inside `.zip` archives); the JACoW class version.

**Build** — the edited source is compiled, so every automatic change is known
not to break the build. Page-limit checks run on the resulting PDF.

## Reliability guarantees

- **No phantom fixes.** An `Edit` with `before == after` cannot be constructed.
- **Verified before applied.** Every edit's `before` is re-checked against the
  source at apply time.
- **Never invents a fact.** A constructed DOI is not shown unless it resolves.
- **Never claims to have checked.** A check whose authority was unreachable says
  `NOT CHECKED`, at INFO severity, and `report.md` lists per-service
  availability.
- **Never damages a reference.** A whole-reference rewrite must preserve every
  digit, DOI, word and capital in the original, or it is discarded and the
  original kept.
- **Abstains rather than guesses.** Sentence-casing lowercases only words
  positively known to be ordinary; anything else is left as written and
  reported.

## Optional local model

Off by default. `--llm` enables the four uses in `src/llm/classify.py`, all of
them mechanically checkable, none of them able to author a fact:

- **Proper-noun labelling** for sentence case — the one place the deterministic
  path structurally cannot finish the job. One label per token; the text is
  rebuilt in code.
- **Reference-type classification** — one token from a closed set.
- **Field segmentation** under a verbatim-substring constraint, so invention is
  impossible rather than discouraged.
- **False-positive suppression** — used only to *hide* findings, never to add
  them.

Every classification is sampled three times and must be **unanimous**; JSON mode
is requested so a malformed answer is a parse failure; `UNSURE` propagates to
the report as a flag for a human.

```bash
# Ollama
uv run python main.py prescreen <folder> --llm \
    --model llama3 --base-url http://localhost:11434/v1

# LM Studio exposes the same OpenAI-compatible interface
uv run python main.py prescreen <folder> --llm \
    --model local-model --base-url http://localhost:1234/v1
```

## Configuration

```
LLM_ENABLED=false
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3
LLM_API_KEY=ollama
LLM_SAMPLES=3                    # samples that must agree before a label is used
LLM_TIMEOUT=60
CROSSREF_EMAIL=you@example.com   # for polite Crossref lookups
```

## Rule pack

The agent reads a versioned, sourced JACoW rule pack from
`src/knowledge/rulesets/jacow/`. Each rule carries source IDs, applicability, an
automation policy and an editor-escalation condition.

```bash
uv run python main.py rules --format latex
uv run python main.py rules --query "proceedings DOI" --category references
uv run python main.py rules --json
```

## Project layout

```
src/
├── edits.py                  Edit, EditSet, Tier — the unit of everything proposed
├── lookup_status.py          which external authorities actually answered
├── models.py                 Finding, Reference, Paper
├── parser/                   .tex → Paper, .bib → References, .docx → ParsedWord
├── checks/                   deterministic checks, producing findings
├── autofix/
│   ├── latex_edits.py        span-anchored edit generators for LaTeX source
│   ├── reference_edits.py    .bib fields and \bibitem bodies
│   └── structural.py         reference-list reordering (applied after span edits)
├── refs/
│   ├── verify.py             mechanical damage checks on a rewrite
│   ├── text_utils.py         sentence case with abstention
│   └── …                     formatters, journal abbreviation, conference DB
├── llm/
│   ├── classify.py           the only sanctioned uses of a model
│   └── prompts.py            advisory review prompts
├── output/
│   ├── review.py             review.html, per-edit patches, git history
│   ├── docx_tracked.py       Word tracked changes
│   └── report.py             report.md / .json, from the EditSet
└── workflow/
    ├── prescreen.py          LaTeX end to end, plus `apply`
    └── word_prescreen.py     Word end to end
```

## Tests

```bash
uv run pytest -q          # 301 tests
```

`tests/test_edits.py` pins the edit-model invariants;
`tests/test_editor_workflow.py` runs the whole pipeline on a synthetic
submission and asserts the report matches the file on disk, that accept/reject
applies only what was accepted, and that Word tracked changes reject back to the
author's exact text. Several tests are named after the specific regression they
prevent.

## Roadmap

| Scope | Status |
|---|---|
| Span-anchored edits, three tiers, per-edit patches, git history | done |
| Word tracked changes | done |
| `.bib` field editing for BibLaTeX submissions | done |
| Evidence tracking and NOT CHECKED reporting | done |
| Rewrite damage verification, sentence-case abstention | done |
| Constrained local-model classification with abstention | done |
| Labelled gold set over the 49 examples, per-check precision in CI | next |
| Tier derived from measured precision rather than chosen by hand | next |
| Indico integration, green/yellow/red submission judge | later |

See [`docs/editor_workflow.md`](docs/editor_workflow.md) for the reasoning
behind all of it, and [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the
original design.
