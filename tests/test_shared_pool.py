"""Several editors' desks on one shared pool of papers.

The pool sits on the chief editor's computer, shared over the LAN; every
editor runs their own desk on it. These tests stand in for that room: two
desks with different home folders (so different names and desk ids) opened on
the same pool.
"""

from __future__ import annotations

import http.client
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk import claim as claim_module
from src.desk import files
from src.desk import me as me_module
from src.desk import title_check
from src.desk.server import DeskHandler, JobRunner
from src.desk.state import ReviewState, worklist

TEX = ("\\documentclass{jacow}\n\\title{Beam Dynamics in a Small Ring}\n"
       "\\author{A. Author, B. Author}\n\\begin{document}\n\\maketitle\n"
       "\\end{document}\n")


@pytest.fixture()
def pool(tmp_path: Path) -> Path:
    """A pulled conference with two papers, as the chief's computer holds it."""
    root = tmp_path / "NAPAC2025"
    for code in ("MOP001", "TUP002"):
        source = root / code / "original" / "Source_Files"
        source.mkdir(parents=True)
        (source / f"{code}.tex").write_text(TEX, encoding="utf-8")
        (root / code / "manifest.json").write_text(json.dumps({"code": code}),
                                                   encoding="utf-8")
    (root / "index.json").write_text(json.dumps({"event_id": 97, "papers": []}),
                                     encoding="utf-8")
    return root


def paper(pool: Path, code: str = "MOP001") -> Path:
    return pool / code / "original"


def editor(tmp_path: Path, name: str) -> me_module.Me:
    home = tmp_path / f"home-{name.split()[0].lower()}"
    me_module.update_settings(home, editor=name)
    return me_module.current(home)


# ---------------------------------------------------------------------------
# Files several desks read at once
# ---------------------------------------------------------------------------

def test_a_file_is_replaced_whole_and_leaves_nothing_behind(tmp_path: Path):
    target = tmp_path / "aiagent_prescreen" / "review_state.json"
    files.write_text(target, "first")
    files.write_text(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert [p.name for p in target.parent.iterdir()] == ["review_state.json"]


def test_review_state_is_saved_whole(pool: Path):
    state = ReviewState(editor="Ling Wang")
    state.decide("E001", "accepted")
    state.save(paper(pool))

    out = paper(pool) / "aiagent_prescreen"
    assert sorted(p.name for p in out.iterdir()) == ["review_state.json"]
    assert ReviewState.load(paper(pool)).decisions == {"E001": "accepted"}


def test_paths_are_recorded_relative_to_the_paper(pool: Path):
    source = paper(pool) / "Source_Files" / "MOP001.tex"

    assert files.relative_to_paper(source, paper(pool)) == "Source_Files/MOP001.tex"
    assert files.relative_to_paper(pool / "index.json", paper(pool)) == str(pool / "index.json")


@pytest.mark.parametrize("stored", [
    "Source_Files/MOP001.tex",                                         # reports now
    "/Users/chief/NAPAC2025/MOP001/original/Source_Files/MOP001.tex",  # the chief's Mac
    "Z:\\NAPAC2025\\MOP001\\original\\Source_Files\\MOP001.tex",       # a Windows mount
])
def test_a_paper_prepared_on_another_computer_finds_its_source(pool: Path, stored: str):
    assert files.source_file(paper(pool), stored) == (
        paper(pool) / "Source_Files" / "MOP001.tex")


def test_a_recorded_path_cannot_climb_out_of_the_paper(pool: Path):
    assert files.source_file(paper(pool), "../../TUP002/original/Source_Files/TUP002.tex") is None
    assert files.source_file(paper(pool), "Source_Files/missing.tex") is None
    assert files.source_file(paper(pool), "") is None


def test_the_title_check_reads_a_paper_prepared_on_the_chiefs_computer(pool: Path):
    report = {"source": "/Users/chief/NAPAC2025/MOP001/original/Source_Files/MOP001.tex"}

    front = title_check.front_for(paper(pool), report)

    assert front is not None
    assert front.title == "Beam Dynamics in a Small Ring"


# ---------------------------------------------------------------------------
# Each editor's own settings
# ---------------------------------------------------------------------------

def test_each_editor_has_their_own_name_and_desk_id(tmp_path: Path):
    ling, yue = editor(tmp_path, "Ling Wang"), editor(tmp_path, "Yue Hao")

    assert (ling.name, yue.name) == ("Ling Wang", "Yue Hao")
    assert ling.desk_id != yue.desk_id
    assert me_module.current(tmp_path / "home-ling").desk_id == ling.desk_id


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

def test_the_first_desk_to_claim_a_paper_has_it(pool: Path, tmp_path: Path):
    ling, yue = editor(tmp_path, "Ling Wang"), editor(tmp_path, "Yue Hao")

    claim_module.take(paper(pool), ling)
    claim_module.take(paper(pool), ling)          # again: still Ling's, no error

    with pytest.raises(claim_module.Held) as refused:
        claim_module.take(paper(pool), yue)
    assert "Ling Wang is editing this paper" in str(refused.value)
    assert claim_module.view(paper(pool), yue.desk_id)["state"] == "other"
    assert claim_module.view(paper(pool), ling.desk_id)["state"] == "mine"


def test_only_the_holder_can_let_a_paper_go(pool: Path, tmp_path: Path):
    ling, yue = editor(tmp_path, "Ling Wang"), editor(tmp_path, "Yue Hao")
    claim_module.take(paper(pool), ling)

    assert claim_module.release(paper(pool), yue) is False
    assert claim_module.current(paper(pool)).name == "Ling Wang"
    assert claim_module.release(paper(pool), ling) is True
    assert claim_module.current(paper(pool)) is None


def test_two_desks_claiming_at_the_same_moment_cannot_both_win(pool: Path, tmp_path: Path):
    desks = [editor(tmp_path, f"Editor{i} X") for i in range(8)]
    winners, start = [], threading.Barrier(len(desks))

    def claim(me):
        start.wait()
        try:
            claim_module.take(paper(pool), me)
            winners.append(me.name)
        except claim_module.Held:
            pass

    threads = [threading.Thread(target=claim, args=(me,)) for me in desks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert claim_module.current(paper(pool)).name == winners[0]


def test_an_unreadable_claim_still_counts_and_can_be_taken_over(pool: Path, tmp_path: Path):
    yue = editor(tmp_path, "Yue Hao")
    claim_module.path_for(paper(pool)).parent.mkdir(parents=True)
    claim_module.path_for(paper(pool)).write_text("", encoding="utf-8")

    with pytest.raises(claim_module.Held):
        claim_module.take(paper(pool), yue)
    claim_module.take_over(paper(pool), yue)
    assert claim_module.view(paper(pool), yue.desk_id)["state"] == "mine"


def test_preparing_a_paper_again_keeps_its_claim(pool: Path, tmp_path: Path):
    from src.workflow.prescreen import _reset_dir

    claim_module.take(paper(pool), editor(tmp_path, "Ling Wang"))
    ReviewState(editor="Ling Wang").save(paper(pool))
    out = paper(pool) / "aiagent_prescreen"
    (out / "report.json").write_text("{}", encoding="utf-8")

    _reset_dir(out)

    assert sorted(p.name for p in out.iterdir()) == ["claim.json", "review_state.json"]


def test_the_worklist_says_who_is_editing_each_paper(pool: Path, tmp_path: Path):
    ling, yue = editor(tmp_path, "Ling Wang"), editor(tmp_path, "Yue Hao")
    claim_module.take(paper(pool), ling)

    rows = {r.paper_id: r.claim for r in worklist(pool, me=yue.name, desk_id=yue.desk_id)}

    assert rows["MOP001"]["state"] == "other" and rows["MOP001"]["who"] == "Ling Wang"
    assert rows["TUP002"] is None


def test_the_batch_leaves_papers_being_edited_alone(pool: Path, tmp_path: Path):
    from main import prescreen_targets

    claim_module.take(paper(pool), editor(tmp_path, "Ling Wang"))
    (paper(pool, "TUP002") / "aiagent_prescreen").mkdir()
    (paper(pool, "TUP002") / "aiagent_prescreen" / "report.json").write_text("{}")

    to_prepare, held = prescreen_targets(pool)
    assert to_prepare == [paper(pool, "TUP002").resolve()]
    assert held == [(paper(pool).resolve(), "Ling Wang")]

    assert prescreen_targets(pool, skip_prepared=True) == ([], held)


# ---------------------------------------------------------------------------
# Two desks on one pool, through the server
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_desks(pool: Path, tmp_path: Path):
    """Ling's desk and Yue's desk, each on their own computer, on one pool."""
    servers, ports = [], {}
    for name in ("Ling Wang", "Yue Hao"):
        home = tmp_path / f"home-{name.split()[0].lower()}"
        me_module.update_settings(home, editor=name)
        handler = partial(DeskHandler, root=pool, jobs=JobRunner(llm=False), home=home)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        ports[name.split()[0].lower()] = httpd.server_address[1]
    yield ports
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": f"127.0.0.1:{port}"}
    payload = None
    if body is not None:
        headers.update({"Content-Type": "application/json",
                        "Origin": f"http://127.0.0.1:{port}"})
        payload = json.dumps(body)
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, data


def test_each_desk_knows_its_own_editor(two_desks: dict, pool: Path):
    assert _call(two_desks["ling"], "GET", "/api/setup")[1]["editor"] == "Ling Wang"
    assert _call(two_desks["yue"], "GET", "/api/setup")[1]["editor"] == "Yue Hao"

    _call(two_desks["yue"], "POST", "/api/editor", {"editor": "Y. Hao"})

    assert _call(two_desks["ling"], "GET", "/api/setup")[1]["editor"] == "Ling Wang"
    assert not (pool / ".aiagent_desk.json").exists()


def test_a_second_desk_cannot_change_a_paper_the_first_is_editing(two_desks: dict, pool: Path):
    folder = str(paper(pool))
    status, _ = _call(two_desks["ling"], "POST", "/api/decide",
                      {"folder": folder, "id": "E001", "decision": "accepted"})
    assert status == 200

    status, data = _call(two_desks["yue"], "POST", "/api/decide",
                         {"folder": folder, "id": "E001", "decision": "rejected"})

    assert status == 409
    assert "Ling Wang is editing this paper" in data["error"]
    assert data["claim"]["state"] == "other"
    assert ReviewState.load(paper(pool)).decisions == {"E001": "accepted"}
    assert ReviewState.load(paper(pool)).editor == "Ling Wang"


def test_opening_a_paper_claims_nothing(two_desks: dict, pool: Path):
    status, view = _call(two_desks["yue"], "GET", f"/api/paper?folder={paper(pool)}")

    assert status == 200
    assert view["claim"] is None
    assert claim_module.current(paper(pool)) is None


def test_taking_a_paper_over_moves_it_and_its_letter(two_desks: dict, pool: Path):
    folder = str(paper(pool))
    _call(two_desks["ling"], "POST", "/api/decide",
          {"folder": folder, "id": "E001", "decision": "accepted"})

    status, view = _call(two_desks["yue"], "POST", "/api/claim",
                         {"folder": folder, "action": "take_over"})
    assert status == 200 and view["claim"]["state"] == "mine"
    assert ReviewState.load(paper(pool)).editor == "Yue Hao"

    status, data = _call(two_desks["ling"], "POST", "/api/decide",
                         {"folder": folder, "id": "E002", "decision": "accepted"})
    assert status == 409 and "Yue Hao is editing" in data["error"]


def test_letting_a_paper_go_frees_it_for_the_next_editor(two_desks: dict, pool: Path):
    folder = str(paper(pool))
    _call(two_desks["ling"], "POST", "/api/decide",
          {"folder": folder, "id": "E001", "decision": "accepted"})

    status, view = _call(two_desks["ling"], "POST", "/api/claim",
                         {"folder": folder, "action": "release"})
    assert status == 200 and view["claim"] is None

    status, _ = _call(two_desks["yue"], "POST", "/api/decide",
                      {"folder": folder, "id": "E002", "decision": "accepted"})
    assert status == 200


def test_whoever_picks_up_a_free_paper_signs_its_next_letter(two_desks: dict, pool: Path):
    folder = str(paper(pool))
    _call(two_desks["ling"], "POST", "/api/decide",
          {"folder": folder, "id": "E001", "decision": "accepted"})
    _call(two_desks["ling"], "POST", "/api/claim", {"folder": folder, "action": "release"})

    status, view = _call(two_desks["yue"], "POST", "/api/reopen", {"folder": folder})

    assert status == 200 and view["claim"]["state"] == "mine"
    assert ReviewState.load(paper(pool)).editor == "Yue Hao"
    assert ReviewState.load(paper(pool)).decisions == {"E001": "accepted"}


def test_preparing_skips_a_paper_another_desk_is_editing(two_desks: dict, pool: Path):
    for code in ("MOP001", "TUP002"):
        status, _ = _call(two_desks["ling"], "POST", "/api/decide",
                          {"folder": str(paper(pool, code)), "id": "E001",
                           "decision": "accepted"})
        assert status == 200

    status, data = _call(two_desks["yue"], "POST", "/api/prepare",
                         {"folder": str(paper(pool))})
    assert status == 409 and "Ling Wang" in data["error"]

    status, data = _call(two_desks["yue"], "POST", "/api/prepare", {"all": True})
    assert status == 200 and data["job"] is None
    assert "2 paper(s) left alone" in data["message"]
