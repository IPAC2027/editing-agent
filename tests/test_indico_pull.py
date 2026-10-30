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
    manifest = json.loads((tmp_path / "MOX01" / "manifest.json").read_text(encoding="utf-8"))

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
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))

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


@respx.mock
def test_the_edited_version_is_the_latest_revision_with_files(client: IndicoClient):
    """Regression: the final revisions are often state changes without files
    ("accepted"); taking the very last one left most papers with only the
    author's version."""
    detail = json.loads(json.dumps(DETAIL_JSON))
    detail["revisions"].append({"id": 27100, "created_dt": "2025-06-25T10:00:00+00:00", "files": []})
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))
    respx.get(f"{BASE}/event/82/api/contributions/6680/editing/paper").mock(
        return_value=httpx.Response(200, json=detail))
    plan = build_plan(client)
    paper = next(p for p in plan.papers if p.row.code == "MOX01")
    assert [(r.role, r.revision.id) for r in paper.revisions] == [
        ("original", 26704), ("current", 26999)]
    assert "1 with an edited version" in plan.summary()


# --- File names an operating system cannot store (Oct 2026) -----------------------

def test_safe_filename():
    from src.indico_client.pull import safe_filename
    assert safe_filename("MOPA001*.pdf") == "MOPA001_.pdf"
    assert safe_filename('a<b>c:d"e|f?g.docx') == "a_b_c_d_e_f_g.docx"
    assert safe_filename("../../etc/passwd") == "passwd"          # never leaves the folder
    assert safe_filename("CON.pdf") == "_CON.pdf"
    assert safe_filename("paper. ") == "paper"
    assert safe_filename("MOPA001.pdf") == "MOPA001.pdf"


@respx.mock
def test_a_non_standard_file_name_does_not_stop_the_pull(client: IndicoClient, tmp_path):
    """Regression: "MOPA001*.pdf" stopped the pull; the next files never came."""
    from src.indico_client.pull import pull
    detail = json.loads(json.dumps(DETAIL_JSON))
    detail["revisions"][-1]["files"] = [
        {"id": 3, "filename": "MOX01*.pdf", "size": 5, "file_type": 191,
         "download_url": "/f/star.pdf", "external_download_url": ""},
        {"id": 4, "filename": "MOX01.docx", "size": 12, "file_type": 192,
         "download_url": "/f/broken.docx", "external_download_url": ""},
        {"id": 5, "filename": "MOX01-figures.zip", "size": 3, "file_type": 193,
         "download_url": "/f/figs.zip", "external_download_url": ""},
    ]
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))
    respx.get(f"{BASE}/event/82/api/contributions/6680/editing/paper").mock(
        return_value=httpx.Response(200, json=detail))
    respx.get(f"{BASE}/f/original.docx").mock(return_value=httpx.Response(200, content=b"0123456789"))
    respx.get(f"{BASE}/f/star.pdf").mock(return_value=httpx.Response(200, content=b"%PDF-"))
    respx.get(f"{BASE}/f/broken.docx").mock(return_value=httpx.Response(500))
    respx.get(f"{BASE}/f/figs.zip").mock(return_value=httpx.Response(200, content=b"zip"))
    plan = pull(client, tmp_path)
    current = tmp_path / "MOX01" / "current" / "Source_Files"
    assert (current / "MOX01_.pdf").read_bytes() == b"%PDF-"
    assert (current / "MOX01-figures.zip").exists()               # the pull went on
    assert not list(current.glob("*.part"))                       # nothing half-written left
    assert len(plan.failures) == 1 and "MOX01.docx" in plan.failures[0]
    manifest = json.loads((tmp_path / "MOX01" / "manifest.json").read_text(encoding="utf-8"))
    names = {f["filename"]: f["saved_as"] for r in manifest["revisions"] for f in r["files"]}
    assert names["MOX01*.pdf"] == "MOX01_.pdf"


# --- A restarted pull does not read finished papers again (Oct 2026) --------------

@respx.mock
def test_a_restarted_pull_skips_reading_finished_papers(client: IndicoClient, tmp_path):
    from src.indico_client.pull import build_plan, pull
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))
    detail = respx.get(f"{BASE}/event/82/api/contributions/6680/editing/paper").mock(
        return_value=httpx.Response(200, json=DETAIL_JSON))
    respx.get(f"{BASE}/f/original.docx").mock(return_value=httpx.Response(200, content=b"0123456789"))
    respx.get(f"{BASE}/f/current.docx").mock(return_value=httpx.Response(200, content=b"012345678901"))
    pull(client, tmp_path)
    assert json.loads((tmp_path / "MOX01" / "manifest.json").read_text(encoding="utf-8"))["complete"] is True
    calls = detail.call_count
    plan = build_plan(client, destination=tmp_path)
    assert detail.call_count == calls                      # not read again
    assert "1 already downloaded" in plan.summary() and not plan.fetchable
    # index.json still describes the finished paper fully
    pull(client, tmp_path, plan=plan)
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["papers"][0]["revisions"][1]["role"] == "current"


def test_an_old_manifest_without_the_edited_version_is_read_again(tmp_path):
    from src.indico_client.pull import _already_complete
    folder = tmp_path / "MOX01"
    (folder / "original" / "Source_Files").mkdir(parents=True)
    (folder / "original" / "Source_Files" / "MOX01.docx").write_bytes(b"0123456789")
    manifest = {"revision_count": 3, "note": "", "revisions": [
        {"role": "original", "files": [{"filename": "MOX01.docx", "size": 10}]}]}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert _already_complete(folder, "first-last") is None   # the old pull missed "current"
    manifest["revision_count"] = 1
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert _already_complete(folder, "first-last") is not None   # truly only the author's
