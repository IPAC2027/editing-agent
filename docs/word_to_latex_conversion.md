# Word → LaTeX Conversion Pipeline (Future Implementation)

## Overview

When an author submits a Word (`.docx`) manuscript, the goal is to produce a
JACoW-compliant `.tex` file + `.bib` file that compiles to a PDF closely
matching the original submission — then feed it through the existing
`prescreen` pipeline for checks and auto-fixes.

---

## Input

| File | Required | Notes |
|------|----------|-------|
| `<ID>.docx` | Yes | Main manuscript |
| `<ID>.pdf` | Yes | Author's original rendered PDF, used for visual validation |
| Figures | Yes | Any image files (`.png`, `.jpg`, `.pdf`, `.eps`) uploaded alongside |

---

## Pipeline Stages

### Stage 1 — Pandoc extraction (deterministic)

```bash
pandoc <ID>.docx -o <ID>_raw.tex \
    --wrap=none \
    --extract-media=figures/
```

- Converts prose, headings, tables, and inline math to LaTeX
- Extracts embedded images to `figures/`
- Output is intentionally kept as raw Pandoc output — no JACoW-specific
  formatting yet
- **Do not let the LLM touch math output from Pandoc** — Pandoc's math
  extraction is more reliable than LLM reconstruction

---

### Stage 2 — LLM pass 1: structural conversion

Feed to the LLM:
- The raw `<ID>_raw.tex` from Stage 1
- The list of available figure filenames
- A system prompt containing the JACoW template skeleton (see below)

**LLM tasks:**
1. Replace the Pandoc documentclass with `\documentclass{jacow}`
2. Reconstruct the preamble (`\usepackage` blocks standard for JACoW)
3. Rebuild `\author[affil]{Name}` and `\institute[affil]{Institution}` blocks
   from the author list
4. Convert the reference list (plain text at end of document) into proper
   `.bib` entries, inferring `@inproceedings` / `@article` / `@misc` from
   context (conference names, journal names, arXiv IDs)
5. Wire `\includegraphics{figures/<filename>}` using the actual uploaded
   filenames
6. Preserve Pandoc's math output verbatim — do not rewrite equations
7. Output: `<ID>.tex` + `<ID>.bib`

**System prompt anchor:**
```
You are a LaTeX expert converting a rough Pandoc-generated .tex file into a
clean JACoW conference paper. The target documentclass is `jacow` (v3.0).
Preserve all mathematical content exactly as given. Reconstruct the
bibliography as a BibTeX .bib file. Use \doi{} for DOIs, never \url{https://doi.org/...}.
```

---

### Stage 3 — Compile

Feed `<ID>.tex` + `<ID>.bib` into the existing `compile_tex()` pipeline
(`src/latex_build.py`). This handles:
- JACoW class file injection
- Figure path resolution
- biber / pdflatex sequencing
- PDF output to `aiagent_prescreen/<ID>_converted.pdf`

---

### Stage 4 — Visual diff (validation gate)

Convert both PDFs to page images and compute similarity:

```python
# Dependencies: pdf2image, scikit-image
from pdf2image import convert_from_path
from skimage.metrics import structural_similarity as ssim
import numpy as np

def page_similarity(pdf_a: Path, pdf_b: Path) -> list[float]:
    pages_a = convert_from_path(pdf_a, dpi=150)
    pages_b = convert_from_path(pdf_b, dpi=150)
    scores = []
    for a, b in zip(pages_a, pages_b):
        arr_a = np.array(a.convert("L"))
        arr_b = np.array(b.convert("L"))
        # Resize b to match a if page counts or sizes differ
        if arr_a.shape != arr_b.shape:
            from skimage.transform import resize
            arr_b = resize(arr_b, arr_a.shape, anti_aliasing=True)
        scores.append(ssim(arr_a, arr_b, data_range=255))
    return scores
```

**Acceptance threshold:** mean SSIM ≥ 0.80 across all pages is "good enough"
for JACoW editorial review purposes (content match, not pixel-perfect).

If threshold is met → proceed to `prescreen` checks.
If not → enter the feedback loop (Stage 5).

---

### Stage 5 — LLM pass 2: visual feedback loop

**Trigger:** any page with SSIM < 0.80.

For each failing page:
1. Render both versions as images
2. Ask the LLM (vision-capable model preferred):
   - "Here is page N of the original PDF and page N of the compiled PDF.
     Describe the layout differences and suggest targeted LaTeX fixes."
3. Apply the suggested fix to `<ID>.tex`
4. Recompile (Stage 3)
5. Recompute SSIM (Stage 4)
6. Repeat up to **3 iterations** — stop and flag for manual review if not
   converged

**Notes:**
- Keep fixes surgical — pass only the relevant paragraph/figure block to the
  LLM, not the entire file
- Log each iteration's SSIM scores so the editor can see progress
- A non-vision LLM can still help if given a textual diff description extracted
  from `pdfplumber` (bounding boxes of text blocks)

---

## Convergence and Exit Criteria

| Condition | Action |
|-----------|--------|
| SSIM ≥ 0.80 on first compile | Pass to `prescreen` |
| SSIM ≥ 0.80 after ≤ 3 LLM iterations | Pass to `prescreen` |
| SSIM < 0.80 after 3 iterations | Output best attempt, flag `CONVERT-WARN` finding, pass to `prescreen` anyway |
| Compile fails after LLM edits | Revert to last successful compile, flag `BUILD-FAIL` |

---

## Failure Modes and Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM hallucinates math | Preserve Pandoc math output verbatim; only touch prose |
| Long paper exceeds context window | Chunk by `\section`; convert section-by-section |
| Figure filenames unknown | List all uploaded files in the LLM prompt |
| Multi-author affiliation confusion | Pass the raw author block to LLM separately before full conversion |
| Bibliography type ambiguity | If LLM is unsure, default to `@misc` with `howpublished`; editor can correct |

---

## Suggested New CLI Command

```
uv run python main.py convert-word <folder> [--compile] [--llm-model gpt-4o]
```

- Expects `<folder>/Source_Files/<ID>.docx`, `<folder>/PDF/<ID>.pdf`,
  and figures in `<folder>/Supporting_files_for_papers/`
- Writes converted `.tex` + `.bib` to `<folder>/Source_Files/`
- Then runs the standard `prescreen` pipeline automatically
- Emits `CONVERT-OK` or `CONVERT-WARN` findings in the report

---

## Dependencies to Add

```toml
# pyproject.toml
pdf2image = ">=1.17"    # PDF → images for visual diff
scikit-image = ">=0.22" # SSIM computation
pdfplumber = ">=0.11"   # text/bbox extraction from PDFs (fallback for non-vision LLMs)
# pandoc must be installed system-wide: brew install pandoc
```
