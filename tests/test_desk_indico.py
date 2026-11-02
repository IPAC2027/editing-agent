"""The desk shows who holds each paper in Indico.

Indico gives a paper to one editor at a time, but the desk works on local
copies, so nothing else stops two editors spending an hour on the same paper.
These tests pin that every pulled paper says who holds it, that "yours" follows
the name typed at the top of the desk, and that a live check can only read.
"""

from __future__ import annotations

import http.client
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import respx

from src.desk.indico import LIVE_FILE, refresh, same_person
from src.desk.paper import view
from src.desk.server import DeskHandler, JobRunner
from src.desk.state import submission_folders, worklist
from src.indico_client.client import IndicoAuthError, IndicoClient

BASE = "https://indico.jacow.org"
EVENT = 97
LIST_URL = f"{BASE}/event/{EVENT}/editing/api/paper/list"
TEX = "\\documentclass{jacow}\n\\begin{document}\n\\end{document}\n"


@pytest.fixture()
def pulled(tmp_path: Path) -> Path:
    """A pulled conference: one paper Ling Wang has taken, one nobody has."""
    root = tmp_path / "NAPAC2025"
    papers = [("MOP001", 101, "Ling Wang", "ready_for_review"),
              ("TUP002", 102, "", "ready_for_review")]
    for code, contribution_id, editor, state in papers:
        source = root / code / "original" / "Source_Files"
        source.mkdir(parents=True)
        (source / f"{code}.tex").write_text(TEX, encoding="utf-8")
        (root / code / "manifest.json").write_text(json.dumps({
            "code": code, "contribution_id": contribution_id,
            "editor": editor, "state": state,
        }), encoding="utf-8")
    (root / "index.json").write_text(json.dumps({
        "event_id": EVENT, "base_url": BASE, "editable_type": "paper",
        "papers": [],
    }), encoding="utf-8")
    return root


def _holders(root: Path, me: str) -> dict[str, tuple[str, str]]:
    return {row.paper_id: (row.indico.holder, row.indico.editor)
            for row in worklist(root, me=me)}


def _row(contribution_id: int, code: str, editor: str | None) -> dict:
    return {
        "id": contribution_id, "friendly_id": contribution_id, "code": code,
        "title": code, "persons": [],
        "editable": {
            "id": contribution_id + 1000, "type": "paper", "state": "ready_for_review",
            "editor": {"id": 7, "full_name": editor} if editor else None,
        },
    }


def test_each_pulled_paper_says_who_holds_it_in_indico(pulled: Path):
    assert _holders(pulled, me="Yue Hao") == {
        "MOP001": ("other", "Ling Wang"),
        "TUP002": ("nobody", ""),
    }


def test_a_paper_is_yours_when_the_desk_name_is_the_indico_name(pulled: Path):
    assert _holders(pulled, me="Ling Wang")["MOP001"] == ("you", "Ling Wang")


def test_the_name_match_ignores_case_spacing_and_accents():
    assert same_person("  ling   WÁNG ", "Ling Wang")
    assert not same_person("", "")
    assert not same_person("L. Wang", "Ling Wang")


def test_with_no_name_typed_nothing_is_claimed_as_yours(pulled: Path):
    assert _holders(pulled, me="")["MOP001"] == ("other", "Ling Wang")


def test_each_paper_links_to_its_own_page_in_indico(pulled: Path):
    row = worklist(pulled, me="")[0]

    assert row.indico.url == f"{BASE}/event/{EVENT}/contributions/101/editing/paper"
    assert row.indico.source == "pull"


def test_an_ordinary_folder_of_submissions_has_no_indico_column(tmp_path: Path):
    folder = tmp_path / "IPAC26" / "AAA001-revision-1_author" / "Source_Files"
    folder.mkdir(parents=True)
    (folder / "AAA001.tex").write_text(TEX, encoding="utf-8")

    assert [row.indico for row in worklist(tmp_path / "IPAC26")] == [None]


def test_the_open_paper_says_who_holds_it(pulled: Path):
    folder = submission_folders(pulled)[0]

    assert view(folder, default_editor="Ling Wang")["indico"]["holder"] == "you"
    assert view(folder, default_editor="Yue Hao")["indico"]["holder"] == "other"


def test_an_unprepared_pulled_paper_is_named_after_the_paper(pulled: Path):
    """Its folder is called "original"; the heading above the notice said so."""
    assert view(submission_folders(pulled)[0])["paper_id"] == "MOP001"


@respx.mock
def test_a_live_check_overrides_what_the_pull_recorded(pulled: Path, monkeypatch):
    """Ling Wang has since released MOP001, and Yue Hao has taken TUP002."""
    monkeypatch.setenv("INDICO_TOKEN", "indico-test-token-0123456789")
    route = respx.get(LIST_URL).mock(return_value=httpx.Response(200, json=[
        _row(101, "MOP001", None), _row(102, "TUP002", "Yue Hao"),
    ]))
    manifest = (pulled / "MOP001" / "manifest.json").read_text(encoding="utf-8")

    result = refresh(pulled)

    assert route.called and result["papers"] == 2
    assert _holders(pulled, me="Yue Hao") == {
        "MOP001": ("nobody", ""),
        "TUP002": ("you", "Yue Hao"),
    }
    assert worklist(pulled, me="")[0].indico.source == "indico"
    # The pull's own record is what the corpus measurements read; it stays as fetched.
    assert (pulled / "MOP001" / "manifest.json").read_text(encoding="utf-8") == manifest


def test_the_live_check_uses_a_read_only_client(pulled: Path, monkeypatch):
    seen: list[bool] = []

    def fake_list(self):
        seen.append(self.read_only)
        return []

    def fake_contributions(self):
        seen.append(self.read_only)
        return []

    monkeypatch.setenv("INDICO_TOKEN", "indico-test-token-0123456789")
    monkeypatch.setattr(IndicoClient, "list_editables", fake_list)
    monkeypatch.setattr(IndicoClient, "contributions", fake_contributions)

    refresh(pulled)

    assert seen == [True, True]


def test_a_paper_missing_from_the_live_check_keeps_what_the_pull_said(pulled: Path):
    (pulled / LIVE_FILE).write_text(json.dumps({
        "checked_at": "2026-11-02T10:00:00+00:00",
        "papers": {"102": {"code": "TUP002", "editor": "Yue Hao", "state": "accepted"}},
    }), encoding="utf-8")

    rows = {row.paper_id: row.indico for row in worklist(pulled, me="")}

    assert (rows["MOP001"].editor, rows["MOP001"].source) == ("Ling Wang", "pull")
    assert (rows["TUP002"].editor, rows["TUP002"].source) == ("Yue Hao", "indico")


def test_a_folder_not_pulled_from_indico_cannot_be_checked(tmp_path: Path):
    with pytest.raises(ValueError, match="not pulled from Indico"):
        refresh(tmp_path)


# ---------------------------------------------------------------------------
# Through the desk's own server
# ---------------------------------------------------------------------------

@pytest.fixture()
def desk(pulled: Path):
    (pulled / ".aiagent_desk.json").write_text(json.dumps({"editor": "Ling Wang"}),
                                               encoding="utf-8")
    handler = partial(DeskHandler, root=pulled, jobs=JobRunner(llm=False))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
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


def test_the_worklist_page_gets_holders_for_the_name_at_the_top(desk: int):
    status, data = _call(desk, "GET", "/api/worklist")

    assert status == 200
    assert data["indico"]["source"] == "pull"
    assert data["indico"]["event_url"] == f"{BASE}/event/{EVENT}"
    assert [p["indico"]["holder"] for p in data["papers"]] == ["you", "nobody"]


def test_a_check_without_a_token_says_how_to_get_one(desk: int, monkeypatch):
    def no_token(**_):
        raise IndicoAuthError("No Indico token found. Create one at <indico>/user/tokens/")

    monkeypatch.setattr("src.indico_client.client.load_token", no_token)

    status, data = _call(desk, "POST", "/api/indico-refresh", {})

    assert status == 502
    assert "No Indico token found" in data["error"]
