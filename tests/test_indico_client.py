"""The Indico client, against payloads a real JACoW conference returned.

The fixtures below are trimmed but otherwise verbatim from indico.jacow.org
event 82 (HIAT2025). Testing against invented JSON would have hidden the one
thing that actually bit: a contribution has two ids and the editing routes take
the one an editor never sees.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from src.indico_client import tags as tagmod
from src.indico_client.client import (
    IndicoAuthError,
    IndicoClient,
    IndicoError,
    RevisionMoved,
    load_token,
)

BASE = "https://indico.jacow.org"
EVENT = 82

LIST_JSON = [
    {
        "code": "MOX01",
        "friendly_id": 4,
        "id": 6680,
        "title": "FRIB operations: first three years",
        "persons": ["Tanner Lange", "Yoichi Momozaki"],
        "keywords": [],
        "session": {"code": "MOX", "id": 560, "title": "Invited Talks"},
        "editable": {
            "id": 5440,
            "type": "paper",
            "state": "accepted",
            "revision_count": 3,
            "last_update_dt": "2025-06-23T00:14:17.037406",
            "editor": {"id": 3653, "full_name": "Kent Wootton",
                       "identifier": "User:3653:MzY1Mw.BpXUskrf"},
            "tags": [
                {"code": "TC14", "color": "violet", "id": 531,
                 "title": "Reference formatting: missing info added, DOI/URL added",
                 "system": False, "is_used_in_revision": True},
                {"code": "QA01", "color": "green", "id": 502, "title": "QA Approved",
                 "system": True, "is_used_in_revision": True},
            ],
            "timeline_url": "/event/82/contributions/6680/editing/paper",
        },
    },
    {
        "code": "WEP31",
        "friendly_id": 230,
        "id": 10016,
        "title": "Demonstration of cavity field mapping by falling drops of liquid",
        "persons": ["Lars Groening", "Xiaonan Du"],
        "keywords": [],
        "editable": None,
    },
]

TAGS_JSON = [
    {"code": "TC12", "color": "violet", "id": 530, "system": False,
     "is_used_in_revision": True, "title": "Badly formatted units"},
    {"code": "TC14", "color": "violet", "id": 531, "system": False,
     "is_used_in_revision": True, "title": "Reference formatting"},
    {"code": "QA01", "color": "green", "id": 502, "system": True,
     "is_used_in_revision": True, "title": "QA Approved"},
]


@pytest.fixture()
def client() -> IndicoClient:
    return IndicoClient(base_url=BASE, event_id=EVENT, token="indp_" + "x" * 42)


# ---------------------------------------------------------------------------
# The credential
# ---------------------------------------------------------------------------

def test_the_token_never_appears_in_a_repr(client: IndicoClient):
    """A traceback in an editor's terminal must not leak their Indico account."""
    text = repr(client)
    assert "x" * 42 not in text
    assert client.token not in text
    assert "indp_" in text  # enough to tell which token it is


def test_a_plain_http_host_is_refused():
    with pytest.raises(IndicoError, match="insecure"):
        IndicoClient(base_url="http://indico.example.org", event_id=1, token="indp_x")


def test_a_missing_token_explains_where_to_get_one(monkeypatch):
    monkeypatch.delenv("INDICO_TOKEN", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "keyring", None)
    with pytest.raises(IndicoAuthError, match="user/tokens"):
        load_token()


# ---------------------------------------------------------------------------
# Reading the worklist
# ---------------------------------------------------------------------------

@respx.mock
def test_the_worklist_parses_a_real_payload(client: IndicoClient):
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))

    rows = client.list_editables()

    assert [r.code for r in rows] == ["MOX01", "WEP31"]
    first = rows[0]
    assert first.submitted is True
    assert first.state == "accepted"
    assert first.editor_name == "Kent Wootton"
    assert first.tag_codes == ["TC14", "QA01"]
    assert first.editable.revision_count == 3


@respx.mock
def test_a_contribution_with_no_editable_is_not_submitted(client: IndicoClient):
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=LIST_JSON))

    unsubmitted = client.list_editables()[1]

    assert unsubmitted.submitted is False
    assert unsubmitted.state == "not_submitted"   # Indico shows this as "Unknown"
    assert unsubmitted.editor_name == ""


def test_the_editing_routes_use_the_database_id_not_the_friendly_one(
        client: IndicoClient):
    """The bug this pins: friendly_id 4 and id 6680 name the same paper.

    Indico's own ``timeline_url`` in the payload settles which one the editing
    routes take, and it is not the number the editor sees on the page.
    """
    row = __import__("src.indico_client.models", fromlist=["ContributionRow"]) \
        .ContributionRow.model_validate(LIST_JSON[0])

    assert row.friendly_id == 4 and row.id == 6680
    assert client.timeline_url(row.id).endswith(row.editable.timeline_url)


# ---------------------------------------------------------------------------
# What Indico says when it says no
# ---------------------------------------------------------------------------

@respx.mock
def test_a_redirect_to_login_is_reported_as_a_token_problem(client: IndicoClient):
    """The first thing that happens with a malformed Authorization header."""
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(302, headers={"location": "/login/?next=/event/82"}))

    with pytest.raises(IndicoAuthError, match="Bearer"):
        client.list_editables()


@respx.mock
def test_a_403_is_reported_as_a_scope_problem_not_a_crash(client: IndicoClient):
    respx.get(f"{BASE}/event/82/editing/api/paper/list").mock(
        return_value=httpx.Response(403, json={"error": "nope"}))

    with pytest.raises(IndicoAuthError, match="scope"):
        client.list_editables()


# ---------------------------------------------------------------------------
# The guard that protects the author's work
# ---------------------------------------------------------------------------

@respx.mock
def test_a_write_is_refused_when_the_author_has_submitted_again(client: IndicoClient):
    respx.get(f"{BASE}/event/82/api/contributions/6680/editing/paper").mock(
        return_value=httpx.Response(200, json={"revisions": [{"id": 11}, {"id": 12}]}))

    client.assert_unchanged(6680, 12)          # still current: fine

    with pytest.raises(RevisionMoved, match="submitted again"):
        client.assert_unchanged(6680, 11)      # worked offline on the old one


@respx.mock
def test_the_files_of_one_revision_are_downloaded_as_indicos_own_zip(
        client: IndicoClient, tmp_path: Path):
    url = f"{BASE}/event/82/contributions/6680/editing/paper/12/files.zip"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"PK\x03\x04zip"))

    written = client.download_revision_files(6680, 12, tmp_path / "a" / "files.zip")

    assert written.read_bytes().startswith(b"PK")


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

@respx.mock
def test_tags_are_resolved_against_the_event_not_a_hardcoded_table(
        client: IndicoClient):
    respx.get(f"{BASE}/event/82/editing/api/tags").mock(
        return_value=httpx.Response(200, json=TAGS_JSON))

    live = [t.model_dump() for t in client.tags()]
    ids, missing = tagmod.resolve(["TC12", "TC14", "TC03"], live)

    assert ids == [530, 531]
    assert missing == ["TC03"]      # reported, never invented


def test_the_service_owned_tags_are_never_written(client: IndicoClient):
    """QA01/QA02/QA03/PRC belong to the editing service's own QA gate."""
    ids, missing = tagmod.resolve(["QA01", "PRC", "TC12"],
                                  [{"code": c, "id": i} for c, i in
                                   [("QA01", 502), ("PRC", 501), ("TC12", 530)]])

    assert ids == [530]
    assert missing == []            # skipped deliberately, not "missing"


def test_repeated_findings_of_one_kind_become_one_tag():
    codes = tagmod.tag_codes_for(
        ["FMT-UNIT-01", "FMT-UNIT-01", "FMT-UNIT-02", "DOI-FMT-02"])
    assert codes == ["TC12", "TC14"]


def test_a_check_with_no_confident_mapping_proposes_nothing():
    assert tagmod.tag_codes_for(["BUILD-OK", "EDITOR-NOTE", "LLM-REVIEW-01"]) == []


def test_every_mapped_check_exists_and_every_mapped_tag_exists():
    """Neither side of the mapping may name something that is not real."""
    from src.desk import plain

    unknown_checks = set(tagmod.CHECK_TO_TAG) - set(plain.EXPLANATIONS)
    unknown_tags = set(tagmod.CHECK_TO_TAG.values()) - set(tagmod.VOCABULARY)

    assert not unknown_checks, f"mapped checks that do not exist: {unknown_checks}"
    assert not unknown_tags, f"mapped tags that do not exist: {unknown_tags}"


def test_every_tag_is_either_mapped_out_of_reach_or_the_services_own():
    """No code may be silently unaccounted for.

    This is the test that keeps the coverage claim honest: add a check that
    covers TC03 and this fails until TC03 moves out of OUT_OF_REACH.
    """
    covered = set(tagmod.CHECK_TO_TAG.values())
    accounted = covered | set(tagmod.OUT_OF_REACH) | set(tagmod.SERVICE_OWNED)

    assert set(tagmod.VOCABULARY) == accounted


def test_the_named_next_checks_are_the_ones_reachable_without_a_pdf():
    for code in tagmod.BUILDABLE_NEXT:
        assert "not implemented" in tagmod.OUT_OF_REACH[code]
