"""The review desk: state, plain English, and the whole editor journey.

The journey test is the important one here. It walks the sequence the guide
describes — open a paper, decide, note, add an issue, edit a line by hand,
finish, move on — and asserts that what lands on disk is what the editor
actually chose. A desk that loses one decision in forty is worse than no desk.
"""

import json
from pathlib import Path

import pytest

from src.desk import plain
from src.desk.paper import DeskError, Paper, close_paper, compose, letter_text, view
from src.desk.state import (
    EditorNote,
    ManualEdit,
    ReviewState,
    finding_key,
    submission_folders,
    worklist,
)
from src.workflow.prescreen import prescreen

TEX = r"""% v 2.3  JACoW template
\documentclass[keeplastbox]{jacow}
\begin{document}
\title{Beam dynamics of a 10 MeV injector.}
\author{Yoshiteru Hidaka\thanks{y@example.org}, K. Ha\textsuperscript{1}\\
Brookhaven National Laboratory, Upton, NY, USA}
\maketitle
\section{INTRODUCTION}
The gun runs at 5 mhz with a 250 pC bunch \cite{first}\cite{second}.
Later work \cite{second} refines it.
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
def conference(tmp_path: Path) -> Path:
    """A folder of two submissions, one of them screened."""
    root = tmp_path / "IPAC26"
    for name in ("AAA001-revision-1_author", "BBB002-revision-1_author"):
        folder = root / name
        (folder / "Source_Files").mkdir(parents=True)
        (folder / "Source_Files" / f"{name[:6]}.tex").write_text(TEX, encoding="utf-8")
    return root


@pytest.fixture()
def paper_folder(conference: Path) -> Path:
    folder = conference / "AAA001-revision-1_author"
    prescreen(folder, compile=False, git=False)
    return folder


# ---------------------------------------------------------------------------
# Plain English
# ---------------------------------------------------------------------------

def test_every_check_the_agent_emits_has_plain_english():
    """A card with no explanation shows an editor a raw check id.

    This list is every check id the checks and edit generators can produce. If
    one is added without an entry in ``src/desk/plain.py``, an editor sees
    developer prose instead of a sentence, so the omission fails here.
    """
    emitted = {
        "FMT-UNIT-01", "FMT-UNIT-02", "FMT-AUTH-01", "FMT-TITLE-02",
        "FMT-TITLE-03", "FMT-REF-01", "DOI-FMT-01", "DOI-FMT-02", "DOI-FMT-03",
        "REF-PAGES-01", "REF-NUM-01", "REF-NUM-02", "REF-SEC-01",
        "CITE-BRACKET-01", "CITE-SPACE-01", "CITE-LINK-01", "AUTH-02",
        "URL-AS-DOI-01", "DOI-MISSING-01", "FIG-MISSING-01", "FIG-ARCHIVE-01",
        "BIB-MISSING-01", "BIB-PARSE-01", "BIB-EDIT-01",
        "JACOW-CLS-01", "JACOW-CLS-02", "JACOW-CLS-03",
        "BUILD-OK", "BUILD-FAIL", "BUILD-SKIP", "PAGE-LIMIT-01",
        "EDIT-OVERLAP-01", "LLM-REVIEW-01", "LLM-SUPPRESS-01",
        "WORD-TRACK-00", "WORD-TRACK-01", "WORD-TRACK-02",
        # Word-only ids. These were missing from this list, so five checks
        # reached the desk with no explanation and fell through to the
        # "Needs a look" fallback without any test noticing.
        "CITE-ORDER-01", "CITE-TEXT-02", "TITLE-01", "AUTH-01", "DOI-REQ-01",
        "PROC-REQ-01", "PROC-REQ-02", "PROC-REQ-03",
    }
    missing = sorted(emitted - set(plain.EXPLANATIONS))
    assert not missing, f"no plain-English explanation for: {missing}"


def test_explanations_avoid_jargon_and_check_ids():
    for check_id, explanation in plain.EXPLANATIONS.items():
        text = explanation.label + " " + explanation.why
        assert check_id not in text, f"{check_id} names itself in its own text"
        for jargon in ("regex", "EditSet", "stdout", "JSON", "sha256",
                       "dict", "None", "traceback"):
            assert jargon not in text, f"{check_id} says {jargon!r}"
        # A heading starts with a capital, or with punctuation that opens a
        # quoted term — "'et al.' punctuation" is a legitimate heading.
        assert explanation.label[0].isupper() or explanation.label[0] in "'\u2018\""
        assert explanation.why.endswith((".", "?"))


def test_informational_findings_never_belong_to_the_author():
    """One id, two severities: only the serious one reaches an author."""
    assert plain.owner("JACOW-CLS-02", "error") == plain.AUTHOR
    assert plain.owner("JACOW-CLS-02", "info") == plain.TOOL


def test_titles_are_shown_without_latex_markup():
    raw = r"A framework: \\ \NoCaseChange{ONE} for $10^{34}$ operation\thanks{note}"
    readable = plain.readable_title(raw)
    for markup in ("\\", "{", "}", "$", "NoCaseChange", "thanks"):
        assert markup not in readable
    assert "A framework: ONE for" in readable


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def test_state_survives_a_round_trip(tmp_path: Path):
    folder = tmp_path / "paper"
    (folder / "aiagent_prescreen").mkdir(parents=True)
    state = ReviewState(paper_id="AAA001", editor="A. Editor")
    state.decide("E001", "accepted")
    state.set_edit_note("E001", "checked against the printed volume")
    state.add_note(EditorNote(text="Figure 3 unreadable", where="Figure 3"))
    state.add_manual_edit(ManualEdit(line=9, before="a", after="b"))
    state.save(folder)

    loaded = ReviewState.load(folder)
    assert loaded.decision_for("E001") == "accepted"
    assert loaded.edit_notes["E001"].startswith("checked")
    assert [n.id for n in loaded.editor_notes] == ["N001"]
    assert [e.id for e in loaded.manual_edits] == ["M001"]
    assert loaded.status == "in_review"      # touched by the first decision


def test_a_corrupt_state_file_does_not_lock_the_paper(tmp_path: Path):
    folder = tmp_path / "paper"
    (folder / "aiagent_prescreen").mkdir(parents=True)
    path = ReviewState.path_for(folder)
    path.write_text("{ this is not json", encoding="utf-8")

    state = ReviewState.load(folder)
    assert state.status == "new"              # a fresh start, not a crash
    assert path.with_suffix(".json.broken").exists()   # and the wreck is kept


def test_finding_keys_are_stable_and_distinct():
    a = finding_key("FIG-MISSING-01", 12, "\\includegraphics{one}")
    b = finding_key("FIG-MISSING-01", 12, "\\includegraphics{two}")
    assert a == finding_key("FIG-MISSING-01", 12, "\\includegraphics{one}")
    assert a != b


def test_worklist_lists_every_submission(conference: Path):
    assert len(submission_folders(conference)) == 2
    rows = worklist(conference)
    assert {row.paper_id for row in rows} == {"AAA001", "BBB002"}
    assert all(not row.screened for row in rows)
    assert all(row.status_word == "Not prepared yet" for row in rows)


def test_worklist_reflects_progress(paper_folder: Path):
    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.screened
    assert row.applied > 0
    assert row.to_decide > 0
    assert row.decided == 0

    state = ReviewState.load(paper_folder)
    from src.edits import EditSet

    editset = EditSet.read(paper_folder / "aiagent_prescreen" / "edits.json")
    state.decide(editset.suggested[0].id, "accepted")
    state.save(paper_folder)

    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.decided == 1
    assert row.status_word == "In progress"


# ---------------------------------------------------------------------------
# The view an editor sees
# ---------------------------------------------------------------------------

def test_view_of_an_unprepared_paper_explains_itself(conference: Path):
    data = view(conference / "BBB002-revision-1_author")
    assert data["screened"] is False
    assert "Prepare this paper" in data["message"]


def test_view_separates_what_is_done_from_what_needs_deciding(paper_folder: Path):
    data = view(paper_folder)
    assert data["screened"]
    assert data["counts"]["applied"] > 0
    assert data["counts"]["to_decide"] > 0

    import re as _re

    for card in data["decisions"] + data["applied"]:
        # A heading must be words, not a check id: "DOI written the JACoW way"
        # is fine, "DOI-FMT-01" is not.
        assert card["heading"]
        assert not _re.fullmatch(r"[A-Z]+(?:-[A-Z0-9]+)+", card["heading"])
    for card in data["decisions"]:
        assert card["decision"] == "undecided"
        assert card["why"]
    for card in data["findings"]:
        assert card["owner"] in (plain.TOOL, plain.EDITOR, plain.AUTHOR)
        assert card["owner_label"]


def test_view_offers_the_source_for_hand_editing(paper_folder: Path):
    data = view(paper_folder)
    assert data["source"]["editable"] is True
    lines = data["source"]["lines"]
    assert lines and lines[0]["n"] == 1
    # The automatic unit fix is already in the text the editor is shown.
    assert any("250~pC" in line["text"] for line in lines)
    assert any(line["changed"] for line in lines)


def test_the_letter_is_signed_with_the_name_from_the_desk(paper_folder: Path):
    assert "The editorial team" in view(paper_folder)["letter"]
    assert "A. Editor" in view(paper_folder, default_editor="A. Editor")["letter"]


# ---------------------------------------------------------------------------
# The whole journey
# ---------------------------------------------------------------------------

def test_an_editor_works_through_a_paper_and_closes_it(paper_folder: Path):
    from src.edits import EditSet

    original = (paper_folder / "Source_Files" / "AAA001.tex").read_text()
    editset = EditSet.read(paper_folder / "aiagent_prescreen" / "edits.json")
    suggestions = view(paper_folder)["decisions"]
    assert len(suggestions) >= 2, "the fixture should offer several decisions"

    state = ReviewState.load(paper_folder)
    state.editor = "A. Editor"

    # Accept the first, reject the second and say why.
    accepted, rejected = suggestions[0], suggestions[1]
    state.decide(accepted["id"], "accepted")
    state.decide(rejected["id"], "rejected")
    state.set_edit_note(rejected["id"], "author confirmed their spelling is deliberate")

    # Something the agent missed.
    state.add_note(EditorNote(
        text="Figure 2 axis labels are unreadable at print size.",
        where="Figure 2", severity="must_fix", for_author=True,
    ))
    # And something only a human would change.
    paper = Paper(paper_folder)
    working = compose(paper).splitlines()
    target = next(i for i, line in enumerate(working, start=1)
                  if "INTRODUCTION" in line)
    state.add_manual_edit(ManualEdit(
        line=target, before=working[target - 1],
        after=working[target - 1].replace("INTRODUCTION", "OVERVIEW"),
        note="house style",
    ))
    state.save(paper_folder)

    # --- what the editor is shown now ---------------------------------
    data = view(paper_folder)
    assert data["counts"]["accepted"] == 1
    assert data["counts"]["rejected"] == 1
    assert data["counts"]["my_notes"] == 1
    assert data["counts"]["my_edits"] == 1
    assert data["status_word"] == "In progress"
    assert any(card["note"] for card in data["decisions"])

    # --- and the composed text matches those choices exactly ----------
    result = compose(Paper(paper_folder))
    assert "OVERVIEW" in result                      # the hand edit
    assert "250~pC" in result                        # an automatic fix
    accepted_edit = editset.get(accepted["id"])
    if accepted_edit:
        assert accepted_edit.after in result
    rejected_edit = editset.get(rejected["id"])
    if rejected_edit:
        assert rejected_edit.before in result        # left as submitted

    # --- closing writes the files and records the outcome -------------
    outcome = close_paper(paper_folder, status="needs_author", compile_pdf=False)
    assert outcome["status"] == "needs_author"
    assert "AAA001_final.tex" in outcome["written"]
    assert "author_letter.txt" in outcome["written"]
    assert "review_summary.md" in outcome["written"]

    out_dir = paper_folder / "aiagent_prescreen"
    final = (out_dir / "AAA001_final.tex").read_text()
    assert final == result

    letter = (out_dir / "author_letter.txt").read_text()
    assert "Figure 2 axis labels are unreadable" in letter
    assert "A. Editor" in letter
    assert "\\includegraphics" not in letter, "the letter must not contain markup"
    assert "FMT-" not in letter, "the letter must not contain check ids"

    summary = (out_dir / "review_summary.md").read_text()
    assert "author confirmed their spelling is deliberate" in summary
    assert "Waiting on author" in summary
    assert "house style" in summary

    # --- the author's own file was never touched ----------------------
    assert (paper_folder / "Source_Files" / "AAA001.tex").read_text() == original

    # --- and it shows up in the worklist as finished-with-the-author --
    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.status_word == "Waiting on author"
    assert row.editor == "A. Editor"


def test_a_hand_edit_is_verified_against_the_line_it_was_made_on(paper_folder: Path):
    state = ReviewState.load(paper_folder)
    state.add_manual_edit(ManualEdit(
        line=3, before="a line that is not in this paper", after="something else",
    ))
    state.save(paper_folder)
    # The edit is kept in the record but cannot be applied, and composing must
    # not raise or corrupt anything.
    result = compose(Paper(paper_folder))
    assert "something else" not in result
    from src.desk.paper import stale_manual_edits

    assert stale_manual_edits(Paper(paper_folder)) == ["M001"]


def test_reopening_a_finished_paper_keeps_everything(paper_folder: Path):
    state = ReviewState.load(paper_folder)
    state.decide("E001", "accepted")
    state.add_note(EditorNote(text="something"))
    state.save(paper_folder)
    close_paper(paper_folder, compile_pdf=False)

    state = ReviewState.load(paper_folder)
    assert state.status == "done"
    state.status = "in_review"
    state.closed_at = ""
    state.save(paper_folder)

    state = ReviewState.load(paper_folder)
    assert state.decision_for("E001") == "accepted"
    assert len(state.editor_notes) == 1


def test_rescreening_keeps_decisions_and_notes(paper_folder: Path):
    from src.edits import EditSet

    editset = EditSet.read(paper_folder / "aiagent_prescreen" / "edits.json")
    target = editset.suggested[0].id
    state = ReviewState.load(paper_folder)
    state.editor = "A. Editor"
    state.decide(target, "rejected")
    state.set_edit_note(target, "keep it")
    state.add_note(EditorNote(text="mine"))
    state.save(paper_folder)

    prescreen(paper_folder, compile=False, git=False)

    state = ReviewState.load(paper_folder)
    assert state.editor == "A. Editor"
    assert state.decision_for(target) == "rejected"
    assert state.edit_notes[target] == "keep it"
    assert [n.text for n in state.editor_notes] == ["mine"]


# ---------------------------------------------------------------------------
# Word submissions at the desk
# ---------------------------------------------------------------------------

def test_a_word_paper_becomes_decisions_and_a_reviewed_document(tmp_path: Path):
    docx = pytest.importorskip("docx")
    import zipfile

    folder = tmp_path / "WRD001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    document = docx.Document()
    document.add_paragraph("A Word submission")
    document.add_paragraph("Results [1], [2].")
    heading = document.add_paragraph("REFERENCES")
    heading.style = document.styles["Heading 1"]
    document.add_paragraph(
        '[1]\tM. Ruth, \u201cLevel set learning,\u201d SIAM Journal on Applied '
        'Dynamical Systems, vol. 24, no. 1, pp. 611\u2013632, Feb. 2025, '
        'DOI: 10.1137/23m1622179'
    )
    document.add_paragraph(
        '[2]\tP. Helander, \u201cOn heat conduction. Part 1,\u201d Journal of '
        'Plasma Physics, vol. 88, no. 1, Feb. 2022, '
        'https://doi.org/10.1017/s002237782100129x'
    )
    source = folder / "Source_Files" / "WRD001.docx"
    document.save(str(source))

    prescreen(folder, compile=False)

    data = view(folder)
    assert data["screened"], "a Word paper must be visible at the desk"
    assert data["kind"] == "word"
    assert data["source"]["editable"] is False
    assert "edited in Word" in data["source"]["note"]
    assert data["counts"]["to_decide"] >= 1

    # Accept one correction, reject the other.
    ids = [card["id"] for card in data["decisions"]]
    state = ReviewState.load(folder)
    state.decide(ids[0], "accepted")
    for other in ids[1:]:
        state.decide(other, "rejected")
    state.save(folder)

    outcome = close_paper(folder, compile_pdf=False)
    reviewed = folder / "aiagent_prescreen" / "WRD001_reviewed.docx"
    assert reviewed.name in outcome["written"]
    assert reviewed.exists()

    xml = zipfile.ZipFile(reviewed).read("word/document.xml").decode()
    assert "<w:ins " in xml and "<w:del " in xml
    # One correction accepted means one paragraph carries revisions.
    revised_paragraphs = sum(
        1 for para in docx.Document(str(reviewed)).paragraphs
        if "w:ins" in para._element.xml
    )
    assert revised_paragraphs == 1
    # A tab is a tab element, not a literal character, so the hanging indent
    # of a numbered reference list survives the rewrite.
    assert "<w:tab/>" in xml


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

def test_closing_an_unprepared_paper_says_so(conference: Path):
    with pytest.raises(DeskError, match="not been prepared"):
        close_paper(conference / "BBB002-revision-1_author", compile_pdf=False)


def test_editing_the_author_source_makes_the_conflict_visible(paper_folder: Path):
    source = paper_folder / "Source_Files" / "AAA001.tex"
    source.write_text("\\documentclass{jacow}\n\\begin{document}\nrewritten\n"
                      "\\end{document}\n", encoding="utf-8")
    with pytest.raises(DeskError, match="Prepare this paper"):
        compose(Paper(paper_folder))


# ---------------------------------------------------------------------------
# Putting back an automatic correction
#
# The AUTO tier means "the editor is not asked".  It must never come to mean
# "the editor is not allowed to say no": a rule that is right on 999 papers
# and wrong on this one is exactly the case an editor is there for.
# ---------------------------------------------------------------------------

def _first_auto(folder: Path):
    from src.edits import EditSet

    editset = EditSet.read(folder / "aiagent_prescreen" / "edits.json")
    assert editset.auto, "the fixture is meant to produce automatic corrections"
    return editset.auto[0]


def test_automatic_corrections_are_listed_with_everything_needed_to_undo_one(
        paper_folder: Path):
    data = view(paper_folder)

    assert data["applied"], "an automatic correction the editor cannot see is a trap"
    card = data["applied"][0]
    for field in ("id", "check_id", "heading", "why", "before", "after", "decision"):
        assert card[field] != "" and card[field] is not None, field
    assert card["decision"] == "applied"
    assert card["before"] != card["after"]


def test_putting_one_back_restores_the_authors_text_in_the_file(paper_folder: Path):
    auto = _first_auto(paper_folder)
    paper = Paper(paper_folder)
    with_it = compose(paper)
    assert auto.after in with_it

    state = ReviewState.load(paper_folder)
    state.decide(auto.id, "reverted")
    state.save(paper_folder)

    without_it = compose(Paper(paper_folder))
    assert without_it != with_it
    assert without_it.count(auto.before) > with_it.count(auto.before)


def test_the_other_automatic_corrections_are_unaffected(paper_folder: Path):
    from src.edits import EditSet

    editset = EditSet.read(paper_folder / "aiagent_prescreen" / "edits.json")
    if len(editset.auto) < 2:
        pytest.skip("needs two automatic corrections")
    first, second = editset.auto[0], editset.auto[1]

    state = ReviewState.load(paper_folder)
    state.decide(first.id, "reverted")
    state.save(paper_folder)

    text = compose(Paper(paper_folder))
    assert second.after in text


def test_the_count_moves_from_applied_to_put_back(paper_folder: Path):
    before = view(paper_folder)["counts"]
    auto = _first_auto(paper_folder)

    state = ReviewState.load(paper_folder)
    state.decide(auto.id, "reverted")
    state.save(paper_folder)

    after = view(paper_folder)["counts"]
    assert after["applied"] == before["applied"] - 1
    assert after["reverted"] == before.get("reverted", 0) + 1
    # And it is not miscounted as a suggestion the editor turned down.
    assert after["rejected"] == before["rejected"]


def test_the_letter_does_not_claim_a_correction_that_was_put_back(paper_folder: Path):
    from src.desk import plain

    auto = _first_auto(paper_folder)
    phrase = plain.explain(auto.check_id).fixed_phrase()
    if not phrase:
        pytest.skip("this check has no letter phrasing of its own")

    # Nothing else may be producing the same phrase, or the assertion is empty.
    others = [
        e for e in Paper(paper_folder).auto_edits
        if e.id != auto.id and plain.explain(e.check_id).fixed_phrase() == phrase
    ]
    state = ReviewState.load(paper_folder)
    for edit in [auto, *others]:
        state.decide(edit.id, "reverted")
    state.save(paper_folder)

    assert phrase not in letter_text(Paper(paper_folder))


def test_the_summary_records_what_was_put_back_and_why(paper_folder: Path):
    auto = _first_auto(paper_folder)
    state = ReviewState.load(paper_folder)
    state.decide(auto.id, "reverted")
    state.set_edit_note(auto.id, "the author means megatesla here")
    state.save(paper_folder)

    close_paper(paper_folder, compile_pdf=False)
    summary = (paper_folder / "aiagent_prescreen" / "review_summary.md").read_text(
        encoding="utf-8")

    assert "put back" in summary.lower()
    assert "the author means megatesla here" in summary


def test_a_revert_survives_rescreening(paper_folder: Path):
    auto = _first_auto(paper_folder)
    state = ReviewState.load(paper_folder)
    state.decide(auto.id, "reverted")
    state.save(paper_folder)

    prescreen(paper_folder, compile=False, git=False)

    assert ReviewState.load(paper_folder).auto_decision(auto.id) == "reverted"


def test_a_revert_can_itself_be_undone(paper_folder: Path):
    auto = _first_auto(paper_folder)
    state = ReviewState.load(paper_folder)
    state.decide(auto.id, "reverted")
    state.decide(auto.id, "undecided")     # what "apply it again" sends
    state.save(paper_folder)

    assert ReviewState.load(paper_folder).auto_decision(auto.id) == "applied"
    assert auto.after in compose(Paper(paper_folder))


def test_the_standalone_review_page_offers_the_same_undo(paper_folder: Path):
    """review.html is the no-desk path; it must not be a dead end either."""
    page = (paper_folder / "aiagent_prescreen" / "review.html").read_text(
        encoding="utf-8")
    auto = _first_auto(paper_folder)

    assert f"data-revert='{auto.id}'" in page
    assert "put back" in page
    assert "--reject" in page          # the command it builds for you


def test_apply_honours_a_reverted_automatic_edit_from_a_decisions_file(
        paper_folder: Path):
    import json

    from src.workflow.prescreen import apply_decisions

    auto = _first_auto(paper_folder)
    path = paper_folder / "aiagent_prescreen" / "review_decisions.json"
    path.write_text(json.dumps({"decisions": {auto.id: "reverted"}}),
                    encoding="utf-8")

    _written, applied, _skipped = apply_decisions(
        paper_folder, decisions_path=path, compile=False)

    assert auto.id not in applied
