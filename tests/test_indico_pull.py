"""Pulling a conference: read-only, costed first, resumable.

The test that matters most here is the first one. "It only reads" is the kind of
promise that is true when written and false two refactors later, so it is
enforced by the client and pinned by a test that tries every modifying verb.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from src.indico_client.client import IndicoClient, ReadOnlyViolation
from src.indico_client.pull import build_plan, pull

BASE = "https://indico.jacow.org"

LIST_JSON = [
    {"code": "MOX01", "friendly_id": 4, "id": 6680, "title": "FRIB operations",
     "persons": ["A. Author"],
     "editable": {"id": 5440, "state": "accepted", "revision_count": 2,
                  "editor": {"id": 1, "full_name": "Kent Wootton"},
                  "tags": [{"id": 531, "code": "TC14", "title": "Reference formatting"},
                           {"id": 502, "code": "QA01", "title": "QA Approved"}]}},
    {"code": "WEP31", "friendly_id": 230, "id": 10016, "title": "Falling drops",
     "persons": [], "editable": None},
]

DETAIL_JSON = {
    "id": 5440,
    "can_comment": True,
    "revisions": [
        {"id": 26704, "created_dt": "2025-06-19T23:18:16+00:00",
         "files": [{"id": 1, "filename": "MOX01.docx", "size": 10, "file_type": 192,
                    "download_url": "/f/original.docx", "external_download_url": ""}]},
        {"id": 26999, "created_dt": "2025-06-23T00:14:17+00:00",
         "files": [{"id": 2, "filename": "MOX01.docx", "size": 12, "file_type": 192,
                    "download_url": "/f/current.docx", "external_download_url": ""}]},
    ],
}


def _mock_reads() -> None:
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))
    respx.get(f"{BASE}/event/82/api/contributions/6680/editing/paper").mock(
        return_value=httpx.Response(200, json=DETAIL_JSON))
    respx.get(f"{BASE}/f/original.docx").mock(
        return_value=httpx.Response(200, content=b"AAAAAAAAAA"))
    respx.get(f"{BASE}/f/current.docx").mock(
        return_value=httpx.Response(200, content=b"BBBBBBBBBBBB"))


@pytest.fixture()
def client() -> IndicoClient:
    return IndicoClient(base_url=BASE, event_id=82, token="indp_" + "x" * 42,
                        read_only=True)


# ---------------------------------------------------------------------------
# The promise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_a_read_only_client_refuses_to_send_anything_that_changes_indico(
        client: IndicoClient, method: str):
    with pytest.raises(ReadOnlyViolation, match="Nothing has been sent"):
        client.request(method, f"{BASE}/event/82/editing/api/tags")


@respx.mock
def test_pulling_a_conference_issues_no_request_but_get(client: IndicoClient,
                                                        tmp_path: Path):
    _mock_reads()

    pull(client, tmp_path)

    methods = {call.request.method for call in respx.calls}
    assert methods == {"GET"}


def test_the_bulk_archive_endpoint_is_deliberately_not_used():
    """Indico can zip a whole conference, but preparing it is a POST.

    A read-only pull cannot use it, and must not be tempted to later.
    """
    source = Path("src/indico_client/pull.py").read_text(encoding="utf-8")
    assert "prepare-" not in source.replace("bulk-archive endpoint", "")


# ---------------------------------------------------------------------------
# Costing it before doing it
# ---------------------------------------------------------------------------

@respx.mock
def test_the_plan_knows_the_size_without_downloading_anything(client: IndicoClient):
    _mock_reads()

    plan = build_plan(client)

    assert plan.bytes == 22          # 10 + 12, straight from the metadata
    assert plan.files == 2
    assert not [c for c in respx.calls if c.request.url.path.startswith("/f/")]


@respx.mock
def test_a_paper_with_nothing_submitted_is_reported_not_fetched(client: IndicoClient):
    _mock_reads()

    plan = build_plan(client)
    unsubmitted = [p for p in plan.papers if p.row.code == "WEP31"][0]

    assert unsubmitted.revisions == []
    assert unsubmitted.note == "nothing submitted"
    assert "1 with nothing to fetch" in plan.summary()


@respx.mock
def test_first_last_takes_the_authors_original_and_the_current_state(
        client: IndicoClient):
    _mock_reads()

    paper = build_plan(client, which="first-last").fetchable[0]

    assert [(r.role, r.revision.id) for r in paper.revisions] == [
        ("original", 26704), ("current", 26999)]


@respx.mock
def test_latest_only_takes_one_revision(client: IndicoClient):
    _mock_reads()
    paper = build_plan(client, which="latest").fetchable[0]
    assert [r.role for r in paper.revisions] == ["current"]


# ---------------------------------------------------------------------------
# What lands on disk
# ---------------------------------------------------------------------------

@respx.mock
def test_the_layout_is_the_one_prescreen_already_understands(client: IndicoClient,
                                                             tmp_path: Path):
    _mock_reads()

    pull(client, tmp_path)

    assert (tmp_path / "MOX01" / "original" / "Source_Files" / "MOX01.docx").exists()
    assert (tmp_path / "MOX01" / "current" / "Source_Files" / "MOX01.docx").exists()
    # Distinct content: the point of the exercise is the difference between them.
    original = (tmp_path / "MOX01" / "original" / "Source_Files" / "MOX01.docx")
    current = (tmp_path / "MOX01" / "current" / "Source_Files" / "MOX01.docx")
    assert original.read_bytes() != current.read_bytes()


@respx.mock
def test_the_manifest_carries_the_editors_labels(client: IndicoClient, tmp_path: Path):
    """The tags are why this corpus is worth having."""
    _mock_reads()

    pull(client, tmp_path)
    manifest = json.loads((tmp_path / "MOX01" / "manifest.json").read_text())

    assert [t["code"] for t in manifest["tags"]] == ["TC14", "QA01"]
    assert manifest["editor"] == "Kent Wootton"
    assert manifest["contribution_id"] == 6680      # the id the routes take
    assert manifest["friendly_id"] == 4             # the one an editor sees
    assert [r["role"] for r in manifest["revisions"]] == ["original", "current"]


@respx.mock
def test_the_index_lists_every_paper_including_the_unsubmitted_ones(
        client: IndicoClient, tmp_path: Path):
    _mock_reads()

    pull(client, tmp_path)
    index = json.loads((tmp_path / "index.json").read_text())

    assert index["event_id"] == 82
    assert [p["code"] for p in index["papers"]] == ["MOX01", "WEP31"]


@respx.mock
def test_a_second_pull_downloads_nothing_it_already_has(client: IndicoClient,
                                                        tmp_path: Path):
    """190 papers of Word documents is not something to fetch twice."""
    _mock_reads()
    pull(client, tmp_path)
    before = len([c for c in respx.calls if c.request.url.path.startswith("/f/")])

    pull(client, tmp_path)
    after = len([c for c in respx.calls if c.request.url.path.startswith("/f/")])

    assert before == 2
    assert after == before      # nothing re-fetched


@respx.mock
def test_a_truncated_file_is_fetched_again(client: IndicoClient, tmp_path: Path):
    """Resume must not mistake half a download for a complete one."""
    _mock_reads()
    pull(client, tmp_path)
    target = tmp_path / "MOX01" / "original" / "Source_Files" / "MOX01.docx"
    target.write_bytes(b"AA")           # as if the pull died mid-file

    pull(client, tmp_path)

    assert target.read_bytes() == b"AAAAAAAAAA"


@respx.mock
def test_only_selects_papers_by_code(client: IndicoClient, tmp_path: Path):
    _mock_reads()

    plan = build_plan(client, only={"WEP31"})

    assert [p.row.code for p in plan.papers] == ["WEP31"]
