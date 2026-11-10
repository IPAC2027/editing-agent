"""The chief editor's desk: the conference in Indico, downloading and preparing it.

Indico is faked throughout; the suite runs offline (see conftest).
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk import chief as chief_module
from src.desk.server import DeskHandler, JobRunner
from src.indico_client.models import ContributionRow

TEX = "\\documentclass{jacow}\n\\title{A}\n\\begin{document}\\maketitle\\end{document}\n"


def _row(code: str, cid: int, *, submitted: bool = True, editor: str = "") -> ContributionRow:
    editable = ({"id": cid, "state": "ready_for_review", "revision_count": 1,
                 "editor": {"id": 1, "full_name": editor} if editor else None}
                if submitted else None)
    return ContributionRow.model_validate({"id": cid, "friendly_id": cid - 100, "code": code,
                                           "title": f"Paper {code}", "editable": editable})


class FakeClient:
    event_id = 194
    base_url = "https://indico.jacow.org"
    editable_type = "paper"

    def list_editables(self):
        return [_row("MOP001", 101), _row("MOP002", 102, editor="Ling Wang"),
                _row("TUP003", 103, submitted=False)]


@pytest.fixture()
def fake_indico(monkeypatch):
    monkeypatch.setattr(chief_module.Event, "client", lambda self: FakeClient())
    monkeypatch.setenv("INDICO_TOKEN", "test-token-not-real")


def _desk(root: Path, chief):
    handler = partial(DeskHandler, root=root, jobs=JobRunner(llm=False),
                      home=root.parent / "home", chief=chief)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


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


@pytest.fixture()
def chief_desk(tmp_path: Path, fake_indico):
    root = tmp_path / "IPAC27TEST"
    root.mkdir()
    httpd, port = _desk(root, chief_module.Event(event_id=194))
    yield root, port
    httpd.shutdown(); httpd.server_close()


def test_an_editors_desk_has_no_chief_part(tmp_path: Path):
    httpd, port = _desk(tmp_path, None)
    try:
        assert _call(port, "GET", "/api/setup")[1]["chief"] is None
        status, data = _call(port, "POST", "/api/chief/papers", {})
        assert status == 400 and "chief" in data["error"]
        assert _call(port, "POST", "/api/chief/download", {})[0] == 400
    finally:
        httpd.shutdown(); httpd.server_close()


def test_the_chief_sees_the_event_but_never_the_token(chief_desk):
    root, port = chief_desk
    chief = _call(port, "GET", "/api/setup")[1]["chief"]
    assert chief["event"] == 194 and chief["token"] is True
    assert chief["event_url"] == "https://indico.jacow.org/event/194"
    assert "test-token-not-real" not in json.dumps(chief)


def test_a_missing_token_is_explained(chief_desk, monkeypatch):
    _root, port = chief_desk
    monkeypatch.delenv("INDICO_TOKEN")
    import importlib.util
    if importlib.util.find_spec("keyring"):
        monkeypatch.setattr("keyring.get_password", lambda *a, **k: None)
    chief = _call(port, "GET", "/api/setup")[1]["chief"]
    assert chief["token"] is False and "Indico box" in chief["token_problem"]


def test_an_empty_folder_lists_the_conference_from_indico(chief_desk):
    root, port = chief_desk
    status, data = _call(port, "POST", "/api/chief/papers", {})
    assert status == 200
    assert [p["code"] for p in data["papers"]] == ["MOP001", "MOP002", "TUP003"]
    assert data["submitted"] == 2 and data["here"] == 0
    assert data["papers"][1]["editor"] == "Ling Wang"
    assert data["papers"][2]["submitted"] is False


def test_a_downloaded_and_prepared_paper_is_marked(chief_desk):
    root, port = chief_desk
    (root / "MOP001" / "original" / "aiagent_prescreen").mkdir(parents=True)
    (root / "MOP001" / "manifest.json").write_text("{}")
    (root / "MOP001" / "original" / "aiagent_prescreen" / "report.json").write_text("{}")
    (root / "MOP002").mkdir()
    (root / "MOP002" / "manifest.json").write_text("{}")
    papers = {p["code"]: p for p in _call(port, "POST", "/api/chief/papers", {})[1]["papers"]}
    assert (papers["MOP001"]["here"], papers["MOP001"]["prepared"]) == (True, True)
    assert (papers["MOP002"]["here"], papers["MOP002"]["prepared"]) == (True, False)
    assert papers["TUP003"]["here"] is False


def test_the_page_chooses_the_event_but_cannot_switch_a_folder_to_another(tmp_path, fake_indico):
    root = tmp_path / "papers"; root.mkdir()
    httpd, port = _desk(root, chief_module.Event())
    try:
        assert _call(port, "GET", "/api/setup")[1]["chief"]["event"] is None
        assert _call(port, "POST", "/api/chief/event", {"event": "abc"})[0] == 400
        status, data = _call(port, "POST", "/api/chief/event", {"event": "194"})
        assert status == 200 and data["event"] == 194
        (root / "index.json").write_text(json.dumps({"event_id": 194}))
        status, data = _call(port, "POST", "/api/chief/event", {"event": 97})
        assert status == 400 and "already holds event 194" in data["error"]
        # the site is never the page's to choose
        _call(port, "POST", "/api/chief/event", {"event": 194, "url": "https://evil.example"})
        assert _call(port, "GET", "/api/setup")[1]["chief"]["url"] == "https://indico.jacow.org"
    finally:
        httpd.shutdown(); httpd.server_close()


def test_download_fetches_asks_who_holds_and_prepares_only_new_papers(tmp_path, monkeypatch):
    root = tmp_path / "papers"; root.mkdir()
    old = root / "MOP000" / "original"; old.mkdir(parents=True)
    (old / "MOP000.tex").write_text(TEX)
    (old / "aiagent_prescreen").mkdir(); (old / "aiagent_prescreen" / "report.json").write_text("{}")

    class Plan:
        fetchable = ["MOP001"]
        failures = ["MOP009: x.pdf: timed out"]

    def fake_pull(client, destination, *, plan, on_paper):
        on_paper(1, 1, type("P", (), {"folder": "MOP001"})())
        new = destination / "MOP001" / "original"; new.mkdir(parents=True)
        (new / "MOP001.tex").write_text(TEX)
        (destination / "index.json").write_text(json.dumps({"event_id": 194}))
        return plan

    refreshed, prepared, updates = [], [], []
    monkeypatch.setattr("src.indico_client.pull.build_plan", lambda client, **kw: Plan())
    monkeypatch.setattr("src.indico_client.pull.pull", fake_pull)
    monkeypatch.setattr("src.desk.indico.refresh", lambda root, client: refreshed.append(root))
    monkeypatch.setattr(chief_module.Event, "client", lambda self: FakeClient())

    chief_module.download_and_prepare(chief_module.Event(event_id=194), root,
                                      lambda **kw: updates.append(kw),
                                      prepare=lambda folder: prepared.append(folder))

    assert refreshed == [root]
    assert prepared == [root / "MOP001" / "original"]          # MOP000 was prepared already
    assert any("MOP009" in u.get("error", "") for u in updates)
    assert any(u.get("label", "").startswith("Downloading 1") for u in updates)


def test_download_runs_as_a_job_the_page_can_follow(chief_desk, monkeypatch):
    root, port = chief_desk

    def fake(event, folder, progress, *, prepare):
        progress(label="Downloading 2 paper(s)", done=1, total=2, current="MOP001")
        progress(error="MOP002: could not be fetched")

    monkeypatch.setattr(chief_module, "download_and_prepare", fake)
    status, data = _call(port, "POST", "/api/chief/download", {})
    assert status == 200
    job_id = data["job"]["id"]
    for _ in range(50):
        job = _call(port, "GET", f"/api/job?id={job_id}")[1]
        if job["finished"]:
            break
        time.sleep(0.05)
    assert job["finished"] and job["errors"] == ["MOP002: could not be fetched"]
    assert job["label"] == "Downloading 2 paper(s)"


def test_download_without_a_token_says_so_at_once(chief_desk, monkeypatch):
    from src.indico_client.client import IndicoAuthError

    _root, port = chief_desk

    def no_token(self):
        raise IndicoAuthError("No Indico token found. Set INDICO_TOKEN.")

    monkeypatch.setattr(chief_module.Event, "client", no_token)
    status, data = _call(port, "POST", "/api/chief/download", {})
    assert status == 400 and "INDICO_TOKEN" in data["error"]


# ---------------------------------------------------------------------------
# Which is newer: Indico's paper or the copy here
# ---------------------------------------------------------------------------

def test_which_is_newer_indico_or_the_copy_here(tmp_path: Path):
    from src.desk.state import ReviewState

    folder = tmp_path / "MOP001"
    assert chief_module.newer(folder, 3) == {"newer": "", "local_revisions": 0}

    (folder / "original").mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"revision_count": 2}))
    assert chief_module.newer(folder, 2)["newer"] == "same"
    assert chief_module.newer(folder, 3) == {"newer": "indico", "local_revisions": 2}

    state = ReviewState()
    state.status = "in_review"                     # an editor has worked on it here
    state.save(folder / "original")
    assert chief_module.newer(folder, 2)["newer"] == "local"
    assert chief_module.newer(folder, 3)["newer"] == "both"

