"""Editors' desks working from the chief's desk, never from the pool folder.

The chief's desk holds the pool and opens a door (``src.desk.pool``); each
editor's desk (``src.desk.remote``) takes papers through it, works on copies in
its own folder, and sends the review files back.
"""

from __future__ import annotations

import http.client
import io
import json
import threading
import zipfile
import zlib
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk import bundle
from src.desk import claim as claim_module
from src.desk import me as me_module
from src.desk import pool as pool_module
from src.desk import remote
from src.desk.server import DeskHandler, JobRunner
from src.desk.state import ReviewState

TEX = ("\\documentclass{jacow}\n\\title{Beam Dynamics in a Small Ring}\n"
       "\\author{A. Author}\n\\begin{document}\n\\maketitle\n\\end{document}\n")
CODE = "abcd-efgh-jkmn"


@pytest.fixture()
def chief(tmp_path: Path):
    """The chief's pool with two prepared papers, and its door open on 127.0.0.1."""
    root = tmp_path / "chief" / "IPAC27TEST"
    for code in ("MOP001", "TUP002"):
        revision = root / code / "original"
        (revision / "Source_Files").mkdir(parents=True)
        (revision / "Source_Files" / f"{code}.tex").write_text(TEX, encoding="utf-8")
        out = revision / "aiagent_prescreen"
        out.mkdir()
        (out / "report.json").write_text(json.dumps(
            {"paper_id": code, "title": "Beam Dynamics", "findings": []}), encoding="utf-8")
        (root / code / "manifest.json").write_text(json.dumps(
            {"code": code, "contribution_id": 1 if code == "MOP001" else 2}), encoding="utf-8")
    (root / "index.json").write_text(json.dumps(
        {"event_id": 194, "base_url": "https://indico.example.org"}), encoding="utf-8")
    (root / "indico_assignments.json").write_text(json.dumps(
        {"checked_at": "2026-11-07T10:00:00+00:00",
         "papers": {"1": {"code": "MOP001", "editor": "Ling Wang", "state": "ready_for_review"}}}),
        encoding="utf-8")
    pool = pool_module.Pool(root, code=CODE, port=0, addresses=["127.0.0.1"])
    server = pool_module.start(pool, host="127.0.0.1")
    yield pool
    server.shutdown()
    server.server_close()


def connect_indico(home: Path, name: str) -> None:
    """What pasting a token on the page leaves behind: the token, and whose it is."""
    me_module.update_settings(home, indico_user={
        "id": zlib.crc32(name.encode()) % 100000, "name": name,
        "url": "https://indico.example.org"})
    (home / "indico_token").write_text("indico-token-abcdefghijklmnop")


def editor_desk(tmp_path: Path, chief: pool_module.Pool, name: str, *,
                code: str = CODE) -> remote.Joined:
    """An editor's desk joined to *chief*, known as *name* by its Indico account."""
    home = tmp_path / f"home-{name.split()[0].lower()}"
    connect_indico(home, name)
    copies = tmp_path / f"copies-{name.split()[0].lower()}"
    copies.mkdir()
    client = remote.RemotePool(f"http://127.0.0.1:{chief.port}", code, timeout=5)
    return remote.Joined(copies, client, home=home, delay=0, background=False)


def pool_paper(chief: pool_module.Pool, code: str = "MOP001") -> Path:
    return chief.root / code / "original"


# ---------------------------------------------------------------------------
# Taking a paper
# ---------------------------------------------------------------------------

def test_an_editor_takes_a_paper_and_gets_a_copy_of_their_own(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")

    folder = ling.take("MOP001")

    assert folder == ling.root / "MOP001" / "original"
    assert (folder / "Source_Files" / "MOP001.tex").read_text(encoding="utf-8") == TEX
    assert (folder / "aiagent_prescreen" / "report.json").is_file()
    assert chief.root not in folder.parents                 # a copy, not the pool
    # The chief's desk now shows who has it, and Ling is its editor.
    assert claim_module.current(pool_paper(chief)).name == "Ling Wang"
    assert ReviewState.load(pool_paper(chief)).editor == "Ling Wang"
    # The copy knows the conference, so Indico's assignments show on Ling's desk.
    assert json.loads((ling.root / "index.json").read_text())["event_id"] == 194
    assert (ling.root / "indico_assignments.json").is_file()


def test_a_paper_one_editor_has_cannot_be_taken_by_another(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    yue = editor_desk(tmp_path, chief, "Yue Hao")
    ling.take("MOP001")

    with pytest.raises(remote.Refused, match="Ling Wang is editing this paper"):
        yue.take("MOP001")
    assert not (yue.root / "MOP001").exists()


def test_the_list_says_who_has_each_paper_and_who_has_it_in_indico(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    yue = editor_desk(tmp_path, chief, "Yue Hao")
    ling.take("MOP001")

    rows = {row["paper"]: row for row in yue.papers()}

    assert rows["MOP001"]["claim"]["who"] == "Ling Wang"
    assert rows["MOP001"]["claim"]["mine"] is False
    assert rows["MOP001"]["indico"]["editor"] == "Ling Wang"
    assert rows["TUP002"]["claim"] is None
    assert {row["paper"]: row for row in ling.papers()}["MOP001"]["here"] is True


def test_an_editor_is_known_by_their_indico_account_not_a_typed_name(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    me_module.update_settings(ling.home, editor="lw")        # typed before, on an older desk
    ling.take("MOP001")
    assert claim_module.current(pool_paper(chief)).name == "Ling Wang"
    assert ling.me().name == "Ling Wang"


def test_an_editor_without_an_indico_account_cannot_take_a_paper(tmp_path, chief):
    stranger = editor_desk(tmp_path, chief, "Some One")
    (stranger.home / "indico_token").unlink()                # disconnected
    me_module.update_settings(stranger.home, editor="Some One")

    with pytest.raises(ValueError, match="Indico token"):
        stranger.take("MOP001")
    # Nor does the chief's desk let one in that does not say who it is in Indico.
    with pytest.raises(remote.PoolError, match="Indico account"):
        stranger.pool.take("MOP001", stranger.me())
    assert claim_module.current(pool_paper(chief)) is None


def test_a_wrong_join_code_is_refused(tmp_path, chief):
    stranger = editor_desk(tmp_path, chief, "Some One", code="wrong-code-here")

    with pytest.raises(remote.PoolError, match="did not accept that join code"):
        stranger.papers()
    assert stranger.view()["connected"] is False


def test_an_unreachable_chief_is_explained(tmp_path):
    home = tmp_path / "home"
    me_module.update_settings(home, editor="Ling Wang")
    client = remote.RemotePool("http://127.0.0.1:9", CODE, timeout=2)
    joined = remote.Joined(tmp_path / "copies", client, home=home, background=False)

    view = joined.view()

    assert view["connected"] is False
    assert "Could not reach the chief editor's desk" in view["error"]


@pytest.mark.parametrize("given, expected", [
    ("192.168.1.20", "http://192.168.1.20:8770"),
    ("http://192.168.1.20:8771/", "http://192.168.1.20:8771"),
    ("chief-mac.local:8770", "http://chief-mac.local:8770"),
])
def test_the_chiefs_address_can_be_typed_as_the_page_shows_it(given, expected):
    assert remote.normalise_url(given) == expected


# ---------------------------------------------------------------------------
# Sending work back
# ---------------------------------------------------------------------------

def _decide(folder: Path, edit_id: str = "E001", decision: str = "accepted") -> None:
    state = ReviewState.load(folder)
    state.decide(edit_id, decision)
    state.save(folder)


def test_an_editors_work_reaches_the_pool(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    _decide(folder)
    (folder / "aiagent_prescreen" / "author_letter.txt").write_text("Dear author", "utf-8")

    ling.changed(folder)
    ling.flush()

    assert ReviewState.load(pool_paper(chief)).decisions == {"E001": "accepted"}
    assert (pool_paper(chief) / "aiagent_prescreen" / "author_letter.txt").read_text() == "Dear author"
    assert claim_module.current(pool_paper(chief)).name == "Ling Wang"     # claim kept
    assert ling.sync_view(folder)["dirty"] is False
    assert ling.sync_view(folder)["sent_at"]
    assert chief.activity()["papers"]["MOP001"]["received_at"]


def test_each_send_keeps_a_backup_of_what_it_replaced(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    for n in range(7):
        _decide(folder, f"E{n:03d}")
        ling.send(folder)

    backups = sorted((chief.root / pool_module.BACKUP_DIR / "MOP001").glob("*.zip"))
    assert len(backups) == pool_module.KEEP_BACKUPS


def test_giving_a_paper_back_sends_it_and_frees_it(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    yue = editor_desk(tmp_path, chief, "Yue Hao")
    folder = ling.take("MOP001")
    _decide(folder)

    ling.give_back(folder)

    assert claim_module.current(pool_paper(chief)) is None
    assert ReviewState.load(pool_paper(chief)).decisions == {"E001": "accepted"}
    with pytest.raises(ValueError, match="no longer yours"):
        ling.require_held(folder)
    # Yue picks it up with Ling's work in it.
    theirs = yue.take("MOP001")
    assert ReviewState.load(theirs).decisions == {"E001": "accepted"}


def test_an_editors_copies_live_in_a_folder_the_desk_keeps_per_chief(tmp_path):
    home = tmp_path / "home"
    assert remote.working_folder("10.9.0.3", home) == home / "working" / "10.9.0.3-8770"
    assert (remote.working_folder("http://chief-mac.local:8771/", home)
            == home / "working" / "chief-mac.local-8771")


def test_copies_given_back_are_cleared_and_the_rest_kept(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    working = ling.take("MOP001")
    given_back = ling.take("TUP002")
    _decide(given_back)
    ling.give_back(given_back)
    (ling.root / ".incoming-dead").mkdir()          # left by a desk that crashed

    assert ling.tidy() == ["TUP002"]

    assert not (ling.root / "TUP002").exists() and ling.copy("TUP002") == {}
    assert working.is_dir() and ling.holds(working)
    assert not (ling.root / ".incoming-dead").exists()
    assert (ling.root / "index.json").is_file()     # the conference stays
    # The chief has every bit of it: Yue picks it up with Ling's work in it.
    yue = editor_desk(tmp_path, chief, "Yue Hao")
    assert ReviewState.load(yue.take("TUP002")).decisions == {"E001": "accepted"}


def test_a_copy_with_work_the_chief_never_got_is_never_cleared(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    refused = ling.take("MOP001")
    away = ling.take("TUP002")
    # The chief takes MOP001 over, then Ling changes it.
    claim_module.take_over(pool_paper(chief), me_module.Me(desk_id="c" * 32,
                                                           name="Chief Editor"))
    _decide(refused, decision="rejected")
    with pytest.raises(remote.Refused):
        ling.send(refused)
    # TUP002 is finished while the chief's desk cannot be reached.
    _decide(away)
    real, ling.pool.url = ling.pool.url, "http://127.0.0.1:9"
    with pytest.raises(remote.PoolError):
        ling.give_back(away)
    ling.pool.url = real

    assert ling.tidy() == []
    assert refused.is_dir() and away.is_dir()


def test_taking_a_paper_again_replaces_a_copy_given_back_without_keeping_it(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    ling.give_back(folder)

    again = ling.take("MOP001")

    assert again == folder and ling.holds(again)
    assert not (ling.root / ".replaced").exists()


def test_a_paper_given_up_is_free_again_and_the_chief_is_told_why(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    _decide(folder)

    ling.give_back(folder, reason="  conflict of\ninterest  ")

    assert claim_module.current(pool_paper(chief)) is None
    [notice] = chief.given_up()
    assert (notice["paper"], notice["who"], notice["reason"]) == (
        "MOP001", "Ling Wang", "conflict of interest")
    assert chief.view()["given_up"] == [notice]
    # Their work so far stays in it, for whoever takes it next.
    yue = editor_desk(tmp_path, chief, "Yue Hao")
    assert ReviewState.load(yue.take("MOP001")).decisions == {"E001": "accepted"}
    chief.dismiss(notice["id"])
    assert chief.given_up() == []


def test_a_finished_paper_is_not_announced_as_given_up(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    state = ReviewState.load(folder)
    state.status = "done"
    state.save(folder)

    ling.give_back(folder)

    assert claim_module.current(pool_paper(chief)) is None
    assert chief.given_up() == []


def test_a_paper_given_up_while_the_chief_is_away_says_why_when_it_arrives(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    real, ling.pool.url = ling.pool.url, "http://127.0.0.1:9"
    with pytest.raises(remote.PoolError):
        ling.give_back(folder, reason="no time this week")
    ling.pool.url = real

    ling.flush()

    assert [n["reason"] for n in chief.given_up()] == ["no time this week"]
    assert ling.copy("MOP001")["give_back_reason"] == ""


def test_a_desk_with_the_chiefs_own_settings_cannot_come_in_as_an_editor(chief):
    me_module.update_settings(editor="Chief Editor")       # the chief's own settings
    client = remote.RemotePool(f"http://127.0.0.1:{chief.port}", CODE, timeout=5)
    with pytest.raises(remote.PoolError, match="chief editor's own desk id"):
        client.papers(me_module.current())


def test_the_folder_says_while_a_chiefs_desk_shares_it(tmp_path, chief):
    door = chief.root / pool_module.DOOR_FILE
    assert json.loads(door.read_text())["port"] == chief.port
    assert pool_module.door_open(chief.root) is None        # this very desk
    # As another process sees it: the door answers.
    door.write_text(json.dumps({"pid": 1, "port": chief.port}))
    assert pool_module.door_open(chief.root)["port"] == chief.port
    # A note left by a desk that is gone does not count.
    door.write_text(json.dumps({"pid": 1, "port": 9}))
    assert pool_module.door_open(chief.root) is None


def test_work_from_a_desk_that_no_longer_holds_the_paper_is_refused(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    # The chief takes it over on their own desk.
    chief_me = me_module.Me(desk_id="c" * 32, name="Chief Editor")
    claim_module.take_over(pool_paper(chief), chief_me)
    _decide(folder, decision="rejected")

    with pytest.raises(remote.Refused, match="Chief Editor has this paper"):
        ling.send(folder)

    assert ReviewState.load(pool_paper(chief)).decisions == {}
    assert ling.sync_view(folder)["held"] is False
    assert "Chief Editor" in ling.sync_view(folder)["error"]


def test_a_send_that_cannot_get_through_is_tried_again(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    _decide(folder)
    real = ling.pool.url
    ling.pool.url = "http://127.0.0.1:9"
    ling.changed(folder)

    ling.flush()
    assert ling.sync_view(folder)["dirty"] is True
    assert "Could not reach" in ling.sync_view(folder)["error"]

    ling.pool.url = real
    ling.flush()
    assert ling.sync_view(folder)["dirty"] is False
    assert ReviewState.load(pool_paper(chief)).decisions == {"E001": "accepted"}


def test_a_paper_finished_while_the_chief_is_away_is_given_back_later(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    _decide(folder)
    real = ling.pool.url
    ling.pool.url = "http://127.0.0.1:9"
    with pytest.raises(remote.PoolError):
        ling.give_back(folder)
    assert claim_module.current(pool_paper(chief)) is not None

    ling.pool.url = real
    ling.flush()

    assert claim_module.current(pool_paper(chief)) is None
    assert ReviewState.load(pool_paper(chief)).decisions == {"E001": "accepted"}


# ---------------------------------------------------------------------------
# The door refuses what it should
# ---------------------------------------------------------------------------

def _raw_send(chief, paper: str, data: bytes, desk_id: str) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", chief.port, timeout=5)
    conn.request("POST", f"/pool/send?paper={paper}", body=data, headers={
        "Authorization": f"Bearer {CODE}", "X-Desk-Id": desk_id,
        "X-Desk-Name": "Ling%20Wang", "Content-Type": "application/zip"})
    response = conn.getresponse()
    body = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, body


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


@pytest.mark.parametrize("name", [
    "MOP001/original/Source_Files/MOP001.tex",                 # the author's files
    "MOP001/original/aiagent_prescreen/../Source_Files/x.tex",
    "TUP002/original/aiagent_prescreen/review_state.json",     # another paper
    "/etc/passwd",
])
def test_a_send_may_only_hold_the_papers_review_files(tmp_path, chief, name):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    ling.take("MOP001")
    before = (pool_paper(chief) / "Source_Files" / "MOP001.tex").read_text()

    status, body = _raw_send(chief, "MOP001", _zip({
        "MOP001/original/aiagent_prescreen/review_state.json": "{}", name: "x"}),
        ling.me().desk_id)

    assert status == 400 and "Nothing was changed" in body["error"]
    assert (pool_paper(chief) / "Source_Files" / "MOP001.tex").read_text() == before
    assert not (pool_paper(chief, "TUP002") / "aiagent_prescreen" / "review_state.json").exists()


def test_a_send_cannot_replace_the_claim(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    ling.take("MOP001")
    prefix = "MOP001/original/aiagent_prescreen/"

    status, _ = _raw_send(chief, "MOP001", _zip({
        prefix + "review_state.json": "{}",
        prefix + "claim.json": json.dumps({"desk_id": "f" * 32, "name": "Mallory"})}),
        ling.me().desk_id)

    assert status == 200
    assert claim_module.current(pool_paper(chief)).name == "Ling Wang"


def test_a_copy_never_carries_the_claim(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")
    assert not (folder / "aiagent_prescreen" / "claim.json").exists()


def test_a_bundle_cannot_climb_out_of_its_folder():
    with pytest.raises(bundle.BadBundle):
        bundle.read(_zip({"a/../../evil": "x"}), "")
    with pytest.raises(bundle.BadBundle):
        bundle.read(b"not a zip", "")


# ---------------------------------------------------------------------------
# The editor's desk page, joined to the chief's
# ---------------------------------------------------------------------------

@pytest.fixture()
def ling_page(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    handler = partial(DeskHandler, root=ling.root, jobs=JobRunner(llm=False),
                      home=ling.home, pool=ling)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield ling, httpd.server_address[1]
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


def test_the_page_lists_the_chiefs_papers_and_takes_one(ling_page, chief):
    ling, port = ling_page
    assert _call(port, "GET", "/api/setup")[1]["pool"]["connected"] is True
    status, data = _call(port, "POST", "/api/pool/papers", {})
    assert status == 200 and [p["paper"] for p in data["papers"]] == ["MOP001", "TUP002"]

    status, data = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})
    assert status == 200

    rows = _call(port, "GET", "/api/worklist")[1]["papers"]
    assert [r["name"] for r in rows] == ["MOP001"]
    assert rows[0]["sync"]["held"] is True


def test_the_page_knows_the_editor_by_their_indico_account(ling_page, chief, monkeypatch):
    ling, port = ling_page
    setup = _call(port, "GET", "/api/setup")[1]
    assert setup["editor"] == "Ling Wang"                    # nothing was typed
    assert setup["account"]["connected"] and setup["account"]["source"] == "page"

    # Disconnected, a token in the environment names nobody on this desk ...
    monkeypatch.setenv("INDICO_TOKEN", "indico-token-of-whoever-started-it")
    status, account = _call(port, "POST", "/api/indico-account", {"disconnect": True})
    assert status == 200 and account["connected"] is False
    # ... and there is nobody to take a paper as.
    status, data = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})
    assert status == 400 and "Indico token" in data["error"]
    assert claim_module.current(pool_paper(chief)) is None


def test_a_change_on_the_page_is_sent_to_the_chief(ling_page, chief):
    ling, port = ling_page
    folder = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]

    status, view = _call(port, "POST", "/api/decide",
                         {"folder": folder, "id": "E001", "decision": "accepted"})
    assert status == 200 and view["claim"]["state"] == "mine"
    assert ling.sync_view(Path(folder))["dirty"] is True
    ling.flush()

    assert ReviewState.load(pool_paper(chief)).decisions == {"E001": "accepted"}


def test_a_copy_given_back_cannot_be_changed_on_the_page(ling_page, chief):
    ling, port = ling_page
    folder = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]
    status, view = _call(port, "POST", "/api/claim", {"folder": folder, "action": "release"})
    assert status == 200 and view["claim"]["state"] == "copy"
    assert claim_module.current(pool_paper(chief)) is None

    status, data = _call(port, "POST", "/api/decide",
                         {"folder": folder, "id": "E001", "decision": "accepted"})
    assert status == 400 and "no longer yours" in data["error"]


def test_giving_a_paper_up_on_the_page_tells_the_chiefs_page(ling_page, chief):
    ling, port = ling_page
    folder = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]

    status, view = _call(port, "POST", "/api/claim",
                         {"folder": folder, "action": "release", "reason": "ill"})

    assert status == 200 and view["claim"]["state"] == "copy" and "pool_error" not in view
    # The chief's own page lists it, and can dismiss it.
    handler = partial(DeskHandler, root=chief.root, jobs=JobRunner(llm=False),
                      sharing=chief)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        chief_port = httpd.server_address[1]
        [notice] = _call(chief_port, "GET", "/api/worklist")[1]["sharing"]["given_up"]
        assert (notice["paper"], notice["who"], notice["reason"]) == ("MOP001", "Ling Wang", "ill")
        status, data = _call(chief_port, "POST", "/api/chief/given-up",
                             {"dismiss": notice["id"]})
        assert status == 200 and data == {"given_up": []}
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_page_cannot_take_a_paper_over_or_prepare_one(ling_page, chief):
    ling, port = ling_page
    folder = _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]

    status, data = _call(port, "POST", "/api/claim", {"folder": folder, "action": "take_over"})
    assert status == 400 and "chief editor" in data["error"]
    status, data = _call(port, "POST", "/api/prepare", {"folder": folder})
    assert status == 400 and "prepared on the chief" in data["error"]


def test_check_indico_on_an_editors_desk_asks_the_chief_not_indico(ling_page, chief):
    ling, port = ling_page
    _call(port, "POST", "/api/pool/take", {"paper": "MOP001"})
    status, data = _call(port, "POST", "/api/indico-refresh", {})
    assert status == 200 and data["papers"] == 1


def test_the_chiefs_page_shows_the_door_and_who_came_in(tmp_path, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    ling.papers()

    view = chief.view()

    assert view["code"] == CODE
    assert view["addresses"] == [f"http://127.0.0.1:{chief.port}"]
    assert [e["name"] for e in view["editors"]] == ["Ling Wang"]


def test_the_join_code_is_made_once_and_kept(tmp_path):
    home = tmp_path / "chief-home"
    first = pool_module.join_code(home)
    assert first == pool_module.join_code(home)
    assert len(first) == 14 and first.count("-") == 2


# ---------------------------------------------------------------------------
# The chief's managing page: it manages; papers are edited on editors' desks
# ---------------------------------------------------------------------------

@pytest.fixture()
def managing_page(chief):
    from src.desk import chief as chief_module

    handler = partial(DeskHandler, root=chief.root, jobs=JobRunner(llm=False),
                      chief=chief_module.Event(url="https://indico.example.org",
                                               event_id=194),
                      sharing=chief)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_the_managing_page_edits_no_paper(managing_page, chief):
    folder = str(pool_paper(chief))
    for path, body in [("/api/claim", {"folder": folder, "action": "take"}),
                       ("/api/decide", {"folder": folder, "id": "E001",
                                        "decision": "accepted"}),
                       ("/api/letter", {"folder": folder, "letter": "Dear author"}),
                       ("/api/close", {"folder": folder}),
                       ("/api/pool/take", {"paper": "MOP001"})]:
        status, data = _call(managing_page, "POST", path, body)
        assert status == 403 and "Edit papers" in data["error"], path
    assert claim_module.current(pool_paper(chief)) is None
    assert ReviewState.load(pool_paper(chief)).decisions == {}
    # What it is for still answers.
    assert _call(managing_page, "POST", "/api/chief/given-up", {}) == (200, {"given_up": []})


def test_the_chief_frees_a_paper_and_its_editor_hears_on_the_next_send(
        tmp_path, managing_page, chief):
    ling = editor_desk(tmp_path, chief, "Ling Wang")
    folder = ling.take("MOP001")

    status, data = _call(managing_page, "POST", "/api/chief/free",
                         {"folder": str(pool_paper(chief))})
    assert status == 200 and data["freed"] == {"paper": "MOP001", "who": "Ling Wang", "mode": "edit"}
    assert claim_module.current(pool_paper(chief)) is None

    _decide(folder, decision="rejected")
    with pytest.raises(remote.Refused, match="freed by the chief editor"):
        ling.send(folder)
    assert ReviewState.load(pool_paper(chief)).decisions == {}   # nothing came in
    assert ling.sync_view(folder)["held"] is False               # kept on Ling's computer
    editor_desk(tmp_path, chief, "Yue Hao").take("MOP001")       # free for anyone
    # Freeing a paper nobody holds changes nothing.
    assert _call(managing_page, "POST", "/api/chief/free",
                 {"folder": str(pool_paper(chief, "TUP002"))}) == (200, {"freed": None})


def test_edit_papers_opens_the_chiefs_own_editors_desk_which_closes_with_the_chief(
        tmp_path, chief):
    import sys
    import urllib.request

    import main
    from src.desk import editing

    home = tmp_path / "chief-settings" / "editor"
    desk = editing.EditingDesk(chief, command=[sys.executable, main.__file__], home=home,
                               extra_args=["--no-compile", "--no-llm"])
    try:
        url = desk.open()
        with urllib.request.urlopen(url + "api/setup", timeout=5) as response:
            setup = json.loads(response.read())
        assert setup["pool"]["connected"] is True
        # An editor's desk of its own: its own desk id, and no name until its
        # Indico token is pasted in.
        assert me_module.current(home).desk_id != chief.own_desk_id
        assert setup["editor"] == "" and setup["account"]["connected"] is False
        assert desk.open() == url                      # the same desk, not a second one
        process = desk.process
    finally:
        desk.close()
    assert process.wait(timeout=15) == 0               # it closed itself, cleanly
    assert editing.open_desk(home) is None


# ---------------------------------------------------------------------------
# Edited, then QA'd: passed, or failed back to editing
# ---------------------------------------------------------------------------

@pytest.fixture()
def pages(tmp_path, chief):
    """Ling's and Yue's desks, each with its page."""
    servers, out = [], {}
    for name in ("Ling Wang", "Yue Hao"):
        desk = editor_desk(tmp_path, chief, name)
        handler = partial(DeskHandler, root=desk.root, jobs=JobRunner(llm=False),
                          home=desk.home, pool=desk)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        out[name.split()[0].lower()] = (desk, httpd.server_address[1])
    yield out
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def _row(chief, paper="MOP001"):
    return {r["paper"]: r for r in chief.papers()}[paper]


def test_an_edited_paper_is_qad_failed_re_edited_and_passed(pages, chief):
    (ling, ling_port), (yue, yue_port) = pages["ling"], pages["yue"]
    pool = pool_paper(chief)
    assert _row(chief)["take"] == "edit"

    # Nobody can QA a paper not edited yet.
    status, data = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})
    assert status == 502 and "not been edited yet" in data["error"]

    # Ling edits it and finishes: it waits for its QA, with Ling as its editor.
    status, data = _call(ling_port, "POST", "/api/pool/take", {"paper": "MOP001"})
    folder = data["folder"]
    assert _call(ling_port, "POST", "/api/close", {"folder": folder, "status": "done"})[0] == 200
    assert _row(chief)["stage"] == "to_qa" and _row(chief)["take"] == "qa"
    status, data = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001"})
    assert status == 502 and "take it for QA" in data["error"]

    # Ling edited it, so Ling cannot QA it; Yue can.
    status, data = _call(ling_port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})
    assert status == 502 and "You edited MOP001" in data["error"]
    ling_row = {r["paper"]: r for r in ling.papers()}["MOP001"]
    assert ling_row["take"] == "" and ling_row["edited_by_you"] is True
    assert {r["paper"]: r for r in yue.papers()}["MOP001"]["take"] == "qa"
    assert [e["name"] for e in ReviewState.load(pool).edited_by] == ["Ling Wang"]

    # Yue takes it for QA. A QA is not finished like an edit, and does not
    # make Yue its editor.
    status, data = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})
    qa_folder = data["folder"]
    assert status == 200 and claim_module.current(pool).mode == "qa"
    assert _call(yue_port, "GET", "/api/paper?folder=" + qa_folder)[1]["sync"]["mode"] == "qa"
    status, data = _call(yue_port, "POST", "/api/close", {"folder": qa_folder})
    assert status == 400 and "pass or fail" in data["error"]
    _call(yue_port, "POST", "/api/paper-note", {"folder": qa_folder, "note": "checked"})
    status, data = _call(yue_port, "POST", "/api/qa", {"folder": qa_folder, "verdict": "failed"})
    assert status == 400 and "what needs fixing" in data["error"]

    # Failed: back to editing, with the note; nothing announced as given up.
    status, data = _call(yue_port, "POST", "/api/qa", {
        "folder": qa_folder, "verdict": "failed", "note": "Reference 7 has no DOI."})
    assert status == 200 and data["pool"] == "sent"
    state = ReviewState.load(pool)
    assert (state.status, state.qa.status, state.qa.by, state.editor) == (
        "in_review", "failed", "Yue Hao", "Ling Wang")
    assert claim_module.current(pool) is None and chief.given_up() == []
    row = _row(chief)
    assert (row["stage"], row["take"], row["qa"]["note"]) == (
        "to_reedit", "edit", "Reference 7 has no DOI.")

    # Ling re-edits and finishes: it waits for a new QA, the failure kept.
    status, data = _call(ling_port, "POST", "/api/pool/take", {"paper": "MOP001"})
    assert status == 200
    page = _call(ling_port, "GET", "/api/paper?folder=" + data["folder"])[1]
    assert page["qa"]["status"] == "failed" and page["stage"] == "to_reedit"
    _call(ling_port, "POST", "/api/close", {"folder": data["folder"], "status": "done"})
    state = ReviewState.load(pool)
    assert state.qa.status == "" and len(state.qa.history) == 1
    assert _row(chief)["stage"] == "to_qa"

    # Passed: done, and nothing is left to take it for.
    status, data = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})
    _call(yue_port, "POST", "/api/qa", {"folder": data["folder"], "verdict": "passed"})
    state = ReviewState.load(pool)
    assert (state.status, state.qa.status) == ("done", "passed")
    assert [h["status"] for h in state.qa.history] == ["failed", "passed"]
    assert _row(chief)["stage"] == "qa_passed" and _row(chief)["take"] == ""
    for mode in ("edit", "qa"):
        status, data = _call(ling_port, "POST", "/api/pool/take",
                             {"paper": "MOP001", "mode": mode})
        assert status == 502 and "QA is done" in data["error"]


def test_a_qa_given_up_without_a_verdict_is_announced_as_a_qa(pages, chief):
    (ling, ling_port), (yue, yue_port) = pages["ling"], pages["yue"]
    folder = _call(ling_port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]
    _call(ling_port, "POST", "/api/close", {"folder": folder, "status": "done"})
    qa_folder = _call(yue_port, "POST", "/api/pool/take",
                      {"paper": "MOP001", "mode": "qa"})[1]["folder"]

    _call(yue_port, "POST", "/api/claim", {"folder": qa_folder, "action": "release",
                                           "reason": "not my field"})
    notice = chief.given_up()[0]
    assert (notice["paper"], notice["mode"], notice["reason"]) == ("MOP001", "qa", "not my field")
    assert _row(chief)["take"] == "qa"                 # still waiting for its QA


def test_nobody_who_edited_a_paper_does_its_qa(tmp_path, pages, chief):
    (ling, ling_port), (yue, yue_port) = pages["ling"], pages["yue"]
    pool = pool_paper(chief)

    # Yue takes it to edit and gives it up untouched: Yue has not edited it.
    folder = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]
    _call(yue_port, "POST", "/api/claim", {"folder": folder, "action": "release"})
    folder = _call(ling_port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]
    _call(ling_port, "POST", "/api/close", {"folder": folder, "status": "done"})
    assert [e["name"] for e in ReviewState.load(pool).edited_by] == ["Ling Wang"]

    # Yue fails its QA, then re-edits it: now Ling and Yue have both edited it.
    qa = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})[1]["folder"]
    _call(yue_port, "POST", "/api/qa", {"folder": qa, "verdict": "failed", "note": "DOIs."})
    folder = _call(yue_port, "POST", "/api/pool/take", {"paper": "MOP001"})[1]["folder"]
    _call(yue_port, "POST", "/api/close", {"folder": folder, "status": "done"})
    assert [e["name"] for e in ReviewState.load(pool).edited_by] == ["Ling Wang", "Yue Hao"]
    for port in (ling_port, yue_port):
        status, data = _call(port, "POST", "/api/pool/take", {"paper": "MOP001", "mode": "qa"})
        assert status == 502 and "You edited MOP001" in data["error"]

    # A third editor does its QA.
    sam = editor_desk(tmp_path, chief, "Sam Third")
    assert {r["paper"]: r for r in sam.papers()}["MOP001"]["take"] == "qa"
    sam.take("MOP001", "qa")
    assert claim_module.current(pool).name == "Sam Third"

