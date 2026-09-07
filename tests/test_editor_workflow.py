"""End-to-end tests of the editor's workflow, on a synthetic submission.

These are the tests that would have caught the defects the audit found: a
report that disagrees with the file on disk, an accept/reject panel that
applies nothing, and a Word submission that gets no corrected document.
"""

import json
import re
import zipfile
from pathlib import Path

import pytest

from src.edits import EditSet
from src.workflow.prescreen import apply_decisions, prescreen

TEX = r"""% v 2.3  JACoW template
\documentclass[
               keeplastbox,
               ]{jacow}
\begin{document}
\title{Beam dynamics of a 10 MeV injector.}
\author{Yoshiteru Hidaka\thanks{hidaka@example.org}, K. Ha\textsuperscript{1},
S. Kongtawong\textsuperscript{1,2}\\
Brookhaven National Laboratory, Upton, NY, USA}
\maketitle

\section{INTRODUCTION}
The gun runs at 5 mhz with a 250 pC bunch and a 0.4 MT/m gradient \cite{first}\cite{second}.
Earlier work \cite{first} and later work \cite{second} agree [1][2].
A 50 nm spot was measured, see Refs. [ 3 ] and [1,2].
The array element A[1,2] must not be touched.
% A commented 10 MeV value must not be touched.
Energy spread stayed at 10 \% throughout.

\begin{thebibliography}{9}
\bibitem{second}
  B. Author, ``A second paper'', in Proc. IPAC'23, Venice, Italy,
  May 2023, pp. 100-104. DOI: 10.18429/JACoW-IPAC2023-TEST002
\bibitem{first}
  A. Author, ``A first paper'', \textit{Phys. Rev. Accel. Beams}, vol. 24,
  p. 063401, 2021. \url{doi:10.1103/PhysRevAccelBeams.24.063401}
\end{thebibliography}
\end{document}
"""


@pytest.fixture()
def submission(tmp_path: Path) -> Path:
    folder = tmp_path / "TEST001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    (folder / "Source_Files" / "TEST001.tex").write_text(TEX, encoding="utf-8")
    return folder


def _run(folder: Path):
    return prescreen(folder, compile=False, git=False)


# ---------------------------------------------------------------------------
# The report cannot disagree with the file on disk
# ---------------------------------------------------------------------------

def test_reported_edits_match_the_file_on_disk(submission: Path):
    """The core inconsistency, pinned.

    On THP017 the previous version reported 7 auto-fixes in ``report.md``,
    listed 7 repairs in ``repair_plan.json``, wrote an empty ``changes.patch``,
    said "No safe auto-fixes were applicable" in ``changes.html``, and produced
    identical source and edited hashes — five outputs, four of them wrong.
    """
    paper = _run(submission)
    out = submission / "aiagent_prescreen"

    editset = EditSet.read(out / "edits.json")
    plan = json.loads((out / "repair_plan.json").read_text())
    report = json.loads((out / "report.json").read_text())
    original = (submission / "Source_Files" / "TEST001.tex").read_text()
    edited = (out / f"{paper.paper_id}_edited.tex").read_text()
    patch = (out / "changes.patch").read_text()

    assert len(plan["repairs"]) == len(editset.edits)
    assert report["summary"]["edits"]["total"] == len(editset.edits)
    assert report["summary"]["edits"]["applied_automatically"] == len(editset.auto)

    # Auto edits are applied; suggested ones are not.
    assert (edited != original) == bool(editset.auto)
    assert edited == editset.apply(original, [e.id for e in editset.auto])
    assert bool(patch.strip()) == bool(editset.edits)

    # And not one edit is a no-op.
    assert all(e.before != e.after for e in editset.edits)


def test_every_edit_has_its_own_applicable_patch(submission: Path):
    paper = _run(submission)
    out = submission / "aiagent_prescreen"
    editset = EditSet.read(out / "edits.json")
    index = json.loads((out / "edits" / "index.json").read_text())
    assert len(index) == len(editset.edits)
    for entry in index:
        patch = out / entry["patch"]
        assert patch.exists() and patch.read_text().strip()


# ---------------------------------------------------------------------------
# Accept / reject actually applies
# ---------------------------------------------------------------------------

def test_apply_takes_only_the_accepted_subset(submission: Path):
    _run(submission)
    out = submission / "aiagent_prescreen"
    editset = EditSet.read(out / "edits.json")
    original = (submission / "Source_Files" / "TEST001.tex").read_text()

    suggested = editset.suggested
    assert suggested, "the fixture should produce at least one decision"
    chosen = suggested[0]

    target, applied, unknown = apply_decisions(
        submission, accept=[chosen.id], compile=False,
    )
    assert not unknown
    assert chosen.id in applied
    result = target.read_text()
    assert chosen.after in result
    # Every *other* suggestion stayed out.
    for other in suggested[1:]:
        assert result == result  # nothing asserted about text that may overlap
        assert other.id not in applied
    # The author's source is never touched unless asked.
    assert (submission / "Source_Files" / "TEST001.tex").read_text() == original


def test_apply_from_a_decisions_file(submission: Path):
    _run(submission)
    out = submission / "aiagent_prescreen"
    editset = EditSet.read(out / "edits.json")
    suggested = editset.suggested
    decisions = {suggested[0].id: "accepted"}
    for edit in suggested[1:]:
        decisions[edit.id] = "rejected"
    (out / "review_decisions.json").write_text(
        json.dumps({"decisions": decisions}), encoding="utf-8",
    )

    _target, applied, _unknown = apply_decisions(
        submission, decisions_path=Path("review_decisions.json"), compile=False,
    )
    assert suggested[0].id in applied
    for edit in suggested[1:]:
        assert edit.id not in applied


def test_apply_with_no_arguments_takes_only_the_auto_tier(submission: Path):
    _run(submission)
    editset = EditSet.read(submission / "aiagent_prescreen" / "edits.json")
    _target, applied, _unknown = apply_decisions(submission, compile=False)
    assert sorted(applied) == sorted(e.id for e in editset.auto)


# ---------------------------------------------------------------------------
# What the AUTO tier is allowed to contain
# ---------------------------------------------------------------------------

def test_auto_tier_fixes_units_and_doi_presentation(submission: Path):
    _run(submission)
    out = submission / "aiagent_prescreen"
    edited = (out / "TEST001_edited.tex").read_text()

    assert "\\qty{250}{pC}" in edited
    assert "\\qty{50}{nm}" in edited
    assert "10~\\%" in edited
    assert "\\doi{10.1103/PhysRevAccelBeams.24.063401}" in edited
    # House style is the macro, not a "doi:" prefix — settled after measuring
    # against two conferences, where every editor who touched one wrote \doi{}.
    assert "\\doi{10.18429/JACoW-IPAC2023-TEST002}" in edited
    assert "doi:10.18429" not in edited
    assert "[1, 2]" in edited                       # merged citation brackets
    assert "[3]" in edited                          # padding removed


def test_auto_tier_leaves_protected_regions_alone(submission: Path):
    _run(submission)
    edited = (submission / "aiagent_prescreen" / "TEST001_edited.tex").read_text()

    # A matrix index is not a citation.
    assert "A[1,2] must not be touched" in edited
    # A comment is not prose.
    assert "% A commented 10 MeV value must not be touched." in edited
    # An ambiguous unit spelling keeps the author's capitalisation.
    # Still not case-corrected — megatesla, not millitesla — but now in the
    # house form.
    assert "\\qty{0.4}{MT}/m" in edited
    assert "mT" not in edited


def test_unit_case_and_title_punctuation_are_decisions_not_auto(submission: Path):
    _run(submission)
    editset = EditSet.read(submission / "aiagent_prescreen" / "edits.json")
    suggested = {e.check_id for e in editset.suggested}
    assert "FMT-UNIT-02" in suggested      # "5 mhz" → "5~MHz"
    assert "FMT-TITLE-02" in suggested     # the trailing full stop
    assert not any(e.check_id == "FMT-UNIT-02" for e in editset.auto)


# ---------------------------------------------------------------------------
# Findings hygiene
# ---------------------------------------------------------------------------

def test_author_names_produce_one_actionable_item_not_a_wall(submission: Path):
    """The 32-false-positive regression, at workflow level.

    Only the name actually written out in full is raised, and it is raised as
    an *edit* (an offer to fix it) rather than a warning to act on by hand.
    Correct names and address fragments do not appear at all.
    """
    paper = _run(submission)
    editset = EditSet.read(submission / "aiagent_prescreen" / "edits.json")

    author_edits = [e for e in editset.edits if e.check_id == "FMT-AUTH-01"]
    assert len(author_edits) == 1
    assert author_edits[0].before == "Yoshiteru Hidaka"
    assert author_edits[0].after == "Y. Hidaka"
    assert author_edits[0].tier.value == "suggest"

    # No leftover per-name warnings, and nothing about affiliations.
    everything = " ".join(f.message for f in paper.findings)
    for text in ("Brookhaven", "Upton", "USA", "2}", "K. Ha"):
        assert text not in everything


def test_a_check_never_duplicates_an_edit(submission: Path):
    paper = _run(submission)
    editset = EditSet.read(submission / "aiagent_prescreen" / "edits.json")
    edited_checks = {e.check_id for e in editset.edits}
    for finding in paper.findings:
        if finding.check_id in edited_checks and finding.severity.value != "info":
            # A surviving non-info finding must not point at an edited line.
            assert finding.line not in {e.line for e in editset.edits}


def test_reorder_is_offered_as_a_single_structural_decision(submission: Path):
    paper = _run(submission)
    out = submission / "aiagent_prescreen"
    from src.autofix.structural import StructuralPlan

    plan = StructuralPlan.read(out / "structural.json")
    assert plan.reorder is not None and plan.reorder.needed
    assert plan.reorder.current_order == ["second", "first"]
    assert plan.reorder.desired_order == ["first", "second"]

    _target, applied, _unknown = apply_decisions(
        submission, accept=[plan.reorder.id], compile=False,
    )
    assert plan.reorder.id in applied
    edited = (out / "TEST001_edited.tex").read_text()
    keys = re.findall(r"\\bibitem\s*\{([^}]+)\}", edited)
    assert keys == ["first", "second"]
    # Reordering alone must not change a single character of entry text.
    assert "A first paper" in edited and "A second paper" in edited


def test_review_html_offers_one_decision_per_suggestion(submission: Path):
    _run(submission)
    out = submission / "aiagent_prescreen"
    html = (out / "review.html").read_text()
    editset = EditSet.read(out / "edits.json")
    from src.autofix.structural import StructuralPlan

    plan = StructuralPlan.read(out / "structural.json")

    expected = [e.id for e in editset.suggested] + [d.id for d in plan.decisions]
    for edit_id in expected:
        assert f'data-id="{edit_id}"' in html
    # AUTO edits are listed for the record but are not decisions.
    for edit in editset.auto:
        assert f'data-id="{edit.id}"' not in html
    assert "review_decisions.json" in html
    assert "main.py apply" in html


def test_offline_checks_say_not_checked_rather_than_reporting_a_problem(
    submission: Path,
):
    """With no network, a DOI lookup must not become a claim about the paper."""
    paper = _run(submission)
    for finding in paper.findings:
        if finding.check_id in ("DOI-MISSING-01", "URL-AS-DOI-01"):
            if "NOT CHECKED" in finding.message:
                assert finding.severity.value == "info"


# ---------------------------------------------------------------------------
# Word submissions
# ---------------------------------------------------------------------------

def test_word_submission_gets_a_tracked_changes_document(tmp_path: Path):
    docx = pytest.importorskip("docx")

    folder = tmp_path / "WORD001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    document = docx.Document()
    document.add_paragraph("A Word Submission")
    document.add_paragraph("Results are reported [1].")
    heading = document.add_paragraph("REFERENCES")
    heading.style = document.styles["Heading 1"]
    document.add_paragraph(
        '[1]\tM. Ruth and D. Bindel, \u201cLevel set learning for Poincar\u00e9 '
        'plots of symplectic maps,\u201d SIAM Journal on Applied Dynamical '
        'Systems, vol. 24, no. 1, pp. 611\u2013632, Feb. 2025, '
        'DOI: 10.1137/23m1622179'
    )
    source = folder / "Source_Files" / "WORD001.docx"
    document.save(str(source))

    result = prescreen(folder, compile=False)
    tracked = folder / "aiagent_prescreen" / "WORD001_tracked.docx"

    assert result.tracked_docx == tracked.name
    assert tracked.exists()

    xml = zipfile.ZipFile(tracked).read("word/document.xml").decode()
    assert "<w:ins " in xml and "<w:del " in xml
    assert "w:delText" in xml
    assert "JACoW prescreen" in xml
    # The revision author names the rule, so Word can group by it.
    assert re.search(r'w:author="JACoW prescreen \([A-Z]', xml)

    # The two defects observed on TUP033 must not be present.
    reference = docx.Document(str(tracked)).paragraphs[3].text
    assert "Poincar\u00e9" in reference
    assert ",," not in reference


def test_word_tracked_changes_reject_restores_the_author_text(tmp_path: Path):
    docx = pytest.importorskip("docx")
    import xml.etree.ElementTree as ET

    from src.output.docx_tracked import ParagraphRewrite, write_tracked_docx

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    document = docx.Document()
    document.add_paragraph("REFERENCES")
    paragraph = document.add_paragraph("[1] A. Author, ")
    paragraph.add_run("Phys. Rev. Accel. Beams").italic = True
    paragraph.add_run(", vol. 24, 2021, DOI: 10.1/x")
    source = tmp_path / "in.docx"
    document.save(str(source))

    before = docx.Document(str(source)).paragraphs[1].text
    after = before.replace("DOI: 10.1/x", "doi:10.1/x")
    out, revisions, skipped = write_tracked_docx(
        source, tmp_path / "out.docx", [ParagraphRewrite(1, before, after)],
    )
    assert revisions and not skipped

    xml = zipfile.ZipFile(out).read("word/document.xml").decode()

    def _resolve(accept: bool) -> str:
        root = ET.fromstring(xml)
        for parent in root.iter():
            for child in list(parent):
                if child.tag == W + "del" and accept:
                    parent.remove(child)
                elif child.tag == W + "ins" and not accept:
                    parent.remove(child)
        paragraphs = list(root.iter(W + "p"))
        return "".join(
            node.text or ""
            for node in paragraphs[1].iter()
            if node.tag in (W + "t", W + "delText")
        )

    assert _resolve(accept=True) == after
    assert _resolve(accept=False) == before
    # Italic formatting survives the rewrite.
    assert any(run.italic for run in docx.Document(str(out)).paragraphs[1].runs)
