# Fine-tuning Qwen3-14B on reference formatting

The model learns one job: turn an author's reference into the JACoW (Annex B)
form, the way your editors did. It never becomes the source of facts — the
agent still checks every answer and every added value comes from Crossref,
DataCite or the JACoW proceedings.

```
corpus (indico-pull) ──► finetune-data ──► train.jsonl / eval.jsonl
                                              │
                         GPU: train_qwen3_lora.py ──► LoRA adapter
                                              │
                         merge_and_export.sh ──► Ollama model "jacow-refs"
                                              │
             finetune-eval (model vs rules) ──► decide ──► REFERENCE_MODEL=jacow-refs
```

## 1. Training data (CPU, any machine with the corpus)

**Standalone:** `scripts/finetune/prepare_dataset.py` does only this step and
needs only the JACoW reference formatter, `python-docx` and `bibtexparser<2` —
not the agent. The formatter is not on PyPI: install the copy in the local
test package (`pip install ./jacow-tools/jacow-reference-formatter python-docx "bibtexparser<2" pylatexenc`), or run
the script inside the agent's environment (`uv run python scripts/finetune/…`
from `jacow-tools/editing-agent`), where everything is already installed:

```bash
python scripts/finetune/prepare_dataset.py corpora/CONF-A corpora/CONF-B \
    --test-conference corpora/CONF-B --out data/refs --mailto you@lab.org
```

It writes `train.jsonl`, `eval.jsonl`, `test.jsonl` (all of the test
conference), `rejected.jsonl` and `summary.json`. The same step through the
agent:

```bash
uv run python main.py indico-pull …             # once per past conference
uv run python main.py finetune-data corpora/IPAC25 --out data/refs-ipac25
```

Each paper's author revision is paired with the editors' final revision and
references are matched by number (Word) or `\bibitem` key (LaTeX). A pair is
kept only if it teaches **formatting that preserves information**:

* the editor's version passes the damage check against the author's, with
  only values a lookup supplied declared as added — editors' slips (one test paper's
  editor copied another reference's arXiv number) are rejected;
* values the editor added (DOI, pages) are supported by the lookup record,
  which is put in the prompt exactly as at inference;
* the editor's version is checked against the clear Annex B rules first —
  "et al." with a full stop, "and" between two authors, the comma before
  "and", spaced initials, `doi:` form, month full stops, “…” quotes — and
  corrected, so an editor's slip is not learned as correct; each row records
  the fixes and the editor's own text (`style_fixes`, `editor_original`).
  Title case is a team decision: `--title-case sentence` sentence-cases
  titles and rejects any title whose words cannot all be decided;
* references are paired by content — same first author and similar text —
  not only by number, since editors renumber, insert and remove references;
* LaTeX (`\enquote`, `\textquotedblleft`, accents, `\,`, math) is turned
  into plain text; an example with LaTeX still in it is rejected;
* correct Annex B edits are not mistaken for damage: a conference written in
  full becoming its label ("10th Int. Particle Accelerator Conf. (IPAC'19)" →
  "IPAC'19"), long journal titles with commas (NIM A) abbreviated, months
  abbreviated, a publisher URL replaced by the DOI the lookup confirms;
* already-correct references make up at most `--unchanged-share` (15 %) of
  the final data, so the model learns to leave a correct reference alone
  without learning to change nothing;
* identical pairs are kept once across the whole conference (popular
  references recur in hundreds of papers);
* LaTeX papers are read from their `\bibitem` list, or — when they cite from
  `.bib` files — entry by entry by citation key. Both sides of a `.bib` pair
  are written out in the same Annex B layout, so what the model learns from
  them is the editor's field changes (title case, journal abbreviation,
  added DOI, author list); layout is learned from Word and `\bibitem` papers.

`rejected.jsonl` lists every pair left out and why — read it: it is also a
record of where editors went beyond formatting. Papers, not references, are
split between training and evaluation, so no paper is in both.

Combine several conferences by concatenating their `train.jsonl` files; keep
one recent conference out entirely as the final test.

## 2. Training (GPU)

```bash
pip install -r scripts/finetune/requirements.txt
python scripts/finetune/train_qwen3_lora.py --data data/refs --check     # look first
python scripts/finetune/train_qwen3_lora.py --data data/refs --out runs/refs-v1
```

QLoRA on a 4-bit base model: one 24 GB GPU is enough for Qwen3-14B. With about
20 000 examples, two epochs take a few hours. `--check` prints one example as
the model sees it: the system prompt ends with `/no_think`, and the answer
must contain no `<think>` text.

## 3. Serve it

```bash
scripts/finetune/merge_and_export.sh runs/refs-v1/adapter ~/llama.cpp
```

This merges the adapter, converts to GGUF, quantises to Q4_K_M (about 9 GB)
and registers the model with Ollama as `jacow-refs`. If Ollama does not pick
up Qwen3's chat template from the GGUF, copy the `TEMPLATE` block from
`ollama show qwen3:14b --modelfile` into the generated `Modelfile` and run
`ollama create` again.

## 4. Decide with numbers

```bash
uv run python main.py finetune-eval data/refs/eval.jsonl --model jacow-refs
```

For the held-out references, the rule-based formatter and the model are both
scored: **exact** and **loose** agreement with the editor, **safe** (passes the
damage check) and **offered** (safe and an actual change). Switch the model
on only if it beats the formatter on agreement without losing on *safe*.

## 5. Use it

In `editing-agent/.env`:

```
LLM_ENABLED=true
REFERENCE_MODEL=jacow-refs
REFERENCE_MODEL_MODE=fallback    # ask only when the rules' rewrite was not offered
# REFERENCE_MODEL_MODE=prefer    # ask for every reference; use it whenever it passes
```

Whatever the mode, a model answer passes the same damage check as any
rewrite, with only the lookups' values declared, and is always a decision on
the desk, never applied automatically. The card says which model proposed it.

## Effort and cost (estimate)

| Step | Effort | Compute |
|---|---|---|
| Pull 2–3 past conferences, build and review the data | 1–2 weeks | CPU |
| Training runs and tuning (5–10 runs) | 1 week | a few hundred to ~2 000 USD rented, or a 24 GB GPU workstation |
| Evaluation and the go/no-go decision | 1 week | the served model |
| Retraining each year | a few days | one or two runs |

Train on an in-house machine if author drafts may not leave your
institution; the corpus and the data builder never need the network except
for reference look-ups.
