"""The title and author check: the paper against its Indico record.

The names in the matching tests are the shapes NAPAC2025 actually produced —
each one was a false difference before the rule that handles it. The journey
tests pin the promise the email makes: nothing changes before the time printed
in it, what changes is exactly what it described, and the author can stop it.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import respx

from src.checks.title_authors import (
    FrontMatter,
    IndicoRecord,
    Person,
    compare,
    latex_front_matter,
    latex_source_front_matter,
    latex_title_text,
    looks_like_person,
    person,
    same_person,
    word_front_matter,
)
from src.desk import title_check
from src.desk.indico import ABSTRACTS_FILE, LIVE_FILE, refresh
from src.desk.paper import Paper, close_paper, compose, letter_text, view
from src.desk.state import ReviewState, submission_folders, worklist
from src.workflow.prescreen import prescreen

BASE = "https://indico.jacow.org"
EVENT = 97


# ---------------------------------------------------------------------------
# Who is who
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("paper, indico", [
    ("Y. Luo", "Yun Luo"),
    ("J. S. Berg", "J. Berg"),
    ("D. S. Doran", "Scott Doran"),                      # goes by his middle name
    ("B. N. Temizel Ozdemir", "Buse Naz Temizel Ozdemir"),
    ("G. H. Hoffstaetter de Torquat", "Georg Hoffstaetter"),
    ("D. Edstrom Jr", "Dean Edstrom"),
    ("B. O' Shea", "Brendan O'Shea"),
    ("J.T Li", "Jingtao Li"),
    ("A. Müller", "Anke Muller"),
])
def test_one_person_written_two_ways_is_one_author(paper: str, indico: str):
    assert same_person(person(paper), person(indico))


def test_indico_first_and_last_name_swapped_is_still_the_same_person():
    assert same_person(person("Y. Hao"), Person(name="Hao Yue", given="Hao", family="Yue"))


@pytest.mark.parametrize("paper, indico", [
    ("R. Berlioz", "Jose Berlioz"),
    ("S. Kelham", "Spencer Kellham"),    # a spelling the author should settle
    ("J. Wang", "Li Zhang"),
])
def test_different_people_are_not_merged(paper: str, indico: str):
    assert not same_person(person(paper), person(indico))


@pytest.mark.parametrize("fragment", [
    "RadiaSoft LLC", "Boulder", "USA", "Los Angeles", "Virginia Tech", "CLASSE",
    "Helmholtz-Zentrum Dresden-Rossendorf", "rchic@uic.edu", "Universidad de Guanajuato",
    "IHEP CAS",
    "table Parameter ranges of the IOTA duoplasmatron",
])
def test_address_and_body_fragments_are_not_people(fragment: str):
    assert not looks_like_person(fragment)


@pytest.mark.parametrize("name", ["A. van der Meer", "Henry J. Gaus III", "F.-J. Decker",
                                  "ShuCheng PAI"])
def test_real_names_are_people(name: str):
    assert looks_like_person(name)


# ---------------------------------------------------------------------------
# Reading the paper
# ---------------------------------------------------------------------------

AUTHOR_BLOCK = (r"Y. Hidaka\thanks{y@example.org, see \url{https://x.org/{a}}}, "
                r"J.\ R. Berlioz, Brookhaven National Laboratory, Upton, NY, USA \\"
                "\n" r"K. Ha, Argonne National Laboratory, Lemont, IL, USA")


def test_every_author_group_is_read_not_only_the_first():
    """The template's second group comes after a line break; the general
    parser reads that line as affiliation and lost "K. Ha"."""
    front = latex_front_matter("A title", AUTHOR_BLOCK)

    assert front.authors == ["Y. Hidaka", "J. R. Berlioz", "K. Ha"]


def test_latex_titles_are_read_as_their_text():
    assert latex_title_text(r"Multi-G\NoCaseChange{e}V FFA~Beams\thanks{DOE}") == (
        "Multi-GeV FFA Beams", [])


def test_a_title_macro_that_renders_as_nothing_is_unreadable_not_different():
    front = latex_front_matter(r"\gtpsa: A SciBmad interface", "A. Author, Lab")
    result = compare(front, IndicoRecord(title="GTPSA.jl: A SciBmad interface",
                                         authors=[person("Anna Author")]))

    assert not result.title_differs
    assert "\\gtpsa" in result.unreadable[0]


def test_authblk_authors_are_read_one_per_command():
    """TUP006, TUP009 and others: no author was read at all."""
    source = (r"\documentclass{jacow}\begin{document}\title{Fast spin tracking}"
              r"\author[1]{J.~P.~Devlin\thanks{jpd285@cornell.edu}}\author[1,2]{G.~H.~Hoffstaetter}"
              r"\affil[1]{CLASSE, Cornell University}\maketitle\end{document}")

    assert latex_source_front_matter(source).authors == ["J. P. Devlin", "G. H. Hoffstaetter"]


def test_an_old_author_block_left_in_the_source_is_not_read_twice():
    """TUP077 kept a previous \\author{} beside the current one. LaTeX uses the
    last before \\maketitle, and nothing inside \\iffalse ... \\fi."""
    source = (r"\title{T}\author{E. Hamwi, G. H. Hoffstaetter de Torquat, Cornell, USA}"
              r"\iffalse\author{Old Draft, Nobody}\fi"
              r"\author{E. Hamwi\textsuperscript{1}, G. H. Hoffstaetter\textsuperscript{1,2}}"
              r"\maketitle\author{Not In The Header}")

    assert latex_source_front_matter(source).authors == ["E. Hamwi", "G. H. Hoffstaetter"]


def test_an_author_block_ending_in_a_line_break_still_ends():
    """MOP070: "…, USA \\\\}" was read as an escaped brace, and the author list ran
    on through the whole paper."""
    source = (r"\title{T}\author{N. Banerjee, Fermilab, Batavia, IL, USA \\"
              "\n" r"B. Simons, Northern Illinois University, DeKalb, IL, USA \\}"
              "\n" r"\maketitle Body text, with commas, that is not an author.")

    assert latex_source_front_matter(source).authors == ["N. Banerjee", "B. Simons"]


def test_the_papers_own_macros_are_expanded_in_its_title():
    source = (r"\newcommand{\gtpsa}{GTPSA.jl\xspace}\title{\gtpsa: A SciBmad interface}"
              r"\author{A. Author, Lab}")

    front = latex_source_front_matter(source)

    assert (front.title, front.unreadable) == ("GTPSA.jl: A SciBmad interface", [])


def test_a_line_break_in_a_title_is_not_an_unknown_macro():
    """THP093: "LANSCE\\\\Proton" was reported as the macro "\\Proton"."""
    assert latex_title_text(r"Septum magnet redesign at LANSCE\\Proton Storage Ring") == (
        "Septum magnet redesign at LANSCE Proton Storage Ring", [])


def test_the_main_tex_file_is_the_paper_not_a_template(tmp_path: Path):
    """THAN01 sent four .tex files; the first in the listing was a template."""
    from src.workflow.prescreen import _find_tex

    source = tmp_path / "THAN01" / "original" / "Source_Files"
    source.mkdir(parents=True)
    whole = "\\documentclass{jacow}\\begin{document}\\title{%s}\\end{document}"
    (source / "THAN01_annexes.tex").write_text("\\section{Annex}", encoding="utf-8")
    (source / "THAN01_JACoW_LaTeX_A4.tex").write_text(whole % "Template", encoding="utf-8")
    (source / "THAN01.tex").write_text(whole % "The paper", encoding="utf-8")

    assert _find_tex(source.parent).name == "THAN01.tex"


def test_a_word_title_split_over_paragraphs_is_read_whole(tmp_path: Path):
    """WEP014: the paper code, an empty line, then the title in two parts."""
    docx = pytest.importorskip("docx")
    from src.checks.word_front_checks import read_front_matter

    document = docx.Document()
    for text in ("WEP014", "", "CONSIDERATION OF HTS RAPID-CYCLING MAGNET", "FOR MUON ACCELERATION"):
        document.add_paragraph(text, style="Title")
    document.add_paragraph("H. Piekarz\nFermi National Accelerator Laboratory, Batavia, IL, USA")
    path = tmp_path / "WEP014.docx"
    document.save(str(path))

    front = read_front_matter(path)

    assert front.title == "CONSIDERATION OF HTS RAPID-CYCLING MAGNET FOR MUON ACCELERATION"
    assert front.author_names == "H. Piekarz"


def test_a_word_title_loses_its_footnote_mark():
    assert word_front_matter("COMMISSIONING OF THE HEPS*", "Y. Jiao").title == (
        "COMMISSIONING OF THE HEPS")


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

def _front(title: str, *authors: str, not_names: tuple = ()) -> FrontMatter:
    return FrontMatter(title=title, authors=list(authors), not_names=list(not_names))


def test_capitals_and_punctuation_are_not_a_difference():
    result = compare(_front("Crabbing Schemes for the Electron Ion Collider", "Y. Luo"),
                     IndicoRecord(title="Crabbing schemes for the Electron-Ion Collider",
                                  authors=[person("Yun Luo")]))

    assert not result.differs


def test_a_different_title_makes_the_papers_title_indicos():
    result = compare(_front("Design and development of a feedback system", "Y. Luo"),
                     IndicoRecord(title="Development of a feedback system",
                                  authors=[person("Yun Luo")]))

    assert result.title_differs
    assert result.proposed_indico_title == "Design and development of a feedback system"
    assert not result.check_capitals


def test_a_title_in_capitals_takes_indicos_capitals_and_flags_the_rest():
    result = compare(_front("ANALOG SIGNAL SYSTEM FOR THE IOTA PROTON INJECTOR", "D. Edstrom"),
                     IndicoRecord(title="Analog signal multiplexing system for the IOTA",
                                  authors=[person("Dean Edstrom")]))

    assert result.proposed_indico_title == "Analog signal system for the IOTA PROTON INJECTOR"
    assert result.check_capitals


def test_a_title_with_almost_nothing_in_common_is_a_misreading():
    """THAN01: the parser picked up "THE JACoW COLLABORATION". Proposing that
    as Indico's new title would be the worst thing this check could do."""
    result = compare(_front("THE JACoW COLLABORATION", "C. Petit-Jean-Genaz"),
                     IndicoRecord(title="AI-driven neutrino diagnostics for experiments",
                                  authors=[person("Sudeshna Ganguly")]))

    assert not result.differs
    assert "misread" in result.unreadable[0]


def test_the_combined_list_is_the_paper_then_who_indico_adds():
    record = IndicoRecord(title="T", authors=[
        Person(name="Yue Hao", given="Yue", family="Hao",
               affiliation="Michigan State University", role="coauthor"),
        person("Yun Luo"),
    ])

    result = compare(_front("T", "Y. Luo", "M. Signorelli"), record)

    assert result.paper_only == ["M. Signorelli"]
    assert [p.jacow for p in result.indico_only] == ["Y. Hao"]
    assert result.combined == ["Y. Luo", "M. Signorelli", "Y. Hao"]


def test_someone_the_paper_has_but_could_not_be_parsed_is_not_added():
    """THP093: "E.-H. Huang" came out as "E.-H" and "Huang"."""
    result = compare(_front("T", "A. Author", not_names=("E.-H", "Huang")),
                     IndicoRecord(title="T", authors=[person("Anna Author"),
                                                      person("En-Hui Huang")]))

    assert result.indico_only == []


# ---------------------------------------------------------------------------
# The desk: email, wait, apply
# ---------------------------------------------------------------------------

TEX = r"""% v 2.3  JACoW template
\documentclass[keeplastbox]{jacow}
\begin{document}
\title{Design and Development of a 10~MeV Injector}
\author{Y. Hidaka\thanks{y@example.org}, Brookhaven National Laboratory, Upton, NY, USA \\
        K. Ha, Argonne National Laboratory, Lemont, IL, USA}
\maketitle
\section{INTRODUCTION}
The gun runs at 5~MHz.
\end{document}
"""

ABSTRACT = {
    "title": "Development of a 10 MeV injector",
    "authors": [
        {"first_name": "Yoshiteru", "last_name": "Hidaka",
         "affiliation": "Brookhaven National Laboratory", "role": "primary"},
        {"first_name": "Yue", "last_name": "Hao",
         "affiliation": "Michigan State University", "role": "coauthor"},
    ],
}
T0 = datetime(2026, 11, 2, 9, 40, tzinfo=timezone.utc)


@pytest.fixture()
def pulled(tmp_path: Path) -> Path:
    """One LaTeX paper pulled from Indico, prepared, with its authors fetched."""
    root = tmp_path / "NAPAC2025"
    source = root / "MOP001" / "original" / "Source_Files"
    source.mkdir(parents=True)
    (source / "MOP001.tex").write_text(TEX, encoding="utf-8")
    (root / "MOP001" / "manifest.json").write_text(json.dumps({
        "code": "MOP001", "contribution_id": 101, "title": ABSTRACT["title"],
        "editor": "Ling Wang", "persons": ["Yoshiteru Hidaka", "Yue Hao"],
    }), encoding="utf-8")
    (root / "index.json").write_text(json.dumps(
        {"event_id": EVENT, "base_url": BASE, "editable_type": "paper", "papers": []}),
        encoding="utf-8")
    (root / ABSTRACTS_FILE).write_text(json.dumps(
        {"checked_at": T0.isoformat(), "contributions": {"101": ABSTRACT}}), encoding="utf-8")
    prescreen(submission_folders(root)[0], compile=False, git=False)
    return root


def _folder(root: Path) -> Path:
    return submission_folders(root)[0]


def _panel(folder: Path, now: datetime) -> dict:
    from src.desk.indico import Conference

    paper = Paper(folder)
    return title_check.view(front=title_check.front_for(folder, paper.report),
                            prepared=True, state=paper.state,
                            record=Conference.open(folder.parent.parent).record(folder),
                            paper_id="MOP001", event="NAPAC2025", now=now)


def _act(folder: Path, action: str, now: datetime, **body) -> None:
    from src.desk.indico import Conference

    state = ReviewState.load(folder)
    title_check.act(state, action, body,
                    front=title_check.front_for(folder, Paper(folder).report),
                    record=Conference.open(folder.parent.parent).record(folder), now=now)
    state.save(folder)


def test_the_prepared_report_carries_the_papers_title_and_authors(pulled: Path):
    front = Paper(_folder(pulled)).report["front_matter"]

    assert front["title"] == "Design and Development of a 10 MeV Injector"
    assert front["authors"] == ["Y. Hidaka", "K. Ha"]


def test_a_difference_drafts_an_email_that_says_what_will_change(pulled: Path):
    panel = _panel(_folder(pulled), T0)

    assert panel["status"] == "differs"
    assert panel["status_word"] == "Needs correction: email drafted"
    assert panel["roles_known"] is True
    email = panel["email"]
    # What is wrong ...
    assert "In your paper: Design and Development of a 10 MeV Injector" in email
    assert "In Indico:     Development of a 10 MeV injector" in email
    assert "K. Ha is an author in your paper but not in Indico." in email
    assert ("Y. Hao (Michigan State University) is an author in Indico but not in "
            "your paper.") in email
    # ... and what the paper will be if nobody answers.
    assert ("If we have not heard from you by Wednesday 4 November 2026, 10:00 UTC, "
            "we will correct this, and your paper will be published with:") in email
    assert "  Title:   Design and Development of a 10 MeV Injector" in email
    assert "  Authors: Y. Hidaka, K. Ha, Y. Hao" in email
    assert "in Indico, the title will be changed to the title of your paper" in email
    assert "in Indico, K. Ha will be added to the authors" in email
    assert "in your paper, Y. Hao (Michigan State University) will be added" in email


def test_a_paper_that_matches_indico_is_labelled_done(pulled: Path):
    matching = {"title": "Design and development of a 10 MeV injector", "authors": [
        {"first_name": "Yoshiteru", "last_name": "Hidaka", "role": "primary"},
        {"first_name": "Kyungbo", "last_name": "Ha", "role": "coauthor"}]}
    (pulled / ABSTRACTS_FILE).write_text(json.dumps(
        {"checked_at": T0.isoformat(), "contributions": {"101": matching}}), encoding="utf-8")

    panel = _panel(_folder(pulled), T0)

    assert panel["status"] == "match"
    assert panel["status_word"] == "Author/title check done"
    assert panel["email"] == ""
    assert worklist(pulled)[0].title_authors["status_word"] == "Author/title check done"


def test_a_corrected_paper_is_done_once_indico_is_ticked_off(pulled: Path):
    folder = _folder(pulled)
    _act(folder, "send", T0)
    _act(folder, "apply", T0 + timedelta(hours=49))
    assert _panel(folder, T0 + timedelta(hours=49))["status"] == "applied"

    _act(folder, "tick", T0, key="title", done=True)
    _act(folder, "tick", T0, key="author:K. Ha", done=True)

    panel = _panel(folder, T0 + timedelta(hours=50))
    assert panel["status"] == "done"
    assert panel["status_word"] == "Author/title check done (corrected)"


def test_nothing_is_applied_before_the_deadline_in_the_email(pulled: Path):
    folder = _folder(pulled)
    printed = _panel(folder, T0)["deadline"]
    _act(folder, "send", T0 + timedelta(minutes=5))

    assert ReviewState.load(folder).title_authors.deadline >= printed
    with pytest.raises(ValueError, match="has until"):
        _act(folder, "apply", T0 + timedelta(hours=47))
    assert _panel(folder, T0 + timedelta(hours=47))["status"] == "waiting"
    assert _panel(folder, T0 + timedelta(hours=49))["status"] == "due"


def test_after_48_hours_the_paper_gains_the_authors_and_indico_gets_a_checklist(pulled: Path):
    folder = _folder(pulled)
    _act(folder, "send", T0)
    _act(folder, "apply", T0 + timedelta(hours=49))

    text = compose(Paper(folder))
    assert "K. Ha, Argonne National Laboratory, Lemont, IL, USA \\\\\n  Y. Hao, Michigan State University}" in text

    panel = _panel(folder, T0 + timedelta(hours=49))
    assert panel["status"] == "applied"
    assert [t["key"] for t in panel["indico_tasks"]] == ["title", "author:K. Ha"]
    assert "the author list, which is now the combined list" in letter_text(Paper(folder))

    close_paper(folder, compile_pdf=False)
    final = (folder / "aiagent_prescreen" / "MOP001_final.tex").read_text(encoding="utf-8")
    assert "Y. Hao, Michigan State University" in final


def test_undo_takes_the_authors_back_out(pulled: Path):
    folder = _folder(pulled)
    _act(folder, "send", T0)
    _act(folder, "apply", T0 + timedelta(hours=49))
    _act(folder, "undo", T0 + timedelta(hours=50))

    assert "Y. Hao" not in compose(Paper(folder))


def test_an_author_who_agrees_does_not_have_to_wait(pulled: Path):
    folder = _folder(pulled)
    _act(folder, "send", T0)
    _act(folder, "agreed", T0 + timedelta(hours=2))

    assert _panel(folder, T0 + timedelta(hours=2))["status"] == "applied"


def test_an_author_who_answers_otherwise_stops_the_change(pulled: Path):
    folder = _folder(pulled)
    _act(folder, "send", T0)
    _act(folder, "declined", T0 + timedelta(hours=2))

    assert _panel(folder, T0 + timedelta(hours=60))["status"] == "replied"
    assert "Y. Hao" not in compose(Paper(folder))


def test_a_record_that_changes_after_the_email_is_noticed(pulled: Path):
    """The author fixed Indico themselves: applying the old plan would add
    nothing useful and the desk must not pretend otherwise."""
    folder = _folder(pulled)
    _act(folder, "send", T0)
    fixed = {**ABSTRACT, "authors": ABSTRACT["authors"] + [
        {"first_name": "Kyungbo", "last_name": "Ha", "affiliation": "ANL", "role": "coauthor"}]}
    (pulled / ABSTRACTS_FILE).write_text(json.dumps(
        {"checked_at": T0.isoformat(), "contributions": {"101": fixed}}), encoding="utf-8")

    assert _panel(folder, T0 + timedelta(hours=49))["status"] == "changed"


def test_a_paper_prepared_before_the_check_is_read_from_its_source(pulled: Path):
    """A reading stored by an older version, or the report's own author list
    (which lost every author after the first line of the author block), is not
    trusted: trusting it would ask to add K. Ha's group again."""
    folder = _folder(pulled)
    report_path = folder / "aiagent_prescreen" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["front_matter"] = {"title": "old reading", "authors": ["Y. Hidaka"]}   # no version
    report["authors"] = ["Y. Hidaka"]                    # what the old parser kept
    report_path.write_text(json.dumps(report), encoding="utf-8")

    front = title_check.front_for(folder, report)

    assert front.authors == ["Y. Hidaka", "K. Ha"]
    assert (folder / "aiagent_prescreen" / title_check.FRONT_CACHE).exists()


def test_the_paper_view_and_worklist_carry_the_check(pulled: Path):
    assert view(_folder(pulled))["title_authors"]["status"] == "differs"
    assert worklist(pulled)[0].title_authors["status"] == "differs"


def test_a_paper_indico_does_not_know_has_no_check(tmp_path: Path):
    folder = tmp_path / "IPAC26" / "AAA001-revision-1_author" / "Source_Files"
    folder.mkdir(parents=True)
    (folder / "AAA001.tex").write_text(TEX, encoding="utf-8")

    assert worklist(tmp_path / "IPAC26")[0].title_authors is None


def test_without_fetched_authors_the_pull_names_are_used_and_flagged(pulled: Path):
    (pulled / ABSTRACTS_FILE).unlink()

    panel = _panel(_folder(pulled), T0)

    assert panel["roles_known"] is False
    assert panel["status"] == "differs"


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def test_a_word_paper_gains_the_authors_as_a_tracked_change(tmp_path: Path):
    docx = pytest.importorskip("docx")
    root = tmp_path / "NAPAC2025"
    source = root / "WEP001" / "original" / "Source_Files"
    source.mkdir(parents=True)
    document = docx.Document()
    document.add_paragraph("DESIGN OF A 10 MEV INJECTOR", style="Title")
    document.add_paragraph("Y. Hidaka, K. Ha\nBrookhaven National Laboratory, Upton, NY, USA")
    document.add_paragraph("Abstract text.")
    document.save(str(source / "WEP001.docx"))
    (root / "WEP001" / "manifest.json").write_text(json.dumps({
        "code": "WEP001", "contribution_id": 202, "title": "Design of a 10 MeV injector",
        "persons": []}), encoding="utf-8")
    (root / "index.json").write_text(json.dumps(
        {"event_id": EVENT, "base_url": BASE, "papers": []}), encoding="utf-8")
    (root / ABSTRACTS_FILE).write_text(json.dumps({"checked_at": T0.isoformat(),
        "contributions": {"202": {"title": "Design of a 10 MeV injector", "authors": [
            {"first_name": "Yoshiteru", "last_name": "Hidaka", "role": "primary",
             "affiliation": "BNL"},
            {"first_name": "Kyungbo", "last_name": "Ha", "role": "coauthor", "affiliation": "BNL"},
            {"first_name": "Yue", "last_name": "Hao", "role": "coauthor",
             "affiliation": "Michigan State University"}]}}}), encoding="utf-8")
    folder = submission_folders(root)[0]
    prescreen(folder, compile=False)

    assert Paper(folder).report["front_matter"]["authors"] == ["Y. Hidaka", "K. Ha"]
    _act(folder, "send", T0)
    _act(folder, "apply", T0 + timedelta(hours=49))
    close_paper(folder, compile_pdf=False)

    reviewed = folder / "aiagent_prescreen" / "WEP001_reviewed.docx"
    xml = zipfile.ZipFile(reviewed).read("word/document.xml").decode()
    assert "<w:ins " in xml and "Y. Hao, Michigan State University" in xml
    assert docx.Document(str(reviewed)).paragraphs[0].text == "DESIGN OF A 10 MEV INJECTOR"


# ---------------------------------------------------------------------------
# Fetching the authors from Indico
# ---------------------------------------------------------------------------

EXPORT = {"count": 1, "results": [{"contributions": [{
    "db_id": 101, "friendly_id": 1, "title": "Development of a 10 MeV injector",
    "primaryauthors": [{"first_name": "Yoshiteru", "last_name": "Hidaka",
                        "fullName": "Yoshiteru Hidaka", "affiliation": "BNL"}],
    "coauthors": [{"first_name": "Yue", "last_name": "Hao", "fullName": "Yue Hao",
                   "affiliation": None}],
    "speakers": [{"first_name": "Pat", "last_name": "Speaker", "affiliation": "X"}],
}]}]}


@respx.mock
def test_check_indico_reads_the_authors_with_roles_and_drops_speakers(pulled: Path, monkeypatch):
    monkeypatch.setenv("INDICO_TOKEN", "indico-test-token-0123456789")
    respx.get(f"{BASE}/event/{EVENT}/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=[]))
    export = respx.get(f"{BASE}/export/event/{EVENT}.json").mock(
        return_value=httpx.Response(200, json=EXPORT))

    result = refresh(pulled)

    assert export.calls.last.request.url.params["detail"] == "contributions"
    assert result["authors"] == 1 and result["authors_error"] == ""
    stored = json.loads((pulled / ABSTRACTS_FILE).read_text(encoding="utf-8"))
    assert stored["contributions"]["101"]["authors"] == [
        {"first_name": "Yoshiteru", "last_name": "Hidaka", "affiliation": "BNL",
         "role": "primary"},
        {"first_name": "Yue", "last_name": "Hao", "affiliation": "", "role": "coauthor"},
    ]


@respx.mock
def test_authors_that_cannot_be_fetched_do_not_lose_the_assignments(pulled: Path, monkeypatch):
    monkeypatch.setenv("INDICO_TOKEN", "indico-test-token-0123456789")
    respx.get(f"{BASE}/event/{EVENT}/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/export/event/{EVENT}.json").mock(return_value=httpx.Response(403))

    result = refresh(pulled)

    assert (pulled / LIVE_FILE).exists()
    assert "could not be fetched" in result["authors_error"]
