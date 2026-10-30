"""Training examples from pulled conferences: author reference -> editor reference.

Pairs come from the corpus (``indico-pull``): each paper's author revision and
the editors' final revision, references matched by number (Word) or key
(``\\bibitem``).  Editors make mistakes too — a test paper's editor copied another
reference's arXiv number — and a model learns whatever it is shown, so an
example is kept only when it teaches information-preserving formatting:

* the editor's version passes ``check_rewrite`` against the author's, with
  only values a lookup can vouch for declared as added;
* values the editor added (a DOI, pages) are supported by the verified
  record, which is then put in the prompt, as it will be at inference;
* identical pairs are kept at a small rate, so the model also learns to leave
  a correct reference alone.

LaTeX papers with a ``\\bibitem`` list are paired on the list; papers that
cite from ``.bib`` files are paired entry by entry (by key), each side written
out with the same Annex B layout so the pair carries only the editor's field
changes.  Identical pairs across papers are kept once.

Everything is written to JSONL in chat format, split by paper so no paper
contributes to both training and evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Pair:
    paper: str
    label: str
    raw: str
    final: str


def _script():
    """scripts/finetune/prepare_dataset.py — the one implementation of data preparation."""
    import importlib.util
    script = Path(__file__).resolve().parents[2] / "scripts" / "finetune" / "prepare_dataset.py"
    spec = importlib.util.spec_from_file_location("prepare_dataset", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pairs_from_corpus(root: Path) -> list[Pair]:
    """Author/editor reference pairs of a pulled conference, paired by content."""
    script = _script()
    out: list[Pair] = []
    for paper in script.paper_folders(root):
        try:
            old, _ = script.references(paper / "original")
            new, _ = script.references(paper / "current")
        except Exception:  # noqa: BLE001 — one unreadable paper never stops the run
            continue
        pairs, _ = script.pair_references(old, new)
        out += [Pair(paper.name, label, raw, final) for label, raw, final in pairs]
    return out


def build(root: Path, out_dir: Path, *, lookups: bool = True, unchanged_share: float = 0.15,
          eval_share: float = 0.1, seed: int = 7, title_case: str = "any") -> dict:
    """Write train/eval/rejected JSONL for one conference (see the script for details)."""
    return _script().run([root], out_dir, eval_share=eval_share, unchanged_share=unchanged_share,
                         lookups=lookups, title_case=title_case, seed=seed)
