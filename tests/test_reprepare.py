"""Preparing papers again after the preparation improved, keeping the editors' work.

The danger this guards against: decisions are stored by edit id, ids are
numbered by position, so a new set of edits would make an old "accepted" land
on a different change. Decisions must follow what their edit says, and a
decision with nothing left to land on must be dropped and reported.
"""

import http.client
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk import claim as claim_module
from src.desk import reprepare
from src.desk.me import Me
from src.desk.paper import view
from src.desk.server import DeskHandler, JobRunner
from src.desk.state import ReviewState, worklist
from src.edits import EditSet
from src.workflow.prescreen import preparation_build, prescreen

from tests.test_desk import TEX


def _prepare(folder: Path) -> dict:
    return reprepare.prepare_keeping_work(folder, lambda f: prescreen(f, compile=False, git=False))


@pytest.fixture()
def paper_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "IPAC26" / "AAA001-revision-1_author"
    (folder / "Source_Files").mkdir(parents=True)
    (folder / "Source_Files" / "AAA001.tex").write_text(TEX, encoding="utf-8")
    prescreen(folder, compile=False, git=False)
    return folder


def _edits(folder: Path) -> EditSet:
    return EditSet.read(folder / "aiagent_prescreen" / "edits.json")


def test_decisions_follow_their_edits_when_the_ids_move(paper_folder: Path):
    before = _edits(paper_folder)
    unit = next(e for e in before.suggested if e.check_id == "FMT-UNIT-02")       # 5 mhz
    title = next(e for e in before.suggested if e.check_id == "FMT-TITLE-02")
    applied = next(e for e in before.auto if e.check_id == "FMT-UNIT-01")
    state = ReviewState.load(paper_folder)
    state.decide(unit.id, "accepted")
    state.set_edit_text(unit.id, "\\qty{5}{\\mega\\hertz}")
    state.decide(title.id, "rejected")
    state.set_edit_note(title.id, "the author wants the full stop")
    state.decide(applied.id, "reverted")
    state.save(paper_folder)

    # The source gains a new correction near the top, so every id after it shifts.
    source = paper_folder / "Source_Files" / "AAA001.tex"
    source.write_text(source.read_text(encoding="utf-8").replace(
        "\\maketitle", "\\maketitle\nA 3 kV supply."), encoding="utf-8")
    result = _prepare(paper_folder)
    assert result["kept"] == 3 and result["dropped"] == []

    after = _edits(paper_folder)
    def same(old):
        return next(e for e in after.edits if (e.check_id, e.before, e.after)
                    == (old.check_id, old.before, old.after))
    assert same(unit).id != unit.id or same(title).id != title.id   # the ids did move
    state = ReviewState.load(paper_folder)
    assert state.decisions[same(unit).id] == "accepted"
    assert state.edit_texts[same(unit).id] == "\\qty{5}{\\mega\\hertz}"
    assert state.decisions[same(title).id] == "rejected"
    assert state.edit_notes[same(title).id] == "the author wants the full stop"
    assert state.decisions[same(applied).id] == "reverted"
    # Nothing landed on an edit the editor never saw.
    assert set(state.decisions) == {same(unit).id, same(title).id, same(applied).id}


def test_a_decision_whose_suggestion_is_gone_is_dropped_and_reported(paper_folder: Path):
    unit = next(e for e in _edits(paper_folder).suggested if e.check_id == "FMT-UNIT-02")
    state = ReviewState.load(paper_folder)
    state.decide(unit.id, "accepted")
    state.save(paper_folder)

    # The author's text no longer has "5 mhz": the suggestion disappears.
    source = paper_folder / "Source_Files" / "AAA001.tex"
    source.write_text(source.read_text(encoding="utf-8").replace("5 mhz", "5~MHz"),
                      encoding="utf-8")
    result = _prepare(paper_folder)
    assert [d["check_id"] for d in result["dropped"]] == ["FMT-UNIT-02"]
    assert result["dropped"][0]["decision"] == "accepted"

    state = ReviewState.load(paper_folder)
    assert unit.id not in state.decisions or _edits(paper_folder).get(unit.id).before != "5 mhz"
    shown = view(paper_folder)["reprepared"]
    assert shown["dropped"][0]["before"] == "5 mhz"


def test_the_report_says_which_version_prepared_it(paper_folder: Path):
    report = json.loads((paper_folder / "aiagent_prescreen" / "report.json").read_text())
    assert report["prepared_by"] == preparation_build()
    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.outdated is False
    report["prepared_by"] = "older"
    (paper_folder / "aiagent_prescreen" / "report.json").write_text(json.dumps(report))
    row = next(r for r in worklist(paper_folder.parent) if r.paper_id == "AAA001")
    assert row.outdated is True


def test_a_paper_being_prepared_is_marked_busy(paper_folder: Path):
    seen = []
    reprepare.prepare_keeping_work(paper_folder, lambda f: seen.append(reprepare.is_busy(f)))
    assert seen == [True] and not reprepare.is_busy(paper_folder)


def test_a_paper_taken_meanwhile_is_left_alone(paper_folder: Path):
    claim_module.take(paper_folder, Me(name="B. Colleague", machine="b", desk_id="desk-b"))
    ran = []
    result = reprepare.prepare_keeping_work(paper_folder, ran.append, desk_id="desk-a")
    assert result.get("skipped") == "held" and ran == []


# ---------------------------------------------------------------------------
# Through the desk: "Prepare all again"
# ---------------------------------------------------------------------------

@pytest.fixture()
def conference(tmp_path: Path) -> Path:
    root = tmp_path / "IPAC26"
    for name in ("AAA001-revision-1_author", "BBB002-revision-1_author",
                 "CCC003-revision-1_author"):
        folder = root / name
        (folder / "Source_Files").mkdir(parents=True)
        (folder / "Source_Files" / f"{name[:6]}.tex").write_text(TEX, encoding="utf-8")
        prescreen(folder, compile=False, git=False)
    return root


@pytest.fixture()
def desk(conference: Path, tmp_path: Path):
    handler = partial(DeskHandler, root=conference, jobs=JobRunner(llm=False),
                      home=tmp_path / "home")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    headers = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        headers.update({"Content-Type": "application/json",
                        "Origin": f"http://127.0.0.1:{port}"})
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
                 headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, data


def test_prepare_all_again_leaves_edited_and_finished_papers_alone(desk: int, conference: Path):
    a, b, c = sorted(p for p in conference.iterdir() if p.is_dir())
    claim_module.take(b, Me(name="B. Colleague", machine="b", desk_id="desk-b"))
    state = ReviewState.load(c)
    state.status = "done"
    state.save(c)

    status, plan = _call(desk, "POST", "/api/prepare", {"all": True, "force": True,
                                                        "dry_run": True})
    assert status == 200
    assert (plan["would_prepare"], plan["held"], plan["finished"]) == (1, 1, 1)

    before = {p: (p / "aiagent_prescreen" / "report.json").stat().st_mtime_ns
              for p in (a, b, c)}
    status, data = _call(desk, "POST", "/api/prepare", {"all": True, "force": True})
    assert status == 200 and data["job"] and data["skipped"] == 1 and data["finished"] == 1
    import time

    for _ in range(200):
        _, job = _call(desk, "GET", "/api/job?id=" + data["job"]["id"])
        if job.get("finished"):
            break
        time.sleep(0.1)
    assert job["finished"] and not job["errors"]
    after = {p: (p / "aiagent_prescreen" / "report.json").stat().st_mtime_ns
             for p in (a, b, c)}
    assert after[a] != before[a]                       # prepared again
    assert after[b] == before[b] and after[c] == before[c]
