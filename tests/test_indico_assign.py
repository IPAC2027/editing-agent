"""The chief's desk keeping Indico's editor assignments in step, and Indico accounts.

Editors take papers on their desks; the chief's desk assigns them in Indico
(``src.desk.indico_sync`` through ``src.indico_client.assign``). Tokens are
typed into the desks' pages (``src.desk.account``) and never shown again.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import httpx
import pytest
import respx

from src.desk import account
from src.desk import claim as claim_module
from src.desk import me as me_module
from src.desk import pool as pool_module
from src.desk.chief import Event
from src.desk.indico_sync import IndicoSync
from src.desk.state import ReviewState
from src.indico_client.assign import AssignmentConflict, AssignmentWriter
from src.indico_client.client import load_token
from src.indico_client.models import IndicoUser

BASE = "https://indico.example.org"
LING, YUE, SAM = 501, 502, 503          # Sam Lee has an Indico account, but is no editor
EDITORS_URL = f"{BASE}/event/194/editing/api/paper/editors"


def signed(user_id: int) -> str:
    """Indico's signed identity for a user, as its editors list gives it out."""
    return f"User:{user_id}:MTYwNg.sig{user_id}"


@pytest.fixture()
def conference(tmp_path: Path) -> Path:
    """The chief's pool: MOP001 free in Indico, TUP002 given to Yue Hao in Indico."""
    root = tmp_path / "IPAC27TEST"
    for code, contribution in (("MOP001", 11), ("TUP002", 12)):
        out = root / code / "original" / "aiagent_prescreen"
        (root / code / "original" / "Source_Files").mkdir(parents=True)
        (root / code / "original" / "Source_Files" / f"{code}.tex").write_text(
            "\\documentclass{jacow}\\begin{document}\\end{document}\n", encoding="utf-8")
        out.mkdir()
        (out / "report.json").write_text(json.dumps({"paper_id": code}), encoding="utf-8")
        (root / code / "manifest.json").write_text(json.dumps(
            {"code": code, "contribution_id": contribution}), encoding="utf-8")
    (root / "index.json").write_text(json.dumps({"event_id": 194, "base_url": BASE}),
                                     encoding="utf-8")
    (root / "indico_assignments.json").write_text(json.dumps({
        "checked_at": "2026-11-07T10:00:00+00:00",
        "papers": {
            "11": {"code": "MOP001", "editor": "", "state": "ready_for_review",
                   "editable_id": 901, "editor_id": None},
            "12": {"code": "TUP002", "editor": "Yue Hao", "state": "ready_for_review",
                   "editable_id": 902, "editor_id": YUE, "editor_identifier": signed(YUE)},
        }}), encoding="utf-8")
    return root


class FakeWriter:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def assign(self, editable_id, editor, *, current=None):
        if self.fail:
            raise self.fail
        self.calls.append(("assign", editable_id, editor, current))

    def unassign(self, editable_id, *, current):
        self.calls.append(("unassign", editable_id, current))


class FakeClient:
    """Indico's paper editors for the event (the chief's token reads them)."""

    def __init__(self, team=None, fail=None):
        self.team = team if team is not None else [
            IndicoUser(id=LING, full_name="Ling Wang", identifier=signed(LING)),
            IndicoUser(id=YUE, full_name="Yue Hao", identifier=signed(YUE))]
        self.fail, self.reads = fail, 0

    def editors(self):
        self.reads += 1
        if self.fail:
            raise self.fail
        return list(self.team)


def _sync(root: Path, writer: FakeWriter, *, on: bool = True,
          client: FakeClient | None = None) -> IndicoSync:
    event = Event(url=BASE, event_id=194)
    client = client or FakeClient()
    event.client = lambda: client                  # type: ignore[method-assign]
    sync = IndicoSync(root, event, writer_factory=lambda: writer, background=False)
    sync.read = lambda: None                        # type: ignore[method-assign]
    sync.set_enabled(on)
    return sync


def _me(name: str, desk: str) -> me_module.Me:
    return me_module.Me(desk_id=desk * 32, name=name)


def _editor(pool: pool_module.Pool, name: str, desk: str) -> me_module.Me:
    """An editor whose desk told the chief's who they are in Indico."""
    me = _me(name, desk)
    pool.identities[me.desk_id] = {
        "id": {"Ling Wang": LING, "Yue Hao": YUE, "Sam Lee": SAM}[name], "name": name}
    return me


def _live(root: Path) -> dict:
    return json.loads((root / "indico_assignments.json").read_text())["papers"]


# ---------------------------------------------------------------------------
# Taking and giving back on the desk, assigning in Indico
# ---------------------------------------------------------------------------

def test_taking_a_paper_assigns_the_editor_in_indico(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    pool.identities["a" * 32] = {"id": LING, "name": "Ling Wang"}

    pool.take("MOP001", _me("Ling Wang", "a"))
    sync.apply()

    assert writer.calls == [("assign", 901, signed(LING), None)]
    assert _live(conference)["11"]["editor"] == "Ling Wang"   # shown at once
    assert sync.view()["waiting"] == [] and sync.view()["problems"] == []


def test_an_editor_without_an_indico_account_cannot_take_a_paper(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)

    with pytest.raises(ValueError, match="Indico account"):
        pool.take("MOP001", _me("Ling Wang", "a"))
    sync.apply()

    assert writer.calls == []


def test_switching_the_sync_on_assigns_the_papers_already_being_edited(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer, on=False)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    pool.take("MOP001", _editor(pool, "Ling Wang", "a"))
    assert pool.assign_held() == []                       # off: nothing is sent
    sync.apply()
    assert writer.calls == []

    # The chief's desk restarted since (who was who is forgotten), then the
    # switch went on: the claim says who took the paper in Indico.
    pool = pool_module.Pool(conference, code="x", sync=sync)
    sync.set_enabled(True)
    assert pool.assign_held() == ["MOP001"]
    sync.apply()

    assert writer.calls == [("assign", 901, signed(LING), None)]
    assert claim_module.current(conference / "MOP001" / "original").indico_id == LING


def test_an_editor_indico_has_no_signed_identity_for_is_assigned_once_added(conference):
    # Sam is an editing manager, not in the paper editing team: Indico gives
    # out no signed identity for him, and its assignment route takes no other.
    client = FakeClient()
    writer = FakeWriter()
    sync = _sync(conference, writer, client=client)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    sam = _editor(pool, "Sam Lee", "c")
    pool.identities[sam.desk_id]["manager"] = True
    pool.take("MOP001", sam)
    sync.apply()

    assert writer.calls == []
    assert "paper editing team" in sync.view()["problems"][0]["message"]

    # The chief adds him to the team in Indico: the next read assigns it.
    client.team.append(IndicoUser(id=SAM, full_name="Sam Lee", identifier=signed(SAM)))
    sync._editors = (0.0, [])
    sync.apply()
    assert writer.calls == [("assign", 901, signed(SAM), None)]
    assert sync.view()["problems"] == []


def test_a_signed_identity_also_comes_from_a_paper_indico_gives_them(conference):
    # Not in the team list, but Indico shows them as some paper's editor.
    sync = _sync(conference, FakeWriter(), client=FakeClient(team=[]))
    assert sync.identifier(YUE) == signed(YUE)              # TUP002 is Yue's
    assert sync.identifier(LING) == "" and sync.identifier(None) == ""


def test_editors_desks_are_not_sent_signed_identities(conference):
    pool = pool_module.Pool(conference, code="x")
    sent = pool.conference()["indico_assignments.json"]["papers"]["12"]
    assert sent["editor"] == "Yue Hao" and "editor_identifier" not in sent
    on_disk = json.loads((conference / "indico_assignments.json").read_text())
    assert on_disk["papers"]["12"]["editor_identifier"] == signed(YUE)


def test_switching_the_sync_on_leaves_qa_and_indicos_own_choices_alone(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer, on=False)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    # TUP002 is Yue Hao's in Indico; Ling QAs MOP001 (no assignment for a QA).
    claim_module.take(conference / "MOP001" / "original", _me("Ling Wang", "a"),
                      mode="qa", indico_id=LING)
    pool.take("TUP002", _editor(pool, "Ling Wang", "a"))
    sync.set_enabled(True)

    assert pool.assign_held() == ["TUP002"]
    sync.apply()

    assert writer.calls == []
    assert "Indico gives it to Yue Hao" in sync.view()["problems"][0]["message"]


# ---------------------------------------------------------------------------
# Only Indico's paper editors edit
# ---------------------------------------------------------------------------

def test_only_indicos_paper_editors_take_papers_even_with_the_switch_off(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer, on=False)     # checking is reading: no switch
    pool = pool_module.Pool(conference, code="x", sync=sync)
    sam = _editor(pool, "Sam Lee", "c")

    for mode in ("edit", "qa"):
        with pytest.raises(ValueError, match="neither a paper editor nor an editing"):
            pool.take("MOP001", sam, mode)
    assert claim_module.current(conference / "MOP001" / "original") is None
    assert ReviewState.load(conference / "MOP001" / "original").editor == ""
    assert pool.you(sam) == {"indico_id": SAM, "name": "Sam Lee", "may_edit": False,
                             "why": pool.may_edit(sam), "role": ""}
    assert "Sam Lee (Indico user 503)" in pool.may_edit(sam)

    ling = _editor(pool, "Ling Wang", "a")
    assert pool.take("MOP001", ling)["mode"] == "edit"
    assert pool.you(ling)["may_edit"] is True
    assert pool.you(ling)["role"] == "paper editor"
    assert writer.calls == []


def test_an_editor_the_chief_just_added_in_indico_gets_in_at_once(conference, monkeypatch):
    from src.desk import indico_sync

    client = FakeClient()
    sync = _sync(conference, FakeWriter(), client=client)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    sam = _editor(pool, "Sam Lee", "c")

    with pytest.raises(ValueError, match="neither a paper editor"):
        pool.take("MOP001", sam)
    with pytest.raises(ValueError, match="neither a paper editor"):
        pool.take("MOP001", sam)
    assert client.reads == 1          # asked again soon: Indico is not read every time

    client.team.append(IndicoUser(id=SAM, full_name="Sam Lee",     # added in Indico
                                  identifier=signed(SAM)))
    monkeypatch.setattr(indico_sync, "EDITORS_RECHECK", 0.0)
    assert pool.take("MOP001", sam)["mode"] == "edit"
    assert client.reads == 2


def test_nobody_new_is_let_in_while_indico_cannot_say(conference):
    import time

    client = FakeClient(fail=RuntimeError("Indico answered 503"))
    sync = _sync(conference, FakeWriter(), client=client)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    ling, sam = _editor(pool, "Ling Wang", "a"), _editor(pool, "Sam Lee", "c")

    with pytest.raises(ValueError, match=r"could not read .*Indico answered 503"):
        pool.take("MOP001", ling)

    # A team read twenty minutes ago (old, so read again, which fails): who
    # was in it still is; nobody else gets in on it.
    sync._editors = (time.time() - 1200, FakeClient().team)
    assert pool.take("MOP001", ling)["mode"] == "edit"
    with pytest.raises(ValueError, match="could not read"):
        pool.take("TUP002", sam)


def test_an_editors_desk_and_the_chiefs_page_hear_who_is_no_paper_editor(conference,
                                                                          tmp_path):
    from src.desk import remote

    sync = _sync(conference, FakeWriter())
    pool = pool_module.Pool(conference, code="abcd-efgh-jkmn", port=0,
                            addresses=["127.0.0.1"], sync=sync)
    server = pool_module.start(pool, host="127.0.0.1")
    try:
        def desk(name, indico_id):
            home = tmp_path / name
            me_module.update_settings(home, indico_user={"id": indico_id, "name": name,
                                                         "url": BASE})
            (home / "indico_token").write_text("their-own-token-123456789")
            return remote.Joined(tmp_path / f"{name}-copies",
                                 remote.RemotePool(f"http://127.0.0.1:{pool.port}",
                                                   "abcd-efgh-jkmn", home=home),
                                 home=home, background=False)

        sam, ling = desk("Sam Lee", SAM), desk("Ling Wang", LING)
        listing = sam.listing()
        assert listing["you"]["may_edit"] is False
        assert "neither a paper editor" in listing["you"]["why"]
        assert {row["paper"] for row in listing["papers"]} == {"MOP001", "TUP002"}
        with pytest.raises(remote.PoolError, match="neither a paper editor nor an editing"):
            sam.take("MOP001")
        assert ling.listing()["you"]["may_edit"] is True

        seen = {e["name"]: e["paper_editor"] for e in pool.view()["editors"]}
        assert seen == {"Sam Lee": False, "Ling Wang": True}
    finally:
        server.shutdown()
        server.server_close()


def test_an_editing_manager_takes_papers_too_even_while_indico_is_unreadable(conference):
    # Indico lists editing managers to nobody: the editor's own desk asked
    # Indico about its account, and says so.
    client = FakeClient(fail=RuntimeError("Indico answered 503"))
    sync = _sync(conference, FakeWriter(), client=client)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    sam = _editor(pool, "Sam Lee", "c")
    pool.identities[sam.desk_id]["manager"] = True

    assert pool.take("MOP001", sam)["mode"] == "edit"
    assert pool.you(sam)["role"] == "editing manager"
    assert client.reads == 0                      # no need to read the editors list


@respx.mock
def test_indico_answers_each_account_whether_it_manages_the_editing():
    from src.indico_client.client import IndicoAuthError, IndicoClient

    route = respx.get(EDITORS_URL)
    client = IndicoClient(base_url=BASE, event_id=194, token="t" * 24)
    for status, expected in ((200, True), (403, False)):
        route.mock(return_value=httpx.Response(status, json=[]))
        assert client.can_manage_editing() is expected
    route.mock(return_value=httpx.Response(401))
    with pytest.raises(IndicoAuthError):
        client.can_manage_editing()
    assert {call.request.method for call in route.calls} == {"GET"}
    assert route.calls[0].request.headers["Authorization"] == "Bearer " + "t" * 24


@respx.mock
def test_an_editors_token_is_only_shown_to_its_own_indico(tmp_path):
    route = respx.get(url__regex=r".*/editing/api/paper/editors").mock(
        return_value=httpx.Response(200, json=[]))
    home = tmp_path / "sam"
    assert account.manages_editing(BASE, 194, home) == (None, "")      # no account
    me_module.update_settings(home, indico_user={"id": SAM, "name": "Sam Lee",
                                                 "url": BASE})
    (home / "indico_token").write_text("their-own-token-123456789")

    manager, why = account.manages_editing("https://indico.elsewhere.org", 194, home)
    assert manager is None and "connect a token from https://indico.elsewhere.org" in why
    assert not route.called

    assert account.manages_editing(BASE + "/", 194, home) == (True, "")
    assert route.calls[0].request.url == EDITORS_URL


@respx.mock
def test_an_editing_managers_desk_gets_in_and_a_non_editors_does_not(conference, tmp_path):
    from src.desk import remote

    def answer(request):        # Indico: Sam manages the editing, Kim does not
        token = request.headers["Authorization"].removeprefix("Bearer ")
        return httpx.Response(200 if token.startswith("sam") else 403, json=[])

    route = respx.get(EDITORS_URL).mock(side_effect=answer)
    sync = _sync(conference, FakeWriter())
    pool = pool_module.Pool(conference, code="abcd-efgh-jkmn", port=0,
                            addresses=["127.0.0.1"], sync=sync)
    server = pool_module.start(pool, host="127.0.0.1")
    try:
        def desk(name, indico_id, token):
            home = tmp_path / name
            me_module.update_settings(home, indico_user={"id": indico_id, "name": name,
                                                         "url": BASE})
            (home / "indico_token").write_text(token)
            return remote.Joined(tmp_path / f"{name}-copies",
                                 remote.RemotePool(f"http://127.0.0.1:{pool.port}",
                                                   "abcd-efgh-jkmn", home=home),
                                 home=home, background=False)

        sam = desk("Sam Lee", SAM, "sam-own-token-123456789")
        kim = desk("Kim Park", 504, "kim-own-token-123456789")

        you = sam.listing()["you"]
        assert you["may_edit"] is True and you["role"] == "editing manager"
        assert sam.take("MOP001").is_dir()

        assert kim.listing()["you"]["may_edit"] is False
        with pytest.raises(remote.PoolError, match="neither a paper editor"):
            kim.take("TUP002")

        seen = {e["name"]: (e["editing_manager"], e["paper_editor"])
                for e in pool.view()["editors"]}
        assert seen == {"Sam Lee": (True, False), "Kim Park": (False, False)}
        # Indico was asked with each editor's own token; the chief's desk
        # never had one.
        assert {c.request.headers["Authorization"][7:10] for c in route.calls} == {
            "sam", "kim"}
        assert "token" not in json.dumps(pool.identities)
    finally:
        server.shutdown()
        server.server_close()


def test_someone_not_in_the_editing_team_is_reported_not_guessed(conference):
    # Found by name (the chief's own desk): nobody in the team is that person.
    writer = FakeWriter()
    sync = _sync(conference, writer)

    sync.want("MOP001", name="Some Stranger")
    sync.apply()

    assert writer.calls == []
    assert "not in the event's editing team" in sync.view()["problems"][0]["message"]


def test_a_paper_indico_gives_to_someone_else_cannot_be_taken(conference):
    sync = _sync(conference, FakeWriter())
    pool = pool_module.Pool(conference, code="x", sync=sync)

    with pytest.raises(ValueError, match="assigned to Yue Hao"):
        pool.take("TUP002", _editor(pool, "Ling Wang", "a"))
    assert claim_module.current(conference / "TUP002" / "original") is None
    rows = {r["paper"]: r for r in pool.papers("a" * 32, _editor(pool, "Ling Wang", "a"))}
    assert rows["TUP002"]["blocked"] and not rows["MOP001"]["blocked"]


def test_the_editor_indico_gives_a_paper_to_sees_it_as_theirs_and_takes_it(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    yue = _editor(pool, "Yue Hao", "b")

    rows = {r["paper"]: r for r in pool.papers(yue.desk_id, yue)}
    assert rows["TUP002"]["indico"]["yours"] is True and not rows["TUP002"]["blocked"]
    pool.take("TUP002", yue)
    sync.apply()
    assert writer.calls == []                      # already theirs in Indico


def test_giving_back_unfinished_unassigns_but_finished_stays_assigned(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    pool.identities["a" * 32] = {"id": LING, "name": "Ling Wang"}
    ling = _me("Ling Wang", "a")

    pool.take("MOP001", ling)
    sync.apply()
    pool.release("MOP001", ling)
    sync.apply()
    assert writer.calls[-1] == ("unassign", 901, signed(LING))

    writer.calls.clear()
    pool.take("MOP001", ling)
    state = ReviewState.load(conference / "MOP001" / "original")
    state.status = "done"
    state.save(conference / "MOP001" / "original")
    pool.release("MOP001", ling)
    sync.apply()
    assert [c[0] for c in writer.calls] == ["assign"]


def test_the_chief_freeing_an_unfinished_paper_unassigns_its_editor(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    pool.take("MOP001", _editor(pool, "Ling Wang", "a"))
    sync.apply()

    assert pool.free("MOP001") == {"paper": "MOP001", "who": "Ling Wang", "mode": "edit"}
    sync.apply()
    assert writer.calls[-1] == ("unassign", 901, signed(LING))
    assert pool.free("MOP001") is None                 # nobody holds it now


def test_a_qa_never_changes_indicos_editor(conference):
    """TUP002 is Yue's in Indico; Ling may still QA it, and Indico is not told."""
    writer = FakeWriter()
    sync = _sync(conference, writer)
    pool = pool_module.Pool(conference, code="x", sync=sync)
    yue, ling = _editor(pool, "Yue Hao", "b"), _editor(pool, "Ling Wang", "a")
    folder = conference / "TUP002" / "original"
    pool.take("TUP002", yue)
    state = ReviewState.load(folder)
    state.status = "done"
    state.save(folder)
    pool.release("TUP002", yue)
    sync.apply()
    writer.calls.clear()

    rows = {r["paper"]: r for r in pool.papers(ling.desk_id, ling)}
    assert rows["TUP002"]["take"] == "qa" and not rows["TUP002"]["blocked"]
    assert pool.take("TUP002", ling, "qa")["mode"] == "qa"
    state = ReviewState.load(folder)
    state.status, state.qa.status = "in_review", "failed"      # failed back to editing
    state.save(folder)
    pool.release("TUP002", ling)
    sync.apply()

    assert writer.calls == [] and pool.given_up() == []
    assert ReviewState.load(folder).editor == "Yue Hao"


def test_nothing_is_written_while_the_switch_is_off(conference):
    writer = FakeWriter()
    sync = _sync(conference, writer, on=False)
    pool = pool_module.Pool(conference, code="x", sync=sync)

    pool.take("MOP001", _editor(pool, "Ling Wang", "a"))
    sync.apply()

    assert writer.calls == [] and sync.view()["enabled"] is False
    # And off, Indico's assignment does not stop anyone taking a paper.
    pool.take("TUP002", _editor(pool, "Ling Wang", "a"))


def test_the_switch_belongs_to_one_event(conference):
    _sync(conference, FakeWriter())
    other = Event(url=BASE, event_id=97)
    assert IndicoSync(conference, other, background=False).enabled is False


def test_a_paper_reassigned_in_indico_meanwhile_is_left_alone(conference):
    sync = _sync(conference, FakeWriter(fail=AssignmentConflict("Indico has a different "
                                                                 "editor on this paper now.")))
    pool = pool_module.Pool(conference, code="x", sync=sync)

    pool.take("MOP001", _editor(pool, "Ling Wang", "a"))
    sync.apply()

    assert "different editor" in sync.view()["problems"][0]["message"]


@respx.mock
def test_the_writer_sends_indicos_own_conflict_check():
    route = respx.post(f"{BASE}/event/194/editing/api/paper/editables/assign").mock(
        return_value=httpx.Response(200, json=[]))
    unroute = respx.post(f"{BASE}/event/194/editing/api/paper/editables/unassign").mock(
        return_value=httpx.Response(409, json={"editor_conflict": True}))
    writer = AssignmentWriter(base_url=BASE, event_id=194, token="t" * 24)

    writer.assign(901, signed(LING))
    body = json.loads(route.calls[0].request.content)
    assert body == {"editables": [901], "editor": signed(LING), "editor_assignments": {}}
    assert route.calls[0].request.headers["Authorization"] == "Bearer " + "t" * 24

    with pytest.raises(AssignmentConflict):
        writer.unassign(901, current=signed(YUE))
    assert json.loads(unroute.calls[0].request.content)["editor_assignments"] == {
        "901": signed(YUE)}

    # Indico refuses an unsigned "User:<id>" (422 "User id signature
    # missing"): the writer refuses it first, and sends nothing.
    from src.indico_client.client import IndicoError
    for bad in (f"User:{LING}", LING, "User:501:", "Group:5:x"):
        with pytest.raises(IndicoError, match="signed identity"):
            writer.assign(902, bad)
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# The Indico account, typed into the page
# ---------------------------------------------------------------------------

@respx.mock
def test_a_token_is_checked_with_indico_and_kept_privately(tmp_path, monkeypatch):
    monkeypatch.delenv("INDICO_TOKEN", raising=False)
    respx.get(f"{BASE}/api/user/").mock(return_value=httpx.Response(
        200, json={"id": LING, "first_name": "Ling", "last_name": "Wang", "email": "x"}))

    view = account.connect("  indico-token-abcdefghijklmnop  ", BASE)

    assert view == {"connected": True, "name": "Ling Wang", "id": LING, "url": BASE,
                    "source": "page"}
    path = account.token_path()
    assert path.read_text() == "indico-token-abcdefghijklmnop"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert load_token() == "indico-token-abcdefghijklmnop"
    assert me_module.load_settings()["editor"] == "Ling Wang"      # name filled in
    assert "indico-token" not in json.dumps(me_module.load_settings())

    account.disconnect()
    assert not path.exists() and account.view()["connected"] is False


@respx.mock
def test_a_token_indico_does_not_know_is_not_kept(monkeypatch):
    respx.get(f"{BASE}/api/user/").mock(return_value=httpx.Response(200, json=None))
    with pytest.raises(ValueError, match="did not accept"):
        account.connect("indico-token-abcdefghijklmnop", BASE)
    with pytest.raises(ValueError, match="does not look like"):
        account.connect("not a token\nat all", BASE)
    assert not account.token_path().exists()


def test_an_editors_desk_tells_the_chief_who_they_are_in_indico_not_the_token(tmp_path):
    root = tmp_path / "pool"
    (root / "MOP001" / "original").mkdir(parents=True)
    pool = pool_module.Pool(root, code="abcd-efgh-jkmn", port=0, addresses=["127.0.0.1"])
    server = pool_module.start(pool, host="127.0.0.1")
    try:
        from src.desk import remote

        home = tmp_path / "ling-home"
        me_module.update_settings(home, editor="Ling Wang",
                                  indico_user={"id": LING, "name": "Ling Wang", "url": BASE})
        (home / "indico_token").write_text("secret-token-value-123456")
        joined = remote.Joined(tmp_path / "copies",
                               remote.RemotePool(f"http://127.0.0.1:{pool.port}",
                                                 "abcd-efgh-jkmn"),
                               home=home, background=False)
        joined.papers()
        desk = me_module.current(home).desk_id
        assert pool.identities[desk] == {"id": LING, "name": "Ling Wang", "manager": False}
    finally:
        server.shutdown()
        server.server_close()


@respx.mock
def test_the_chiefs_page_connects_an_account_and_never_sees_the_token(conference, monkeypatch):
    import http.client
    import threading
    from functools import partial
    from http.server import ThreadingHTTPServer

    from src.desk.server import DeskHandler, JobRunner

    monkeypatch.delenv("INDICO_TOKEN", raising=False)
    respx.get(f"{BASE}/api/user/").mock(return_value=httpx.Response(
        200, json={"id": 77, "first_name": "Chief", "last_name": "Editor"}))
    event = Event(url=BASE, event_id=194)
    sync = IndicoSync(conference, event, background=False)
    sharing = pool_module.Pool(conference, code="x", sync=sync, addresses=["127.0.0.1"])
    # Ling took MOP001 to edit it while the switch was off.
    claim_module.take(conference / "MOP001" / "original", _me("Ling Wang", "a"),
                      indico_id=LING)
    handler = partial(DeskHandler, root=conference, jobs=JobRunner(llm=False),
                      chief=event, sync=sync, sharing=sharing)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]

    def call(method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"Host": f"127.0.0.1:{port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json",
                            "Origin": f"http://127.0.0.1:{port}"})
        conn.request(method, path, body=None if body is None else json.dumps(body),
                     headers=headers)
        response = conn.getresponse()
        text = response.read().decode()
        conn.close()
        return response.status, text

    try:
        status, text = call("POST", "/api/indico-account",
                            {"token": "chief-token-abcdefghijklmnop"})
        assert status == 200 and "Chief Editor" in text
        status, setup = call("GET", "/api/setup")
        assert json.loads(setup)["chief"]["token"] is True
        assert json.loads(setup)["account"]["name"] == "Chief Editor"
        assert json.loads(setup)["indico_sync"]["enabled"] is False
        status, text = call("POST", "/api/chief/indico-sync", {"enabled": True})
        assert json.loads(text)["enabled"] is True
        assert json.loads(text)["waiting"] == ["MOP001"]       # assigned now too
        assert sync.papers()["MOP001"]["indico_id"] == LING
        for path in ("/api/setup", "/api/worklist"):
            assert "chief-token" not in call("GET", path)[1]
        # No INDICO_TOKEN anywhere: reading and assigning both use the pasted token.
        assert "INDICO_TOKEN" not in os.environ
        assert event.client().token == "chief-token-abcdefghijklmnop"
        assert sync._writer().token == "chief-token-abcdefghijklmnop"
    finally:
        httpd.shutdown()
        httpd.server_close()
