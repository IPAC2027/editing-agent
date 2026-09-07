"""Describing a pulled conference before drawing conclusions from it.

The failure this module exists to prevent is a precision figure quoted over a
sample that does not support it. So the tests are mostly about what gets
*excluded*: a paper nobody edited, a pair whose file never changed, a format
that no check applies to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.corpus.index import (
    BUILDABLE,
    COVERED,
    PARTIAL,
    SERVICE,
    load,
    measurable_sample,
    tag_report,
)


def _write(root: Path, code: str, *, tags=(), original: dict | None = None,
           current: dict | None = None, state: str = "accepted") -> dict:
    for role, files in (("original", original), ("current", current)):
        if files is None:
            continue
        folder = root / code / role / "Source_Files"
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (folder / name).write_text(content, encoding="utf-8")
    return {
        "code": code, "friendly_id": 1, "contribution_id": 100, "title": code,
        "persons": [], "state": state, "editor": "An Editor",
        "tags": [{"code": t, "title": t} for t in tags],
        "revision_count": 2, "revisions": [], "note": "",
    }


@pytest.fixture()
def conference(tmp_path: Path) -> Path:
    records = [
        # A real pair: the editors changed the source.
        _write(tmp_path, "AAA01", tags=["TC14", "QA01"],
               original={"AAA01.tex": r"\title{A paper} 10 MeV"},
               current={"AAA01.tex": r"\title{A paper} 10~MeV"}),
        # A Word pair.
        _write(tmp_path, "BBB02", tags=["TC01"],
               original={"BBB02.docx": "before"},
               current={"BBB02.docx": "after and longer"}),
        # Submitted once, never edited.
        _write(tmp_path, "CCC03", tags=[],
               original={"CCC03.tex": "only ever this"}),
        # A pair whose paper file is byte-identical.
        _write(tmp_path, "DDD04", tags=["TC02"],
               original={"DDD04.tex": "same", "fig.png": "x"},
               current={"DDD04.tex": "same", "fig.png": "different"}),
        # Nothing submitted at all.
        _write(tmp_path, "EEE05", state="not_submitted"),
        # Only a PDF: nothing to compare.
        _write(tmp_path, "FFF06",
               original={"FFF06.pdf": "a"}, current={"FFF06.pdf": "b"}),
    ]
    (tmp_path / "index.json").write_text(
        json.dumps({"event_id": 82, "which": "first-last", "papers": records}),
        encoding="utf-8")
    return tmp_path


def test_only_pairs_with_a_real_edit_are_counted(conference: Path):
    corpus = load(conference)

    assert len(corpus.papers) == 6
    assert sorted(p.code for p in corpus.usable) == ["AAA01", "BBB02"]


def test_a_pair_whose_paper_never_changed_is_excluded_with_its_reason(
        conference: Path):
    """A revision can exist without the text moving. Counting it would quietly
    inflate every recall figure computed later."""
    corpus = load(conference)
    paper = [p for p in corpus.papers if p.code == "DDD04"][0]

    assert paper.paired is True          # both sides are on disk
    assert paper.changed() is False      # but the paper itself is identical
    assert paper.usability() == (False, "the paper file is unchanged between revisions")


def test_a_paper_submitted_once_is_not_evidence_of_anything(conference: Path):
    corpus = load(conference)
    paper = [p for p in corpus.papers if p.code == "CCC03"][0]
    assert paper.usability() == (False, "only one revision — never edited")


def test_a_pdf_only_submission_is_reported_rather_than_compared_on_its_output(
        conference: Path):
    corpus = load(conference)
    paper = [p for p in corpus.papers if p.code == "FFF06"][0]
    assert paper.usability() == (False, "no source file, only a PDF")


def test_the_sample_is_reported_per_format_not_as_one_number(conference: Path):
    """A LaTeX check has no evidence in a Word paper; one figure would overstate
    the sample for every check in the tool."""
    sample = measurable_sample(load(conference))

    assert sample["all pairs"] == 2
    assert sample["LaTeX source checks"] == 1
    assert sample["Word checks"] == 1


def test_a_partial_download_does_not_crash(conference: Path):
    """The index lists papers whose files may not have arrived yet."""
    import shutil

    shutil.rmtree(conference / "BBB02")
    corpus = load(conference)

    assert [p.code for p in corpus.usable] == ["AAA01"]


def test_a_missing_index_says_what_to_run(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="indico-pull"):
        load(tmp_path)


# ---------------------------------------------------------------------------
# The join that makes this a roadmap
# ---------------------------------------------------------------------------

def test_the_tag_report_ranks_frequent_and_buildable_above_frequent_and_covered(
        conference: Path):
    corpus = load(conference)
    corpus.papers[0].tags = ["TC07", "TC14"]      # buildable, and already covered

    rows = tag_report(corpus)
    order = [r.code for r in rows]

    assert order.index("TC07") < order.index("TC14")


def test_a_correction_that_runs_both_ways_is_not_offered_as_buildable(
        conference: Path):
    """TC09 (Figure/Fig.) was on the roadmap and was taken off it.

    JACoW wants 'Figure 1:' in a caption and 'Fig. 1' in running text, so the
    editors correct in both directions and a rule would have to judge context.
    On the editors' own advice it is theirs, not ours.
    """
    from src.indico_client import tags as vocabulary

    assert "TC09" not in vocabulary.BUILDABLE_NEXT
    assert "out of scope" in vocabulary.OUT_OF_REACH["TC09"]

    corpus = load(conference)
    corpus.papers[0].tags = ["TC09"]
    row = {r.code: r for r in tag_report(corpus)}["TC09"]

    assert row.status != "buildable"


def test_a_code_that_is_only_half_implemented_is_not_called_covered(
        conference: Path):
    """TC08 finds an unresolved citation but not a figure nobody referenced.

    Reporting that as 'covered' would hide the gap the report exists to show.
    """
    corpus = load(conference)
    corpus.papers[0].tags = ["TC08", "TC14"]

    rows = {r.code: r for r in tag_report(corpus)}

    assert rows["TC08"].status == PARTIAL
    assert "not implemented" in rows["TC08"].detail
    assert rows["TC14"].status == COVERED


def test_the_services_own_tags_are_marked_as_not_ours(conference: Path):
    rows = {r.code: r for r in tag_report(load(conference))}
    assert rows["QA01"].status == SERVICE


def test_counting_tags_can_be_restricted_to_the_pairs_we_can_learn_from(
        conference: Path):
    """TC02 sits on a paper whose file never changed: it is in the conference
    but it cannot be evidence for anything."""
    corpus = load(conference)

    everything = corpus.tag_counts()
    usable = corpus.tag_counts(usable_only=True)

    assert everything["TC02"] == 1
    assert "TC02" not in usable


def test_every_reported_status_is_one_of_the_known_kinds(conference: Path):
    from src.corpus import index as corpus_index

    known = {corpus_index.COVERED, corpus_index.PARTIAL, corpus_index.BUILDABLE,
             corpus_index.NEEDS_PDF, corpus_index.OUT_OF_SCOPE,
             corpus_index.JUDGEMENT, corpus_index.SERVICE}
    corpus = load(conference)
    corpus.papers[0].tags = list(
        __import__("src.indico_client.tags", fromlist=["VOCABULARY"]).VOCABULARY)

    assert {r.status for r in tag_report(corpus)} <= known


def test_a_local_code_not_in_the_vocabulary_is_reported_not_dropped(
        conference: Path):
    """HIAT2025 carries a duplicated TC_01..TC_04 set that no mapping knows."""
    corpus = load(conference)
    corpus.papers[0].tags = ["TC_01"]

    rows = {r.code: r for r in tag_report(corpus)}

    assert "TC_01" in rows
    assert "local code" in rows["TC_01"].detail
