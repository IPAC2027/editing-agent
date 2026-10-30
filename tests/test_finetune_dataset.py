"""Training data for the reference model, from a pulled conference."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

AUTHOR = [
    "J. Halvorsen, K. Lindqvist and P. Ortiz, “Lattice Design Of The Booster”, in IPAC 2023, "
    "Venice, Italy, May 2023, pp. 112-115.",
    "C. Alpha, M. Beta et al, “Sustainability”, 2025. http://arxiv.org/abs/2501.10602",
    "A. Alpha, “A correct reference”, Phys. Rev. Lett., vol. 1, p. 011001, 2020.",
]
EDITOR = [
    "J. Halvorsen, K. Lindqvist, and P. Ortiz, “Lattice design of the booster”, in Proc. "
    "IPAC’23, Venice, Italy, May 2023, pp. 112-115.",
    # A test-paper mistake: another reference's arXiv number.
    "C. Alpha, M. Beta et al, “Sustainability”, Apr. 2025, arXiv:2501.10603",
    "A. Alpha, “A correct reference”, Phys. Rev. Lett., vol. 1, p. 011001, 2020.",
]


def _paper(path: Path, refs: list[str]) -> None:
    d = docx.Document()
    d.add_paragraph("A TITLE", style="Title")
    d.add_paragraph("Text [1-3].")
    d.add_paragraph("REFERENCES")
    for i, r in enumerate(refs, 1):
        d.add_paragraph(f"[{i}] {r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "CONF"
    _paper(root / "MOP01" / "original" / "Source_Files" / "MOP01.docx", AUTHOR)
    _paper(root / "MOP01" / "current" / "Source_Files" / "MOP01.docx", EDITOR)
    (root / "index.json").write_text(json.dumps({"event_id": 1, "papers": [
        {"code": "MOP01", "friendly_id": 1, "state": "accepted", "tags": []}]}), encoding="utf-8")
    return root


def test_pairs_are_matched_by_reference_number(corpus):
    from src.finetune.dataset import pairs_from_corpus
    pairs = pairs_from_corpus(corpus)
    assert [p.label for p in pairs] == ["1", "2", "3"]
    assert pairs[1].final.endswith("arXiv:2501.10603")


def test_only_information_preserving_edits_are_kept(corpus, tmp_path, monkeypatch):
    monkeypatch.setenv("AIAGENT_OFFLINE", "1")
    from src.finetune.dataset import build
    out = tmp_path / "data"
    counts = build(corpus, out, lookups=False, unchanged_share=0.5, eval_share=0.0)
    train = [json.loads(line) for line in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    rejected = [json.loads(line) for line in (out / "rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    assert counts["corrections"] == 1 and counts["unchanged_kept"] == 1 and counts["rejected"] == 1
    assert rejected[0]["label"] == "2"                       # the editor's arXiv slip
    assert train[0]["messages"][2]["content"].startswith("J. Halvorsen, K. Lindqvist, and P. Ortiz")
    assert train[0]["messages"][0]["content"].endswith("/no_think")


BIB_AUTHOR = r"""@inproceedings{halvorsen,
  author = {Halvorsen, J. and Lindqvist, K. and Ortiz, P.},
  title = {Lattice Design Of The Booster},
  booktitle = {Proc. IPAC'23},
  venue = {Venice, Italy},
  month = may, year = {2023}, pages = {112--115}}
"""
BIB_EDITOR = r"""@inproceedings{halvorsen,
  author = {Halvorsen, J. and Lindqvist, K. and Ortiz, P.},
  title = {Lattice design of the booster},
  booktitle = {Proc. IPAC'23},
  venue = {Venice, Italy},
  month = may, year = {2023}, pages = {112--115}}
"""
TEX = r"""\documentclass{jacow}
\begin{document}
See \cite{halvorsen}. \printbibliography
\end{document}
"""


def _latex_side(folder: Path, bib: str) -> None:
    (folder / "Source_Files").mkdir(parents=True, exist_ok=True)
    (folder / "Source_Files" / "TUP02.tex").write_text(TEX, encoding="utf-8")
    (folder / "BibTeX_file_only_for_LaTeX_papers").mkdir(parents=True, exist_ok=True)
    (folder / "BibTeX_file_only_for_LaTeX_papers" / "refs.bib").write_text(bib, encoding="utf-8")


def test_bib_based_latex_papers_are_paired_by_key(tmp_path):
    from src.finetune.dataset import pairs_from_corpus
    root = tmp_path / "CONF"
    _latex_side(root / "TUP02" / "original", BIB_AUTHOR)
    _latex_side(root / "TUP02" / "current", BIB_EDITOR)
    (root / "index.json").write_text(json.dumps({"event_id": 1, "papers": [
        {"code": "TUP02", "friendly_id": 2, "state": "accepted", "tags": []}]}), encoding="utf-8")
    pairs = pairs_from_corpus(root)
    assert [p.label for p in pairs] == ["halvorsen"]
    assert "Lattice Design Of The Booster" in pairs[0].raw
    assert pairs[0].final.startswith("J. Halvorsen, K. Lindqvist, and P. Ortiz, “Lattice design of the booster”, in Proc. IPAC'23")
    assert "pp. 112-115." in pairs[0].final


def test_duplicate_references_are_kept_once(corpus, tmp_path, monkeypatch):
    monkeypatch.setenv("AIAGENT_OFFLINE", "1")
    from src.finetune.dataset import build
    # A second paper citing exactly the same references, corrected the same way.
    _paper(corpus / "MOP02" / "original" / "Source_Files" / "MOP02.docx", AUTHOR)
    _paper(corpus / "MOP02" / "current" / "Source_Files" / "MOP02.docx", EDITOR)
    index = json.loads((corpus / "index.json").read_text(encoding="utf-8"))
    index["papers"].append({"code": "MOP02", "friendly_id": 2, "state": "accepted", "tags": []})
    (corpus / "index.json").write_text(json.dumps(index), encoding="utf-8")
    counts = build(corpus, tmp_path / "data", lookups=False, unchanged_share=0.5, eval_share=0.0)
    assert counts["pairs"] == 6
    # MOP02 repeats MOP01 exactly: all three of its pairs are duplicates.
    assert counts["duplicates"] == 3 and counts["rejected"] == 1
