"""The command line's two modes: editor (default) and chief editor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import main
from src.desk import me as me_module


@pytest.fixture
def calls(monkeypatch):
    """Record what a run would serve, without serving."""
    seen: dict = {"serve": []}
    monkeypatch.setattr("src.desk.server.serve",
                        lambda root, **kw: seen["serve"].append((Path(root), kw.get("chief"))))
    monkeypatch.delenv("INDICO_EVENT", raising=False)
    monkeypatch.delenv("INDICO_URL", raising=False)
    monkeypatch.setattr("src.indico_client.client.TYPED_TOKEN_ONLY", False)
    return seen


def _run(*args: str) -> int:
    try:
        main.main(list(args))
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _paper(root: Path, code: str) -> Path:
    folder = root / code
    folder.mkdir(parents=True)
    (folder / f"{code}.tex").write_text("\\documentclass{jacow}\n\\begin{document}\\end{document}\n")
    return folder


def test_editor_mode_opens_the_desk_without_the_chief_part(tmp_path, calls):
    _paper(tmp_path, "MOP001")
    assert _run(str(tmp_path)) == 0
    assert calls["serve"] == [(tmp_path.resolve(), None)]


def test_editor_mode_remembers_the_folder_for_next_time(tmp_path, calls):
    _run(str(tmp_path))
    assert me_module.load_settings()["papers"] == str(tmp_path.resolve())
    _run()
    assert [root for root, _ in calls["serve"]] == [tmp_path.resolve()] * 2


def test_chief_mode_opens_the_desk_on_the_event_even_with_an_empty_folder(tmp_path, calls):
    folder = tmp_path / "IPAC27TEST"                       # does not exist yet
    assert _run(str(folder), "--manage", "--event", "194") == 0
    root, chief = calls["serve"][0]
    assert root == folder.resolve() and folder.is_dir()
    assert (chief.url, chief.event_id) == ("https://indico.jacow.org", 194)


def test_chief_mode_takes_the_event_from_the_folder_after_the_first_download(tmp_path, calls):
    (tmp_path / "index.json").write_text(json.dumps(
        {"event_id": 194, "base_url": "https://indico.example.org"}))
    assert _run(str(tmp_path), "--manage") == 0
    chief = calls["serve"][0][1]
    assert (chief.url, chief.event_id) == ("https://indico.example.org", 194)


def test_chief_mode_without_an_event_lets_the_page_choose_it(tmp_path, calls):
    assert _run(str(tmp_path), "--manage") == 0
    assert calls["serve"][0][1].event_id is None


def test_chief_mode_refuses_to_mix_two_conferences_in_one_folder(tmp_path, calls):
    (tmp_path / "index.json").write_text(json.dumps({"event_id": 97}))
    assert _run(str(tmp_path), "--manage", "--event", "194") == 1
    assert calls["serve"] == []


def test_an_event_in_the_environment_is_not_taken_for_a_new_folder(tmp_path, calls, monkeypatch):
    """.env may name another conference's event; a new folder must not fetch it."""
    monkeypatch.setenv("INDICO_EVENT", "97")
    assert _run(str(tmp_path), "--manage") == 0
    assert calls["serve"][0][1].event_id is None


def test_maintainer_commands_answer_under_tools_and_their_old_names():
    assert main.route(["tools", "rules", "-q", "doi"]) == ("tools", ["rules", "-q", "doi"])
    assert main.route(["prescreen-all", "x"]) == ("tools", ["prescreen-all", "x"])
    assert main.route(["desk", "x"]) == ("tools", ["desk", "x"])
    assert main.route(["../IPAC27TEST", "--manage"]) == ("start", ["../IPAC27TEST", "--manage"])
    assert main.route([]) == ("start", [])


# ---------------------------------------------------------------------------
# An editor joined to the chief's desk has no folder to choose
# ---------------------------------------------------------------------------

JOIN = ("--join", "127.0.0.1:9", "--code", "abcd-efgh-jkmn")   # nobody answers there


def test_a_joined_editor_works_in_the_desks_own_folder(calls):
    assert _run(*JOIN) == 0
    working = me_module.settings_dir() / "working" / "127.0.0.1-9"
    assert calls["serve"][0][0] == working and working.is_dir()
    # Next time nothing needs to be given: the same desk opens.
    assert _run() == 0
    assert calls["serve"][1][0] == working


def test_a_joined_editor_is_not_asked_for_a_folder(tmp_path, calls):
    assert _run(str(tmp_path), *JOIN) == 1
    assert calls["serve"] == []


def test_the_launcher_opens_the_joined_desk_else_its_own_folder(tmp_path, calls):
    alone = tmp_path / "submissions"                 # does not exist yet
    assert _run("--alone-in", str(alone)) == 0
    assert calls["serve"][0][0] == alone.resolve() and alone.is_dir()
    _run(*JOIN)
    # Joined since: the chief's desk wins over the folder used before.
    assert _run("--alone-in", str(alone)) == 0
    assert calls["serve"][2][0] == me_module.settings_dir() / "working" / "127.0.0.1-9"


def test_a_folder_the_chiefs_desk_is_sharing_is_not_opened_directly(tmp_path, calls):
    import socket

    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen()
    try:
        (tmp_path / ".pool_door.json").write_text(json.dumps(
            {"pid": 1, "port": listening.getsockname()[1]}))
        assert _run(str(tmp_path)) == 1                     # an editor, directly
        assert _run(str(tmp_path), "--manage") == 1          # a second chief's desk
        assert calls["serve"] == []
    finally:
        listening.close()
    assert _run(str(tmp_path)) == 0                         # once that desk is gone


# ---------------------------------------------------------------------------
# On the chief's own computer, an editor's desk has settings of its own
# ---------------------------------------------------------------------------

def _the_chiefs_settings(papers: Path) -> dict:
    from src.desk import pool as pool_module

    pool_module.join_code()                      # the chief's door opened once
    me_module.update_settings(editor="EiC", papers=str(papers))
    return me_module.load_settings()


def test_an_editor_joining_on_the_chiefs_computer_is_not_the_chief(tmp_path, calls, monkeypatch):
    chief_home = me_module.settings_dir()
    _the_chiefs_settings(tmp_path)
    chief_id = me_module.current().desk_id
    chiefs = me_module.load_settings()

    assert _run(*JOIN) == 0
    editor_home = chief_home / me_module.EDITOR_HOME
    assert calls["serve"][0][0] == editor_home / "working" / "127.0.0.1-9"
    # This process is the editor's desk from here on: its own id, no name yet.
    assert me_module.settings_dir() == editor_home
    assert me_module.current().desk_id != chief_id and me_module.current().name == ""
    assert me_module.load_settings()["pool_url"] == "http://127.0.0.1:9"
    # The chief's settings are as they were: no join recorded in them.
    assert me_module.load_settings(chief_home) == chiefs
    # Nor is the chief's Indico token this desk's: only one typed into it.
    from src.indico_client import client

    monkeypatch.setenv("INDICO_TOKEN", "the-chiefs-token")
    with pytest.raises(client.IndicoAuthError, match="editor's own token"):
        client.load_token()
    client.saved_token_path().write_text("the-editors-token")
    assert client.saved_token_path().parent == editor_home
    assert client.load_token() == "the-editors-token"

    # Next time, plain 'aiagent' opens the same editor's desk; --manage the chief's.
    monkeypatch.setenv(me_module.HOME_ENV, str(chief_home))
    assert _run() == 0
    assert calls["serve"][1][0] == editor_home / "working" / "127.0.0.1-9"
    monkeypatch.setenv(me_module.HOME_ENV, str(chief_home))
    assert _run("--manage") == 0
    assert calls["serve"][2][0] == tmp_path.resolve() and calls["serve"][2][1] is not None
    assert me_module.current().desk_id == chief_id


def test_a_join_once_saved_with_the_chiefs_settings_is_dropped(tmp_path, calls):
    _the_chiefs_settings(tmp_path)
    me_module.update_settings(pool_url="http://10.9.0.3:8770", pool_join_code="abcd-efgh-jkmn")
    assert _run() == 0                            # not an editor's desk on the chief's id
    assert calls["serve"] == [(tmp_path.resolve(), None)]
    assert "pool_url" not in me_module.load_settings()
    assert "pool_join_code" not in me_module.load_settings()


def test_an_editors_own_computer_keeps_its_settings_where_they_are(calls):
    home = me_module.settings_dir()
    assert _run(*JOIN) == 0
    assert me_module.settings_dir() == home
    assert me_module.load_settings()["pool_url"] == "http://127.0.0.1:9"
    from src.indico_client import client

    assert client.TYPED_TOKEN_ONLY is False


# ---------------------------------------------------------------------------
# The chief's desk manages; the chief edits on an editor's desk of their own
# ---------------------------------------------------------------------------

def test_the_chiefs_desk_always_opens_the_door_and_no_share_keeps_it_here(
        tmp_path, calls, monkeypatch):
    seen = []
    monkeypatch.setattr("src.desk.server.serve", lambda root, **kw: seen.append(kw))
    assert _run(str(tmp_path), "--manage", "--no-share") == 0
    alone = seen[0]
    assert alone["door_host"] == "127.0.0.1" and alone["sharing"].local_only
    assert alone["sharing"].view()["addresses"] == ["http://127.0.0.1:8770"]
    # Edit papers starts an editor's desk with settings of its own.
    assert alone["editing"].home == me_module.settings_dir() / me_module.EDITOR_HOME
    assert "--no-compile" not in alone["editing"].extra_args

    assert _run(str(tmp_path), "--manage") == 0
    assert seen[1]["door_host"] == "0.0.0.0" and not seen[1]["sharing"].local_only


def test_a_second_desk_with_the_same_settings_sends_you_to_the_first(calls, monkeypatch):
    monkeypatch.setattr("src.desk.editing.open_desk", lambda home: "http://127.0.0.1:8766/")
    assert _run(*JOIN, "--no-open") == 0
    assert calls["serve"] == []


def test_the_old_name_chief_still_opens_the_managing_page(tmp_path, calls):
    assert _run(str(tmp_path), "--chief") == 0
    assert calls["serve"][0][1] is not None


def test_manage_and_join_are_two_desks(tmp_path, calls):
    assert _run(str(tmp_path), "--manage", *JOIN) == 1
    assert calls["serve"] == []

