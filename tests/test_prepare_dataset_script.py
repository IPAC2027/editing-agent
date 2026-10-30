"""The standalone data-preparation script (scripts/finetune/prepare_dataset.py)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "finetune" / "prepare_dataset.py"

AUTHOR = ["J. Halvorsen, K. Lindqvist and P. Ortiz, “Lattice Design Of The Booster”, in IPAC 2023, "
          "Venice, Italy, May 2023, pp. 112-115.",
          "C. Alpha, M. Beta et al, “Sustainability”, 2025."]
EDITOR = ["J. Halvorsen, K. Lindqvist, and P. Ortiz, “Lattice design of the booster”, in Proc. "
          "IPAC’23, Venice, Italy, May 2023, pp. 112-115.",
          "C. Alpha, M. Beta et al, “Sustainability”, Apr. 2025, arXiv:2501.10603"]


def _word(path: Path, refs: list[str], link: str | None = None) -> None:
    d = docx.Document()
    d.add_paragraph("A TITLE")
    d.add_paragraph("REFERENCES")
    for i, r in enumerate(refs, 1):
        d.add_paragraph(f"[{i}]\t{r}")
        if link and i == 1:
            d.add_paragraph(link)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))


def _conference(root: Path, papers: list[str]) -> Path:
    for code in papers:
        _word(root / code / "original" / "Source_Files" / f"{code}.docx", AUTHOR,
              "https://doi.org/10.18429/JACoW-IPAC2023-MOPA001")
        _word(root / code / "current" / "Source_Files" / f"{code}.docx", EDITOR,
              "doi:10.18429/JACoW-IPAC2023-MOPA001")
    return root


def test_the_script_prepares_train_test_and_rejected(tmp_path):
    a = _conference(tmp_path / "CONF-A", ["MOP01", "MOP02"])      # MOP02 duplicates MOP01
    b = _conference(tmp_path / "CONF-B", ["TUP01"])
    out = tmp_path / "data"
    run = subprocess.run([sys.executable, str(SCRIPT), str(a), "--test-conference", str(b),
                          "--out", str(out), "--offline", "--eval-share", "0",
                          "--unchanged-share", "0.5"],
                         capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert run.returncode == 0, run.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["papers"] == 3 and summary["duplicates"] == 4   # MOP02 and TUP01 repeat MOP01
    train = [json.loads(x) for x in (out / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    rejected = [json.loads(x) for x in (out / "rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(train) == 1 and train[0]["source"] == "word"
    # The DOI line below the entry is part of the reference, on both sides.
    assert train[0]["messages"][1]["content"].endswith("https://doi.org/10.18429/JACoW-IPAC2023-MOPA001")
    assert train[0]["messages"][2]["content"].endswith("doi:10.18429/JACoW-IPAC2023-MOPA001")
    assert rejected and rejected[0]["label"] == "2"        # the arXiv number an editor added
    assert (out / "test.jsonl").read_text(encoding="utf-8") == ""          # CONF-B's pairs were all duplicates


def test_the_script_uses_the_agents_prompt():
    spec = importlib.util.spec_from_file_location("prepare_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from src.finetune.prompt import SYSTEM, user_message
    assert module.SYSTEM == SYSTEM
    assert module.user_message("R", {"doi": "10.1/x"}) == user_message("R", {"doi": "10.1/x"})


def _module():
    spec = importlib.util.spec_from_file_location("prepare_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("editor,expected,note", [
    # a test paper's editor: "et al" without the full stop
    ("D. Delta, F. Epsilon, Ch. Zeta et al, “The Example Collider”, CERN, Geneva, Switzerland, 2025.",
     "D. Delta, F. Epsilon, Ch. Zeta et al., “The Example Collider”, CERN, Geneva, Switzerland, 2025.",
     "'et al.' punctuation"),
    # two authors without "and", and a stray space before the closing quote
    ("G. Alpha, P. McBeta, “RF developments for a future collider “, CERN, 2025.",
     "G. Alpha and P. McBeta, “RF developments for a future collider”, CERN, 2025.",
     "'and' between two authors"),
    ("J. Halvorsen, K. Lindqvist and P. Ortiz, “Lattice design”, 2023.",
     "J. Halvorsen, K. Lindqvist, and P. Ortiz, “Lattice design”, 2023.", "comma before 'and'"),
    ("H.P. Alpha, “Title”, Apr 2021. https://doi.org/10.1088/2399-6528/ac1c89",
     "H. P. Alpha, “Title”, Apr. 2021. doi:10.1088/2399-6528/ac1c89", "initials spacing"),
])
def test_clear_annex_b_rules_are_applied_to_the_editors_version(editor, expected, note):
    fixed, notes = _module().style_fix(editor)
    assert fixed == expected and note in notes


def test_a_correct_reference_is_left_alone():
    ok = "A. T. Alpha, B. Beta, and J.-P. Gamma, “Compact light sources”, in Proc. FLS’23, Lucerne, Switzerland, May 2023, pp. 57-59."
    assert _module().style_fix(ok) == (ok, [])


def test_title_case_is_a_team_choice():
    m = _module()
    editor = "A. Alpha, “High Field Magnet Programme for Future Colliders”, 2025."
    assert m.style_fix(editor, "any")[0] == editor
    fixed, notes = m.style_fix(editor, "sentence")
    assert fixed == "A. Alpha, “High field magnet programme for future colliders”, 2025." and "sentence case" in notes
    assert m.style_fix("A. Alpha, “The Zorblax Kicker Upgrade”, 2025.", "sentence")[0] is None


# --- Fixes from the review of two conferences' data (Oct 2026) -----------------

def test_latex_becomes_plain_text():
    m = _module()
    assert m.latex_to_text(r"Y. Kappa et al., \textquotedblleft Orbit drift\textquotedblright, Aug.\ 2024") == \
        "Y. Kappa et al., “Orbit drift”, Aug. 2024"
    assert m.latex_to_text(r"S. Lambda et al., \enquote{An Alternating Phase Focusing injector}") == \
        "S. Lambda et al., “An Alternating Phase Focusing injector”"
    assert m.latex_to_text(r"O. Omega, I.\,V. Iota, pp. 1--3") == "O. Omega, I. V. Iota, pp. 1–3"
    assert m.latex_to_text(r"M. Fabbr\`i, {\it et al.}") == "M. Fabbrì, et al."
    assert not m.has_latex(m.latex_to_text(r"10\textsuperscript{th} Int. Conf., $\beta$-beams"))


def test_references_are_paired_by_content_not_only_number():
    m = _module()
    old = {"1": "A. Alpha and B. T. Beta, “An interesting talk”, presented at IPAC’14, unpublished.",
           "2": "C. Gamma et al., “Energy recovery efficiency”, Phys. Rev. Accel. Beams, vol. 24, 2021."}
    new = {"1": "C. Gamma et al., “Energy recovery efficiency”, Phys. Rev. Accel. Beams, vol. 24, p. 010101, 2021.",
           "2": "D. Delta, “Something else entirely”, 2020."}
    pairs, repaired = m.pair_references(old, new)
    assert pairs == [("2", old["2"], new["1"])] and repaired == 1     # Alpha has no partner


def test_bib_entries_follow_the_annex_b_order():
    m = _module()
    article = {"ENTRYTYPE": "article", "author": "Mu, S. and others", "title": "Hard X-ray pulses",
               "journal": "Phys. Rev. Lett.", "volume": "99", "pages": "999999",
               "month": "oct", "year": "2017", "doi": "10.1103/PhysRevLett.99.999999"}
    assert m._bib_layout(article) == ("S. Mu et al., “Hard X-ray pulses”, Phys. Rev. Lett., vol. 99, "
                                      "p. 999999, Oct. 2017. doi:10.1103/PhysRevLett.99.999999")


def test_correct_annex_b_edits_are_kept():
    from jacow_formatter import check_rewrite
    m = _module()
    nim = ("Y. K. Beta, “Beam dynamics”, Nuclear Instruments and Methods in Physics Research Section A: "
           "Accelerators, Spectrometers, Detectors and Associated Equipment, vol. 999, p. 123456, 2022.")
    edited, _ = m.style_fix("Y. K. Beta, “Beam dynamics”, Nucl. Instrum. Methods Phys. Res., Sect. A, "
                            "vol. 999, p. 123456, 2022.")
    assert edited == "Y. K. Beta, “Beam dynamics”, Nucl. Instrum. Methods Phys. Res. A, vol. 999, p. 123456, 2022."
    assert check_rewrite(nim, edited, allowed_substitutions=m.journal_substitutions(nim, edited)).ok
    conf = "Y. Kappa et al., “Drift”, in Proc. 10th Int. Particle Accelerator Conf. (IPAC'19), Melbourne, Australia, May 2019."
    assert check_rewrite(conf, "Y. Kappa et al., “Drift”, in Proc. IPAC'19, Melbourne, Australia, May 2019.").ok
    mixed, notes = m.style_fix("G. Theta, “Recent highlights from an antiproton ring\", Nucl. Instrum. Methods Phys. Res. A, 2004.")
    assert "“Recent highlights from an antiproton ring”" in mixed and "quotation marks" in notes


def test_unchanged_references_are_capped(tmp_path):
    from src.finetune import dataset
    root = tmp_path / "CONF"
    many = [f"A. Author{i}, “Title number {i}”, Phys. Rev. Lett., vol. {i}, p. {i}, 2020." for i in range(1, 11)]
    fixed = list(many)
    fixed[0] = fixed[0].replace("Title number 1", "Title number 1").replace(", 2020.", ", Jan. 2020.")
    _word(root / "P1" / "original" / "Source_Files" / "P1.docx", [m.replace(", 2020.", ", January 2020.") if i == 0 else m for i, m in enumerate(many)])
    _word(root / "P1" / "current" / "Source_Files" / "P1.docx", fixed)
    summary = dataset.build(root, tmp_path / "out", lookups=False, unchanged_share=0.5, eval_share=0.0)
    assert summary["corrections"] == 1 and summary["unchanged_available"] == 9
    assert summary["unchanged_kept"] == 1                       # 50 % of the final data at most


def test_urls_dois_and_doi_links_survive_conversion():
    m = _module()
    assert m.latex_to_text(r"see https://x.org/a_b%20c") == "see https://x.org/a_b%20c"
    assert m.latex_to_text(r"1997, \href{https://doi.org/10.1007/978-3-662-03407-1}{10.1007/978-3-662-03407-1}") == \
        "1997, doi:10.1007/978-3-662-03407-1"


def test_the_nim_section_form_is_not_damage():
    from jacow_formatter import check_rewrite
    m = _module()
    raw = "P. Sigma, “Benchmark”, Nucl. Instrum. Methods Phys. Res., Sect. B, Jul 2015, vol. 99, pp. 1-4."
    fixed, _ = m.style_fix(raw)
    assert fixed == "P. Sigma, “Benchmark”, Nucl. Instrum. Methods Phys. Res. B, Jul. 2015, vol. 99, pp. 1-4."
    assert check_rewrite(raw, fixed, allowed_substitutions=m.journal_substitutions(raw, fixed)).ok
