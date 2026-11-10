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

## For editors: the review desk

Editors do not use a terminal. **Double-click `Start Review Desk`** — the
`.command` file on macOS, the `.bat` file on Windows — and a browser opens on
your papers.

The command line has two modes:

```
aiagent --join ADDRESS --code CODE           # editor, working from the chief's
                                             # desk: no folder (remembered)
aiagent --manage [papers-folder] [--event N] # chief editor: the managing page
                                             # (Indico, download, preparing)
aiagent [papers-folder]                      # one editor working alone
```

The launcher runs the editor mode: the chief's desk this computer joined,
else the folder it used last. In chief mode the list starts with **The conference
in Indico**: every paper Indico has, its state and editor, and whether it is
already in the folder, with **Download and prepare new papers**, which fetches
what is missing, reads who holds each paper, and prepares the new ones (never
one an editor has claimed), with progress on the page. The event can be given
with `--event` or typed on the page; once papers are downloaded the folder
remembers it (`index.json`) and refuses another. The Indico token is pasted
into the page once (no environment variable needed) and never shown again. The maintainers'
commands below are under `aiagent tools …` (their old names still work).

The desk serves a page on your own computer. Nothing is uploaded, nothing is
installed, and the files the author sent are never modified. It answers only
requests addressed to `127.0.0.1` and only accepts changes made from its own
page, so another website open in the same browser cannot drive it.

| Screen | What you do there |
|---|---|
| **The list** | Every submission with its status, how many changes await you, and how many problems the author must fix. Click one to open it. For a conference pulled from Indico, also who has each paper there — you, a colleague, or nobody — as of the pull, or of **Check Indico now** (one read-only request). |
| **Your decisions** | One card per change: what it is, why JACoW wants it, before and after. Accept or keep as submitted. Keyboard: `a` `r` `j` `k` `n`. Repeated changes of one kind get an "accept all" button. The corrections applied automatically are listed too, folded away, each with **Put back as submitted** — "we did not ask you" never means "you cannot say no". |
| **Title & authors** | For a conference pulled from Indico: the paper's title and author list against Indico's. Where they differ, the paper's title is taken as right and the author list becomes the combined list — after an email the desk drafts gives the author 48 hours to object. Applying adds the missing authors to the reviewed files and lists the Indico changes for the editor to make. |
| **Problems** | Sorted by who has to act — only the author can fix these / for you to check / for the record. Tick off what you have handled. |
| **Your notes** | Anything the agent missed. Goes into the letter. |
| **The paper** | The paper with your accepted corrections in place. Click any line to edit it yourself. Jump to the title, authors, body, references, or the first change. |
| **Letter to the author** | Drafted from your decisions and notes. Edit, save, copy. |
| **Files** | The corrected PDF, the author's original, the Word tracked-changes file. |
| **Check a reference list** | Linked from the header. Paste any bibliography; each reference comes back formatted, looked up and checked by the same engine as the papers. Replaces the formatter's separate Streamlit app. |

**Finish this paper** writes the reviewed source, the letter and a summary of
every decision, then offers the next unfinished paper. A finished paper can be
reopened. Everything is saved as you go — there is no save button to forget.

**Several editors.** The chief editor's desk (`--manage`) holds the papers.
It also opens a door for editors on the network: port 8770, with a join code
shown on the chief's page (`--no-share` keeps it to this computer). Each editor runs
`aiagent --join ADDRESS --code CODE` (no folder) on their own computer once;
after that plain `aiagent`, or the launcher, opens the same desk. Their desk
never opens the chief's folder:
- **Take:** the editor takes a paper, and the claim (`aiagent_prescreen/claim.json`,
  `O_EXCL`) is made on the chief's computer.
- **Copy:** the editor's desk downloads a copy into a working folder it keeps
  itself, one per chief's desk (`~/.aiagent/working/<address>/`). Editors
  never choose a folder. Copies given back are cleared the next time the desk
  starts; a copy with changes the chief never received is kept.
- **Send back:** a few seconds after each change, the paper's
  `aiagent_prescreen/` is sent back. Only the desk holding the claim may send.
  The claim file is never overwritten, and the last five versions are kept in
  `.pool_backups/`.
- **Give back or give up:** finishing a paper sends it one last time and
  releases the claim. **Give up this paper** does the same for an unfinished
  one, with an optional reason: the chief's page shows a notice until
  dismissed, and the paper is free for the next editor (unassigned in Indico
  when the sync is on).
- **One desk per person:** while the door is open, `.pool_door.json` in the
  folder says so and any other desk started on that folder refuses. An
  editor's desk started on the chief's computer keeps its own settings in
  `~/.aiagent/editor/`, so it never has the chief's desk id.

**Edit, then QA.** A paper is edited, then QA'd by an editor
(`state.stage_of`: to edit → to QA → QA passed; a failed QA sends it back to
edit, with a note). A claim records what the paper was taken for (`edit` or
`qa`), and the chief's door refuses a take that does not fit the paper's
stage. Only taking to edit makes someone the paper's editor and assigns them
in Indico; a QA never changes Indico. Nobody QAs a paper they edited: the
chief's desk records everyone whose send changed the paper's editing
(`edited_by`, by Indico user id) and refuses them its QA. Verdicts are kept in the review state
(`qa`, with a history).

**The chief's page manages; it does not edit.** It reads Indico, downloads and
prepares papers, keeps Indico's assignments in step and lists every paper,
in Indico or in the folder, with: whether it is downloaded (and prepared),
which is newer (Indico has revisions the copy lacks, or the copy has editing
Indico has not seen), the author/title check (OK, email to send, email sent,
fixed), whether it is edited and by whom, and its QA (not yet, in QA, passed,
failed with the note), next to Indico's editor (refreshed every 10 seconds).
New revisions of papers already downloaded are flagged, not downloaded yet.
**Free** releases a paper from
whoever holds it: their desk is told on its next send, their unsent work stays
on their computer, and an unfinished paper is unassigned in Indico. Every
editing request to the managing page is refused (`MANAGING_ROUTES` in
`src/desk/server.py`). To edit, the chief clicks **Edit papers**: it starts an
editor's desk joined to the chief's own door, with its own settings
(`~/.aiagent/editor/`) and Indico account, and opens it in a new tab
(`src/desk/editing.py`). That desk closes when the managing desk does, even
if it is killed; a desk already open with those settings is reused.

**Indico.** Each desk takes its Indico token in its own page, not from an
environment variable. The token is checked with `GET /api/user/` and kept in
`~/.aiagent/indico_token` (mode 600), and is never sent back to the page.
`INDICO_TOKEN` still works as a fallback, except on an editor's desk.
- **Editors:** their token is who they are, in place of a typed name. Their
  desk sends the chief their Indico user id and name, never the token, and
  the chief's desk refuses a take from a desk without them.
- **Indico's editors only:** the chief's desk lets an account take a paper
  (to edit or to QA) only if it is one of the event's paper editors or
  editing managers in Indico (`IndicoSync.may_edit`). It works whether the
  assignment switch is on or off.
  - *Paper editors:* the chief's token reads `GET …/editing/api/paper/editors`
    (the `paper_editing` permission, given directly or through a group). The
    list is kept 10 minutes. Someone not in it is looked up again at once (at
    most every 30 s), so a newly added editor gets in without a restart.
  - *Editing managers:* Indico has no endpoint listing them. Each editor's
    desk asks about its own account with its own token: that same endpoint
    answers 200 to an editing manager (or event manager) and 403 to anyone
    else (`IndicoClient.can_manage_editing`, `account.manages_editing`). It
    re-asks every 10 minutes, and at most every 30 s before a take, and sends
    the answer as `X-Indico-Editing-Manager`. The token is only sent to the
    Indico it was connected to.
  - *If Indico can't be read:* nobody new is let in. Someone confirmed in the
    last hour still is.
  - *Shown on the pages:* the editor's page and the chief's door panel show
    who is neither.
  - *Papers already taken* are not taken back; the chief can **Free** them.
  - *Trust:* the editing-manager answer, like the editor's Indico id, is
    reported by the editor's desk; the chief's desk cannot verify it.
- **The chief's desk:** when switched on for an event (the box on the chief's
  page), it assigns an editor in Indico when they take a paper, and unassigns
  them when they give it back unfinished. It reads Indico's assignments back
  every 2 minutes. Nothing is sent while it is off. Switching it on assigns
  the papers already being edited (`Pool.assign_held`, using the Indico id
  each claim records). Until then the managing page marks those papers *not
  told: the Indico sync is off*.
- **The one write:** this is the only thing the agent writes to Indico:
  `src/indico_client/assign.py` sends `POST …/editables/assign|unassign`
  with Indico's own conflict check, so a paper reassigned in Indico meanwhile
  is left alone. Indico sends no email for either request.
  `tests/test_indico_read_only.py` keeps every other path read-only.
- **Signed identities:** Indico names a person in these requests only by the
  signed identity it hands out, `User:<id>:<signature>`. The signature is made
  with the server's secret key; a bare `User:<id>` gets a 422 "User id
  signature missing". The chief's desk takes these identities from the paper
  editors list and from each paper's editor in the paper list
  (`IndicoSync.identifier`), and keeps them out of the files sent to editors'
  desks. So Indico can assign only people it lists: an editing manager who
  is not in the paper editing team can take papers here, but is not assigned
  in Indico. The chief's page reports that, and tries again at every read of
  Indico, so adding them to the team is enough.

Each editor's name and desk id live in
`~/.aiagent/desk.json` (`AIAGENT_HOME`); an editor's desk started on the chief's
own computer keeps its own in `~/.aiagent/editor/`. Opening the desk on a folder without
`--join` still works for one editor on their own. Code:
`src/desk/pool.py` (chief), `src/desk/remote.py` (editor), `src/desk/bundle.py`
(the zips, read strictly).

Word submissions work the same way, except the text is edited in Word: finishing
produces a `.docx` carrying **only the corrections you accepted**, as tracked
changes, so *Review → Accept / Reject* works per change and rejecting restores
the author's words exactly.

Full walkthrough: [`docs/editor_guide.md`](docs/editor_guide.md) — written for
someone who has never opened a terminal.

---

## For maintainers: the command line

```bash
uv sync

# One submission
uv run python main.py prescreen paper_examples/MOP030-revision-27360_author

# List the decisions, then apply the accepted ones
uv run python main.py review  paper_examples/MOP030-revision-27360_author --show
uv run python main.py apply   paper_examples/MOP030-revision-27360_author \
    --decisions review_decisions.json

# A whole conference
uv run python main.py prescreen-all paper_examples/ --workers 4
# A conference pulled from Indico; only papers not prepared yet
uv run python main.py prescreen-all NAPAC2025/ --workers 4 --skip-prepared
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

## Measuring against real editorial work

The agent is calibrated against conferences that real editors have already
finished. Their corrections are the ground truth, and the tag codes they
applied are the labels.

```bash
# What is in a conference, using your own Indico account (reads only)
uv run python main.py indico --event 82
uv run python main.py indico --event 82 --tags     # the tag vocabulary

# Pull it for study. Reads only: the client refuses any non-GET request.
uv run python main.py indico-pull ~/HIAT2025 --event 82 --dry-run
uv run python main.py indico-pull ~/HIAT2025 --event 82

# What can be learned from it, and what cannot
uv run python main.py corpus      ~/HIAT2025
# What the editors actually changed, and which corrections recur
uv run python main.py corpus-diff ~/HIAT2025
# How the agent's proposals compare, per check, per zone, per editor
uv run python main.py corpus-score ~/HIAT2025
```

An Indico personal token with `read:everything` is needed
(`<indico>/user/tokens/`). Paste it into the desk's Indico box once: it is kept
in `~/.aiagent/indico_token`, readable only by you, and these commands use it
too. `INDICO_TOKEN` or the OS keyring still work as fallbacks. It is never
printed. Indico has no narrower scope for the
editing module, so treat it as your whole account and revoke it when done.

**Reading the numbers.** Three columns, and only one of them is evidence of a
defect:

| | |
|---|---|
| **confirmed** | the editors made this change too |
| **contradicted** | they changed this very text into something else — the strongest evidence against a rule |
| **unconfirmed** | they did not make it. **Not** evidence that it is wrong |

And every rate is read against the part of the paper it comes from, because
editors are strict about front matter and references, variable about figures
and tables, and inconsistent with each other in running text. Measured over
253 papers the agent confirms at 52% in the strict zones and 14% in running
text. `src/corpus/zones.py` holds that logic; a low rate in running text is a
statement about editorial appetite, not about the check.

Two conferences, two house styles: NAPAC's editors normalise measurements to
`\qty{}` (270 conversions to 27), HIAT's to `~` (43 to 6). So a check
"confirmed" on one conference can be contradicted on the next, and a
per-conference style setting is the obvious next piece of work.

## What lands on disk

Everything the agent and the desk write goes into an `aiagent_prescreen/`
folder beside the author's files. The author's files are never touched.

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
| `review_state.json` | The editor's decisions, notes and hand edits, and the title and author check's email, deadline and outcome. Survives re-screening. |
| `front_matter.json` | The paper's title and authors, read from the source for a paper prepared before reports carried them. |
| `author_letter.txt` | The letter, once the paper is finished. |
| `review_summary.md` | Every decision and note, for the record. |

Three ways to accept a subset, all equivalent:

```bash
# from the browser
uv run python main.py apply <folder> --decisions review_decisions.json
# by id
uv run python main.py apply <folder> --accept E004,E007
# an automatic correction you disagree with
uv run python main.py apply <folder> --reject E002
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
| **auto** | Mechanically reversible, zero judgement, no external fact. Applied without asking — and individually reversible afterwards, from the desk or with `apply --reject <id>`. | `10 MeV` → `10~MeV`, `DOI: 10.x` → `doi:10.x`, `\url{doi:…}` → `\doi{…}`, `[1][2]` → `[1, 2]`, `et. al` → `et al.`, BibTeX `pages`/`doi` presentation |
| **suggest** | One accept/reject decision, with a before/after and the rule behind it. | author initials, unit case (`Gev` → `GeV`), title punctuation, reference sentence case, whole-reference reformat, reference-list reordering |
| **flag** | Reported, never fixed — the fix needs a fact the agent cannot verify. | missing DOI, missing figure, unresolved `\cite`, a `.bib` file that does not exist |

On the 34 LaTeX example submissions, per paper: **8.1 automatic changes, 1.0
decisions, 0.2 problems needing a human.**

## References: one engine

Every reference — a Word paragraph, a `\bibitem` body, a reference pasted into
the desk — is formatted, looked up and integrity-checked by
[jacow-reference-formatter](https://github.com/IPAC2027/jacow-reference-formatter),
pinned to a release tag in `pyproject.toml`. `src/references.py` is the only
module that talks to it, and turns its answer into the agent's tiers:

| Formatter result | Agent |
|---|---|
| Only presentation changes (`DOI:` → `doi:`, "et al" punctuation, serial comma, quotes, dashes) | **auto** |
| Full reformat that passes `check_rewrite` and adds nothing from a lookup | **suggest** |
| Reformat that fills in or corrects fields from Crossref, DataCite or JACoW | **suggest**; the card lists each value and its source: "DOI and pages added from Crossref; volume corrected from Crossref (25 → 26)" |
| `doi_mismatch` | flag REF-INT-01: the cited DOI belongs to another paper |
| `suspected_fabricated` | flag REF-INT-02: no index has it, check by hand |
| `unverifiable` | REF-INT-03, NOT CHECKED (only when lookups ran) |
| Rewrite fails `check_rewrite`, or a value was defaulted | rewrite discarded, author's text kept |

`check_rewrite` lives in the formatter, so its own command line and web page
are protected by the same guard. It protects the author's information, not
the author's wording: every value an authoritative source added or corrected
is declared to it from the formatter's provenance record, so lookups reach the
editor, while anything lost or invented with no source behind it — a dropped
journal name, a guessed year, a lost "unpublished", an acronym's capitals —
still discards the rewrite. Set `REFERENCE_CORRECTIONS=false` to let lookups
fill gaps only, never change a value the author gave. Word and LaTeX differ only in the output:
tracked changes for Word, source edits for LaTeX.

### House style

Choices the Style Guide leaves open are a per-conference profile
(`src/house_style.py`), chosen with `HOUSE_STYLE` in `.env`:

| Profile | Units in LaTeX | Page ranges | Label | Applied Physics |
|---|---|---|---|---|
| `jacow` (default) | `\qty` when siunitx is loaded | `pp. 57-59` | `IPAC’23` | `App.` (Annex C) |
| `napac` | `\qty` | as `jacow` | as `jacow` | as `jacow` |
| `hiat` | `~` | as `jacow` | as `jacow` | as `jacow` |
| `iso4` | as `jacow` | `pp. 57–59` | `IPAC'23` | `Appl.` (ISO 4) |

Any single setting can be overridden: `HOUSE_STYLE_UNITS`,
`HOUSE_STYLE_PAGE_DASH`, `HOUSE_STYLE_APOSTROPHE`, `HOUSE_STYLE_APPLIED`.

## What it checks

**References** — citation order and first-appearance numbering; `\cite` ↔ entry
linkage; Annex B layout per reference type; author-list conventions; DOI
presence, prefix form and single-token constraint; arXiv → DOI; URLs where a DOI
belongs. BibLaTeX submissions are first-class: `.bib` fields are edited
directly, which is safer than rewriting LaTeX prose.

**Formatting** — title punctuation and `\NoCaseChange` handling; author names as
`Initials Surname`; non-breaking space and case for SI units; figure and table
files resolving (including inside `.zip` archives); the JACoW class version.

**Main text of Word papers, as tracked changes** — non-breaking spaces before
units, "[8][9]" → "[8, 9]", "Tab. 1" → "Table 1" and "Fig." → "Figure" at the
start of a sentence are applied automatically; "equation 1" → "Eq. (1)", unit
symbols, title capitals, author lists, numbered headings, subsection Title
Case and caption form ("Figure 1:", final full stop) are suggestions. Each is
decided on the desk; the reviewed Word file carries only what was accepted.
Body text in a heading style and acronyms not expanded at first use are
reported. Paragraphs with hyperlinks, fields or equations are reported, never
rewritten.

**Paragraph and heading layout of Word papers, as tracked formatting
changes** — first-line indents restored to 0.33 cm, widow/orphan control on
and headings kept with their text are applied automatically; body text in
"Normal" or a heading style moved to the body-text style, and direct fonts
on headings and body text removed, are suggestions. Third-level headings on
a line of their own are reported. The team's `jacow-paper-formatting` skill
(kept in `src/knowledge/jacow-paper-formatting-skill/`) supplies the document
audit: page size, margins, columns, fonts, hyperlinks, reference spacing.

**Front matter** (Word) — the title in capitals with units and names in their
own case (GeV, SwissFEL), no closing punctuation; authors as `Initials Surname`
separated by commas, without "and"; values joined to units by a non-breaking
space, with the standard unit symbol. LaTeX papers get the same rules from the
existing title, author and unit checks.

**Body text** (Word and LaTeX) — citations in the abstract; `Tab. 1` (never
abbreviated); `Fig. 1` at the start of a sentence; `equation 1` / `Eq. 1`
instead of `Eq. (1)`; unpublished papers cited `in Proc.`; submitted papers that
name the journal.

**The author's PDF** (Word and LaTeX) — the JACoW page size (595 × 792 pt) and
margins; page numbers; fonts that are not embedded, including inside figures;
Type 3 bitmap fonts; hyperlinks on URLs that are not DOIs; DOIs split across
two lines. An unreadable PDF is
reported as NOT CHECKED, never as clean.

**Build** — the edited source is compiled, so every automatic change is known
not to break the build. Page-limit checks run on the resulting PDF; the limit is a conference setting
(`JACOW_BODY_PAGES` in `.env`, default 3). The build
treats the submission as untrusted: `latexmk` runs with `-norc` and shell escape
off, and any `latexmkrc` that arrived with the paper is deleted first.

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

**Fine-tuned reference model.** `docs/finetune.md` describes training Qwen3-14B
on your editors' reference corrections (`finetune-data`, `scripts/finetune/`,
`finetune-eval`) and switching it on with `REFERENCE_MODEL=jacow-refs`. Its
answers pass the same damage check as any rewrite and are always decisions.

The team's chosen model is **Qwen3 14B** (Apache 2.0): `ollama pull qwen3:14b`,
about 9 GB on disk, comfortable on a 16–24 GB GPU or an Apple-silicon Mac with
24 GB or more. One shared machine can serve every editor: point `LLM_BASE_URL`
at it. Qwen3's "thinking" mode is switched off automatically for the agent's
short classification calls (the `/no_think` tag), which keeps them fast.


Off by default. One model, configured once in `.env`, serves both the agent
and the reference formatter. Every use is mechanically checkable and none can
author a fact — DOIs, years, volumes, pages, authors and titles come only from
Crossref, DataCite, refs.jacow.org or the author's own text:

| Where | What the model does | Kept in check by |
|---|---|---|
| Agent: titles of every reference (`.bib`, `\bibitem`, Word) | Labels the words sentence case left as written: proper noun or ordinary word | One label per word, unanimous samples, text rebuilt in code, damage check rerun; always a suggestion |
| Agent: LaTeX findings | Hides a finding it judges a false positive | May only hide, never add; the report counts what was hidden |
| Agent: `llm_suggestions.md` | Advisory review notes | A separate file; never an edit or a finding |
| Formatter: run-on citations | Points at where authors end and the title begins | Every span must be an exact substring of the citation, in order |
| Formatter: titles | Decides whether a hyphen is a line-break leftover | Labels only |

The formatter's `llm_enrichment` tasks (guessing a conference city, or a
journal abbreviation) are never switched on by the agent.

Every classification is sampled three times and must be **unanimous**; JSON mode
is requested so a malformed answer is a parse failure; `UNSURE` propagates to
the report as a flag for a human.

```bash
# Ollama — the default backend; nothing to configure but the model name
ollama pull qwen3:14b
uv run python main.py prescreen <folder> --llm --model qwen3:14b

# LM Studio exposes the same OpenAI-compatible interface
uv run python main.py prescreen <folder> --llm \
    --model local-model --base-url http://localhost:1234/v1

# The desk takes the same three options
uv run python main.py desk <folder> --llm --model qwen3:14b
```

On the 48 example submissions the deterministic pass abstains on about **two
reference titles per paper**, so the model is asked roughly six questions per
paper — seconds, not minutes.

**The model is checked once, at start-up, not discovered halfway through a
batch.** `desk --llm` asks the server which models it has before it prints its
address, and says which of three things is true:

```
  Model:    qwen3:14b at http://localhost:11434/v1
  Model:    NOT USED — could not reach a model server at http://localhost:11434/v1
            (APIConnectionError). Is Ollama running? Papers are screened
            without it; every check that does not need a model still runs.
  Model:    NOT USED — http://localhost:11434/v1 answered, but has no model
            called 'qwen3.8:27b-mlx'. It offers: qwen3:14b, qwen2.5:14b.
```

A model that is not there degrades the run to the deterministic path; it never
silently substitutes a different model, and the page does not advertise a model
it is not using. When one *is* in use the desk's header carries a `model:` chip,
so an editor can always tell which kind of run they are looking at.

## Configuration

`cp .env.example .env` and edit. Everything is optional: with no `.env` the
agent runs fully deterministically. One file configures both tools: the
reference formatter takes its Crossref address, lookup cache
(`AIAGENT_CACHE_DIR`), model server and house style from these settings, and
`AIAGENT_OFFLINE=1` switches its lookups off.

```
LLM_ENABLED=false
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:14b
LLM_API_KEY=ollama
LLM_SAMPLES=3                    # samples that must agree before a label is used
LLM_TEMPERATURE=                 # default 0.3; see below
LLM_TIMEOUT=60
CROSSREF_EMAIL=you@example.com   # for polite Crossref lookups
```

`LLM_TEMPERATURE` defaults to **0.3** rather than 0, and that is deliberate:
unanimity across three samples is only evidence of confidence if the samples
can differ. Drawn greedily, a local model returns the same tokens three times
and the check degenerates into "did the server answer three times". With
`LLM_SAMPLES=1` there is nothing to compare, so that case is drawn at 0.

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
├── desk/                     the editor's browser workspace
│   ├── server.py             a local-only web server (standard library only)
│   ├── ui.py                 the page: one file, no external requests
│   ├── paper.py              assembling a paper; composing and closing it
│   ├── state.py             decisions, notes, hand edits, the worklist
│   └── plain.py              plain English for every check, and the letter phrasing
├── edits.py                  Edit, EditSet, Tier — the unit of everything proposed
├── lookup_status.py          which external authorities actually answered
├── models.py                 Finding, Reference, Paper
├── parser/                   .tex → Paper, .bib → References, .docx → ParsedWord
├── checks/                   deterministic checks, producing findings
├── autofix/
│   ├── latex_edits.py        span-anchored edit generators for LaTeX source
│   ├── reference_edits.py    .bib fields and \bibitem bodies
│   └── structural.py         reference-list reordering (applied after span edits)
├── references.py             the only door to jacow_formatter: tiers, settings, LaTeX round trip
├── house_style.py            per-conference presentation choices
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

## Continuous integration

`.github/workflows/ci.yml` runs the suite on Linux and Windows against the
pinned formatter release, and runs the formatter's test bibliography through
the agent (`tests/test_shared_bibliography.py`), comparing every decision with
`tests/data/shared_bibliography_decisions.json`. The formatter's own
`agent-contract.yml` runs this suite against each formatter commit, so a change
there that alters what editors are offered fails before it is released.

The measurement against real editors runs by hand on a self-hosted runner
labelled `jacow-corpus`, with the repository variable `JACOW_CORPUS` set to a
conference pulled with `indico-pull`: `corpus-score --json` then
`scripts/confirmation_gate.py`, which fails if a zone's confirmation rate falls
by more than three points or its contradictions rise. The first run records
`scripts/confirmation_baseline.json`; commit it.

Upgrading the formatter: tag a release there, change the tag in
`pyproject.toml`, `uv lock`, and run the suite; accept intended decision
changes with `UPDATE_SNAPSHOT=1`.

## Tests

```bash
uv run --extra dev pytest -q   # 359 tests; the reference engine's 870 are in the formatter
```

`tests/test_desk.py` walks the whole editor journey — open, decide, note, hand
edit, finish — and asserts that the file on disk matches what the editor chose.
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
| Browser review desk for non-technical editors | done |
| Corpus pulled from Indico; per-check scoring against real editorial diffs | done |
| Editor's own credential against the Indico editing API (reads) | done |
| Writing results back to Indico from the desk | next |
| One reference engine (jacow-reference-formatter) for Word and LaTeX | done |
| Per-conference house style (units, page-range dash, label apostrophe, App./Appl.) | done |
| House style for `\emph{et al.}` and `\midrule` | next |
| Tier derived from measured confirmation, per zone | next |
| TC07/TC08: figure, table and equation numbering, and "never referenced" | next |

See [`docs/editor_workflow.md`](docs/editor_workflow.md) for the reasoning
behind all of it, and [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the
original design.
