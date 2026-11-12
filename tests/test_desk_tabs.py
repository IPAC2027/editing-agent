"""The paper page's four tabs: title & authors, references, the paper, the editor's panel.

What is checked here is what lands on disk and in the payload the page draws
from: a reference accepted, kept or rewritten by the editor; a suggestion
accepted in the editor's own words; the source shown line by line with every
suggestion in place; a paper set aside for the author; the JACoW tags.
"""

import http.client
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk.paper import Paper, close_paper, compose, compose_bib, view
from src.desk.server import DeskHandler, JobRunner
from src.desk.state import ManualEdit, ReviewState, worklist
from src.workflow.prescreen import prescreen

from tests.test_desk import TEX


@pytest.fixture()
def paper_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "IPAC26" / "AAA001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    (folder / "Source_Files" / "AAA001.tex").write_text(TEX, encoding="utf-8")
    prescreen(folder, compile=False, git=False)
    return folder


def _row(data: dict, key: str) -> dict:
    return next(r for r in data["references"]["rows"] if r["key"] == key)


# ---------------------------------------------------------------------------
# References: as written, beside what it becomes
# ---------------------------------------------------------------------------

def test_every_bibitem_is_recorded_with_its_source_and_result(paper_folder: Path):
    records = json.loads((paper_folder / "aiagent_prescreen" / "references.json")
                         .read_text(encoding="utf-8"))["references"]
    assert [r["key"] for r in records] == ["second", "first"]
    assert all(r["origin"] == "bibitem" and r["source"] for r in records)

    data = view(paper_folder)
    refs = data["references"]
    assert refs["recorded"] and refs["origin"] == "bibitem"
    second = _row(data, "second")
    # Rewritten in Appendix B's layout with nothing missing: green, to decide.
    assert second["status"] == "fixed"
    assert second["kind"] == "Conference proceedings"
    assert "\\emph{Proc.\\ IPAC'23}" in second["proposed"]
    assert second["suggest_ids"] and second["decision"] == "undecided"
    assert refs["counts"]["undecided"] == 1
    # The DOI fix inside it is part of the rewrite, not a rival edit that
    # would throw the rewrite away.
    assert second["suggest_ids"] == [second["edit_id"]]


def test_a_reference_with_only_a_narrow_fix_still_shows_what_it_becomes(paper_folder: Path):
    first = _row(view(paper_folder), "first")
    assert first["auto"] and first["decision"] == "applied"
    assert "\\doi{10.1103/PhysRevAccelBeams.24.063401}" in first["proposed"]
    assert first["current"] == first["proposed"]


def test_accepting_and_rewriting_a_reference(paper_folder: Path):
    second = _row(view(paper_folder), "second")
    state = ReviewState.load(paper_folder)
    state.decide(second["edit_id"], "accepted")
    state.save(paper_folder)
    text = compose(Paper(paper_folder))
    assert "\\emph{Proc.\\ IPAC'23}" in text

    # The editor's own text replaces the whole reference, whatever was suggested.
    mine = "B. Author, ``A second paper'', presented at IPAC'23, unpublished."
    state = ReviewState.load(paper_folder)
    state.set_ref_text("bibitem:second", mine)
    state.save(paper_folder)
    text = compose(Paper(paper_folder))
    assert mine in text and "\\emph{Proc.\\ IPAC'23}" not in text
    assert "\\bibitem{second}\n  " + mine in text          # its line break and indent kept
    data = view(paper_folder)
    assert _row(data, "second")["own"] == mine
    assert _row(data, "second")["current"] == mine


def test_findings_are_sorted_to_their_tab(paper_folder: Path):
    data = view(paper_folder)
    scopes = {d["check_id"]: d["scope"] for d in data["decisions"]}
    assert scopes["FMT-TITLE-02"] == "title"
    assert scopes["FMT-AUTH-01"] == "title"
    assert scopes["FMT-UNIT-02"] == "body"
    assert scopes["FMT-REF-01"] == "reference"
    assert scopes["REF-NUM-02"] == "reference"
    url = next(f for f in data["findings"] if f["check_id"] == "URL-AS-DOI-01")
    assert (url["scope"], url["ref"]) == ("reference", "bibitem:first")


# ---------------------------------------------------------------------------
# The paper: the source line by line, every suggestion in place
# ---------------------------------------------------------------------------

def test_the_body_lines_are_the_text_as_it_stands(paper_folder: Path):
    body = view(paper_folder)["body"]
    assert body["editable"]
    current = compose(Paper(paper_folder)).splitlines()
    assert [line["text"] for line in body["lines"]] == current
    # An undecided suggestion is shown where it is, with what it would become.
    unit = next(seg for line in body["lines"] for seg in line["segs"]
                if seg.get("state") == "undecided" and seg.get("proposed") == "\\qty{5}{MHz}")
    assert unit["t"] == "5 mhz" and unit["scope"] == "body"
    # An automatic correction is shown applied, with what it was.
    applied = next(seg for line in body["lines"] for seg in line["segs"]
                   if seg.get("state") == "applied" and seg.get("was") == "250 pC")
    assert applied["t"] == "\\qty{250}{pC}"
    assert [j["label"] for j in body["jumps"]][:2] == ["Title", "Authors"]


def test_a_hand_edit_shows_on_its_line(paper_folder: Path):
    lines = compose(Paper(paper_folder)).splitlines()
    n = next(i for i, line in enumerate(lines, start=1) if "INTRODUCTION" in line)
    state = ReviewState.load(paper_folder)
    edit = state.add_manual_edit(ManualEdit(line=n, before=lines[n - 1],
                                            after=lines[n - 1].replace("INTRODUCTION", "OVERVIEW")))
    state.save(paper_folder)
    line = view(paper_folder)["body"]["lines"][n - 1]
    assert line["mine"] == edit.id and "OVERVIEW" in line["text"]


def test_a_suggestion_accepted_in_the_editors_words(paper_folder: Path):
    data = view(paper_folder)
    unit = next(d for d in data["decisions"] if d["check_id"] == "FMT-UNIT-02")
    state = ReviewState.load(paper_folder)
    state.set_edit_text(unit["id"], "\\qty{5}{\\mega\\hertz}")
    state.save(paper_folder)
    text = compose(Paper(paper_folder))
    assert "\\qty{5}{\\mega\\hertz}" in text and "5 mhz" not in text
    card = next(d for d in view(paper_folder)["decisions"] if d["id"] == unit["id"])
    assert card["decision"] == "accepted" and card["edited_text"] == "\\qty{5}{\\mega\\hertz}"
    # Rejecting it afterwards drops the editor's wording too.
    state = ReviewState.load(paper_folder)
    state.decide(unit["id"], "rejected")
    assert unit["id"] not in state.edit_texts


# ---------------------------------------------------------------------------
# The editor's panel: tags
# ---------------------------------------------------------------------------

def test_tags_are_proposed_from_what_was_corrected(paper_folder: Path):
    tags = view(paper_folder)["tags"]
    assert "TC12" in tags["chosen"]                    # units corrected automatically
    assert "TC12" in tags["proposed"]
    assert not {"QA01", "QA02", "QA03", "PRC"} & {v["code"] for v in tags["vocabulary"]}

    state = ReviewState.load(paper_folder)
    state.tags["TC12"] = False                         # unticked
    state.tags["MP02"] = True                          # ticked by hand
    state.save(paper_folder)
    chosen = view(paper_folder)["tags"]["chosen"]
    assert "TC12" not in chosen and "MP02" in chosen


# ---------------------------------------------------------------------------
# Through the desk's server: hold, references, tags
# ---------------------------------------------------------------------------

@pytest.fixture()
def desk(paper_folder: Path, tmp_path: Path):
    handler = partial(DeskHandler, root=paper_folder.parent, jobs=JobRunner(llm=False),
                      home=tmp_path / "home")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _post(port: int, path: str, body: dict) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", path, body=json.dumps(body), headers={
        "Host": f"127.0.0.1:{port}", "Content-Type": "application/json",
        "Origin": f"http://127.0.0.1:{port}"})
    response = conn.getresponse()
    data = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, data


def test_setting_a_paper_aside_and_taking_it_up_again(desk: int, paper_folder: Path):
    status, data = _post(desk, "/api/hold", {"folder": str(paper_folder), "action": "set",
                                             "reason": "waiting for the author"})
    assert status == 200 and data["hold"]["since"] and data["hold"]["reason"]
    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.hold and not row.hold["over"]
    # It stays this editor's paper: the claim is not released.
    from src.desk import claim as claim_module

    assert claim_module.current(paper_folder) is not None

    status, data = _post(desk, "/api/hold", {"folder": str(paper_folder), "action": "clear"})
    assert status == 200 and data["hold"] is None


def test_reference_text_and_tags_through_the_server(desk: int, paper_folder: Path):
    folder = str(paper_folder)
    status, data = _post(desk, "/api/ref-text", {"folder": folder, "ref": "bibitem:second",
                                                 "text": "\\bibitem{x} wrong"})
    assert status == 400 and "\\bibitem" in data["error"]
    status, data = _post(desk, "/api/ref-text", {"folder": folder, "ref": "bibitem:second",
                                                 "text": "B. Author, ``Mine''."})
    assert status == 200 and _row(data, "second")["own"] == "B. Author, ``Mine''."
    status, data = _post(desk, "/api/ref-text", {"folder": folder, "ref": "bibitem:second",
                                                 "text": None})
    assert status == 200 and _row(data, "second")["own"] is None

    status, data = _post(desk, "/api/tags", {"folder": folder, "code": "QA01", "on": True})
    assert status == 400                                # the QA gate's own tags are not ours
    status, data = _post(desk, "/api/tags", {"folder": folder, "code": "MP02", "on": True})
    assert status == 200 and "MP02" in data["tags"]["chosen"]
    status, data = _post(desk, "/api/tags", {"folder": folder, "reset": True})
    assert status == 200 and "MP02" not in data["tags"]["chosen"]


def test_a_line_moved_by_an_addition_can_still_be_edited(desk: int, paper_folder: Path):
    lines = compose(Paper(paper_folder)).splitlines()
    n = next(i for i, line in enumerate(lines, start=1) if "INTRODUCTION" in line)
    status, data = _post(desk, "/api/my-edit", {
        "folder": str(paper_folder), "line": n + 3, "before": lines[n - 1],
        "after": lines[n - 1].replace("INTRODUCTION", "OVERVIEW")})
    assert status == 200, data
    assert "OVERVIEW" in compose(Paper(paper_folder))


# ---------------------------------------------------------------------------
# A biblatex paper: the .bib entries on the References tab
# ---------------------------------------------------------------------------

BIBLATEX_TEX = r"""\documentclass[biblatex]{jacow}
\addbibresource{refs.bib}
\begin{document}
\title{A paper}
\author{A. Author}
\maketitle
\section{INTRODUCTION}
As shown before \cite{alpha}.
\printbibliography
\end{document}
"""

BIB = """@inproceedings{alpha,
  author = {Alpha, A. and Beta, B. T.},
  title = {An Overview of Modern Control Systems},
  booktitle = {Proc. ICALEPCS'23},
  address = {Cape Town, South Africa},
  month = oct,
  year = {2023},
  pages = {57--59},
  doi = {10.18429/JACoW-ICALEPCS2023-MO1BCO01}
}
"""


@pytest.fixture()
def biblatex_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "IPAC26" / "BBB002-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    (folder / "Source_Files" / "BBB002.tex").write_text(BIBLATEX_TEX, encoding="utf-8")
    (folder / "BibTeX_file_only_for_LaTeX_papers").mkdir()
    (folder / "BibTeX_file_only_for_LaTeX_papers" / "refs.bib").write_text(BIB, encoding="utf-8")
    prescreen(folder, compile=False, git=False)
    return folder


def test_bib_entries_are_decided_on_the_references_tab(biblatex_folder: Path):
    data = view(biblatex_folder)
    refs = data["references"]
    assert refs["origin"] == "bib"
    alpha = _row(data, "alpha")
    assert alpha["source"].startswith("@inproceedings{alpha")
    assert alpha["kind"] == "Conference proceedings"
    assert alpha["text"].startswith("A. Alpha and B. T. Beta")
    if alpha["edit_id"]:
        # .bib edits have ids of their own, never a .tex edit's.
        assert alpha["edit_id"].startswith("B")
        assert alpha["edit_id"] in {d["id"] for d in data["decisions"] + data["applied"]}

    state = ReviewState.load(biblatex_folder)
    for edit_id in alpha["suggest_ids"]:
        state.decide(edit_id, "accepted")
    mine = alpha["proposed"] or alpha["source"]
    mine = mine.replace("An Overview of Modern Control Systems", "{An overview of modern control systems}")
    state.set_ref_text("bib:alpha", mine)
    state.save(biblatex_folder)
    assert "{An overview of modern control systems}" in compose_bib(Paper(biblatex_folder))

    result = close_paper(biblatex_folder, compile_pdf=False)
    assert "refs_final.bib" in result["written"]
    final = (biblatex_folder / "aiagent_prescreen" / "refs_final.bib").read_text(encoding="utf-8")
    assert "{An overview of modern control systems}" in final
