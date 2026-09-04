# The editor's workflow

This document is the contract between the agent and the person using it. It
exists because the previous version broke that contract in ways that were only
visible if you compared its outputs against each other, and because the
question "can a local LLM help here reliably?" has a specific answer that has to
be written down or it will be re-litigated every release.

The goal is narrow and measurable: **spend less of an editor's time per paper
than the tool costs them.** Everything below follows from that.

---

## 1. Findings and edits are different things

| | **Finding** | **Edit** |
|---|---|---|
| what it is | something a human must decide or chase | a byte-exact replacement of `source[start:end]` |
| carries | a message, a severity, a location | `before`, `after`, a span, a tier, a rule, evidence |
| lives in | `report.md`, `report.json` | `edits.json`, `edits/E0NN.patch`, `history/` |
| can be wrong by | crying wolf | changing the wrong bytes |

An earlier version had only findings, plus a boolean `auto_fixed` that each fix
function set about itself. Nothing tied that boolean to the file on disk, which
is how one paper (THP017) came to report seven auto-fixes while
`changes.patch` was empty, `changes.html` said "No safe auto-fixes were
applicable", and the source and edited SHA-256 hashes matched.

## 2. Three tiers, decided per check

The tier is a property of the **check**, set by policy. It is not something an
individual fix decides about itself.

**Tier AUTO — applied without asking.**
Mechanically reversible, no judgement, no external fact. Number–unit spacing
(`10 MeV` → `10~MeV`), `doi:` prefix normalisation, `\url{doi:…}` → `\doi{…}`,
citation-bracket tidying inside spans the parser identified as citations,
`et al.` punctuation, BibTeX `pages` and `doi` field presentation.
These are 277 of the 311 changes on the 34-paper example corpus. They need no
review surface: the diff is the record.

**Tier SUGGEST — exactly one accept/reject decision.**
Needs an editor's eye, but comes with a concrete before/after and a rule
citation. Author initials, unit *case* (`1.3 Gev` → `1.3 GeV`), title
punctuation, sentence-casing a reference title, a whole-reference reformat,
reordering the reference list. About one per paper on the corpus.

**Tier FLAG — reported, never fixed.**
Anything whose fix needs a fact the agent could not verify: an absent DOI, a
page range, a venue, a figure it cannot find. A flag carries no `after` text and
is a `Finding`, not an `Edit`.

Two rules the code enforces rather than documents:

* An `Edit` with `before == after` **cannot be constructed** — `Edit`'s
  validator rejects it, and `make_edit()` returns `None`. This is what makes
  the phantom-auto-fix class of bug structurally impossible.
* Tier AUTO **requires verified evidence**. An edit whose justification came
  from an external service that was not reached is rejected at construction if
  it claims AUTO. It may still be offered as a suggestion.

## 3. What an editor actually gets

```
aiagent_prescreen/
├── review.html            one accept/reject decision per SUGGEST edit
├── <ID>_edited.tex        the AUTO tier applied, and nothing else
├── <ID>_edited.pdf        proof that the edited source still compiles
├── edits.json             the EditSet — what `apply` reads
├── structural.json        the reference-list permutation, if one is needed
├── edits/E0NN.patch       every edit as a standalone, applicable diff
├── history/               a git repo: one commit per edit
├── changes.patch          AUTO + SUGGEST as one diff, for a diff tool
├── report.md / .json      findings, and which checks did not run
└── repair_plan.json       machine-readable, generated from the EditSet
```

The workflow:

```bash
aiagent prescreen  <folder>        # safe changes applied, decisions prepared
aiagent review     <folder>        # accept/reject each remaining change
aiagent apply      <folder> --decisions review_decisions.json
```

`review.html` has keyboard shortcuts (`a` accept, `r` reject, `j`/`k` move) and
writes `review_decisions.json`, which `apply` **reads** — the previous panel
wrote decisions to browser storage and downloaded a file that no code consumed,
so the editor's only real choice was all of `<ID>_edited.tex` or none of it.

Editors who would rather not use the HTML at all have two other routes to the
same place:

```bash
aiagent apply <folder> --accept E004,E007      # by id
cd aiagent_prescreen/history
git log --oneline                              # one commit per edit
git revert <sha>                               # undo one, keep the rest
```

`apply` verifies every `before` against the current source first, so a source
the author has revised in the meantime produces a conflict rather than a
scrambled file.

## 4. Word submissions get Word tracked changes

Word is the format most JACoW submissions arrive in, and it used to be the one
this tool did least for: an HTML page of before/after cards and no corrected
document, so the editor read a suggestion in a browser and retyped it.

`<name>_tracked.docx` is now the primary output. It is the author's own
document with each correction as a `w:ins`/`w:del` revision, so Review → Accept
/ Reject works per change in the application editors already use. Rejecting
restores the author's text byte for byte, and character formatting (an italic
journal title) survives. The revision author is
`JACoW prescreen (<CHECK-ID>)`, so Word's reviewing pane groups changes by the
rule that produced them and a whole rule can be accepted at once.

`word_references.html` is still written, because it is the only place the
*reasons* fit.

## 5. A check that cannot verify says so

Every external lookup used to swallow its exception and return `None`, so
"Crossref has no DOI for this reference" and "we had no network" produced
identical output. On a run with blocked egress the agent emitted 25 confident
`DOI-MISSING-01` warnings, several for references with well-known DOIs.

`verify_doi()` now returns three states — `VERIFIED`, `NOT_FOUND`,
`UNVERIFIED` — and `src/lookup_status.py` records which services actually
answered. A check whose authority was unreachable reports **NOT CHECKED** at
INFO severity, and `report.md` ends with a per-service availability table. A
DOI constructed from a URL pattern is never shown unless it resolves: an
earlier version derived `10.18429/JACoW-p05-FPAT077` from a proceedings URL and
offered it unchecked, which is a dead DOI in the published proceedings if an
editor accepts it.

## 6. A rewrite is verified against what it replaced

Round-tripping a reference through a field model and re-emitting it from a
template is the highest-risk operation in the codebase. The old guard looked
for a handful of *missing markers* and passed both real defects observed on the
sample corpus: a doubled comma at `pp. 611-632,,` and `Poincaré` lowercased to
`poincaré`.

`src/refs/verify.check_rewrite()` compares the rewrite to the original:

1. no unresolved sentence-case abstention;
2. no newly-introduced doubled punctuation;
3. every run of digits preserved with at least the same multiplicity;
4. every DOI preserved verbatim;
5. no word lost (accent- and case-insensitively);
6. no word's capitalisation changed (when the caller forbids it);
7. no structural marker lost (`in Proc.`, `pp.`, `vol.`, a month, …);
8. the output not dramatically shorter than the input.

A rewrite that fails any check is **discarded** and the original kept, with a
finding that says what it would have damaged. An unformatted reference costs an
editor less than a damaged one.

## 7. Sentence case: the polarity is inverted

JACoW wants reference titles in sentence case, which means lowercasing ordinary
words and leaving proper nouns alone. Doing that with a whitelist of proper
nouns cannot work — the set of surnames, facilities, codes and instruments in
accelerator physics is open-ended — and a 60-item list is why an earlier version
lowercased `Poincaré`, `Tevatron`, `Twiss` and `Landau`.

A word is now lowercased only when it is **positively known** to be ordinary.
Three sources of evidence, none of them opinion:

1. **An English dictionary, minus every word with a capitalised homograph.**
   This is what protects `Watt`, `May`, `March`, `Kelvin` and `Newton`: each is
   both a common word and a name, so neither is in the lexicon.
2. **Words accelerator physicists write in lowercase themselves**, mined from
   the corpus. An author never writes a real proper noun in lowercase, so a
   word seen lowercase in two or more papers is ordinary — `emittance`,
   `quadrupole`, `symplectic`.
3. **The paper's own prose**, harvested per run by `lowercase_evidence()`. If
   this author writes `cryomodule` lowercase mid-sentence, it is an ordinary
   word here even if no dictionary knows it.

Plus a bounded list of multi-word facility names (`Large Hadron Collider`,
`Advanced Photon Source`), because word-by-word classification cannot catch a
proper noun made entirely of ordinary words — and unlike surnames, the set of
facilities is finite.

Everything else **abstains**: the word is left exactly as written and reported
in `TitleCasing.unsure`. A title with any unsure word is not rewritten at all,
because partial sentence-casing is worse than none — it looks deliberate, so an
editor is less likely to check it.

## 8. Where a local model may and may not be used

**The rule: a model may classify, segment, or verify. It may never author a
bibliographic fact.**

A DOI, a year, a volume, a page range, a venue: these are the fields an editor
cannot check at a glance, which makes a plausible wrong value worse than a
blank. Two prompt templates that asked for exactly those
(`doi_lookup_prompt`, `missing_metadata_prompt`) were **deleted**, not
discouraged. The 244 KB standalone formatter at the repository root already
stated this principle in its header — it did not survive the migration into
`src/`, and is now enforced in code.

The permitted uses live in `src/llm/classify.py`, and each one is
**mechanically checkable**:

| Job | Why a model | How the answer is constrained |
|---|---|---|
| `classify_title_words` | The whitelist problem is unbounded; this is the one place the deterministic path structurally cannot finish the job | One label per token from `KEEP`/`LOWER`/`UNSURE`. A response with the wrong number of labels, or a label for a word not asked about, is discarded. The text is rebuilt in code from the labels — the model never returns prose. |
| `classify_reference_type` | Replaces a regex cascade | One token from a closed set of eight. Anything else is a parse failure. |
| `segment_reference` | Where 1,000 lines of extraction regex are brittle | **Verbatim only**: every character of every field must be a contiguous substring of the input, checked in code. One failed field discards the whole response. |
| `adjudicate_finding` | Directly attacks false positives | `CONFIRM`/`REJECT`/`UNSURE` plus a quote that must appear in the text. Used only to **hide** findings, never to add one: a wrong suppression leaves the editor where they were without the tool; a wrong addition sends them chasing nothing. |

Three practices that matter more with a 7–8B local model than a hosted one, and
that live in code rather than in the prompt:

* **Constrain the decoding, not just the prompt.** JSON mode is requested, so a
  malformed answer is a parse failure rather than something to salvage.
* **Sample three times and require unanimity.** Not a majority — two out of
  three is exactly where a small model is guessing. Disagreement becomes
  `UNSURE`.
* **Draw those samples at a non-zero temperature.** This one was wrong for a
  while and is worth naming, because it is the kind of bug that leaves every
  test passing. Unanimity is only evidence of confidence if the samples *can*
  differ; drawn greedily a local model returns the same tokens three times, and
  the check silently degenerates into "did the server answer three times". The
  default is now `LLM_TEMPERATURE=0.3`, and `LLM_SAMPLES=1` — where there is
  nothing to compare — is drawn at 0.
* **Abstention is a first-class answer** and propagates to the report, where it
  becomes a flag for a human instead of an edit.

The model is off by default (`LLM_ENABLED=false`). Turning it on can only add
suggestions and remove findings; it can never change what the AUTO tier does.

**There is one answer to "is a model in play?"** `--llm` / `--no-llm` wins;
with neither, `LLM_ENABLED` decides; and `src/desk/server._settle_model` asks
the server once, at start-up, whether the requested model is actually there.
If it is not, the flag *and* the environment are put back to off, and the
launcher window says so. The state being avoided is the half-on one: a `.env`
saying `LLM_ENABLED=true` used to buy the desk one of the four sanctioned uses
of a model — the one that reads the environment directly — and not the other
three, which is a run nobody can describe afterwards. A model that cannot be
reached is never silently swapped for another one either: asking for a model
the server does not have is a failure that names what it does have.

## 9. The noise budget

An editor should have to look at a handful of things per paper, not a wall.
Four mechanisms keep it that way:

* **One finding per problem, not per symptom.** A missing `.bib` file is
  reported once, not once per unresolved `\cite` — that single typo used to
  produce 19 separate ERRORs on MOZN01.
* **One finding per paper for a list-shaped problem.** Author-name format is
  one item naming every offender, not one warning per name (38 of them on ten
  papers, of which 32 were parser debris).
* **A check never duplicates an edit.** If the tool fixed it, the tool does not
  also complain about it. `DOI-FMT-02` used to appear twice per occurrence at
  two different severities.
* **Conference-wide facts are notes.** The template version is the same for
  every paper in a conference and is not something an editor fixes per
  submission, so it is INFO, and it says plainly that the "latest version" is a
  constant this tool does not verify against jacow.org.

Measured on the 34 LaTeX example submissions, per paper: **8.1 changes applied
automatically, 1.0 decisions, 0.2 problems needing a human, 0.2 warnings.**

## 10. What to measure next

The 49 example submissions are the project's most valuable unused asset. Have
one editor label them once — which findings are real, and what the right fix is
— and per-check precision becomes a number in CI. Then the tier a check runs at
can be *derived* from its measured precision (auto above ~98%, suggest above
~90%, off below) instead of chosen by hand, and "the result is not very
satisfying" becomes a quantity that moves.

The one number that matters is not precision, though. It is minutes per paper,
with and without the tool, measured on the same editor. Everything here is a
proxy for that.
