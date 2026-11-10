"""The agent reads Indico, and writes exactly one thing: who edits a paper.

Writing back (comments, judgments, revisions, a changed title or author list)
is planned, and every write needs a ``full:everything`` token, which is the
editor's whole account. The one write done so far is the chief's desk keeping
Indico's editor assignments in step (``src.indico_client.assign``, switched on
per event on the chief's page). These tests make that boundary a fact of the
code rather than a habit:

* a client refuses anything but GET unless it was opened to write;
* no code opens one to write, or sends a modifying request;
* the assignment writer sends only its two requests, for its own event, and
  only the chief's sync uses it;
* "Check Indico now" sends GETs only.

(``conftest.py`` separately stops any test from reaching a real server.)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from src.desk.indico import refresh
from src.indico_client.client import IndicoClient, ReadOnlyViolation

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://indico.jacow.org"
EVENT = 97


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@respx.mock
def test_a_client_refuses_to_change_indico_unless_opened_to_write(method: str):
    client = IndicoClient(base_url=BASE, event_id=EVENT, token="t" * 20)

    assert client.read_only is True
    with pytest.raises(ReadOnlyViolation, match="Nothing has been sent"):
        client.request(method, f"{BASE}/event/{EVENT}/editing/api/paper/list")
    assert respx.calls.call_count == 0


def _sources() -> list[Path]:
    return ([ROOT / "main.py"] + sorted((ROOT / "src").rglob("*.py"))
            + sorted((ROOT / "scripts").rglob("*.py")))


def test_no_code_opens_an_indico_client_that_may_write():
    offenders = [f"{path.relative_to(ROOT)}:{n}"
                 for path in _sources()
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if re.search(r"read_only\s*=\s*False", line)]
    assert offenders == []


def test_no_code_sends_a_modifying_request_to_indico():
    pattern = re.compile(r"""\.(?:request|stream)\(\s*["'](?:POST|PUT|PATCH|DELETE)["']""")
    offenders = [f"{path.relative_to(ROOT)}:{n}"
                 for path in _sources()
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if pattern.search(line)]
    assert offenders == []


@respx.mock
def test_check_indico_now_sends_only_gets(tmp_path: Path, monkeypatch):
    root = tmp_path / "NAPAC2025"
    (root / "MOP001" / "original" / "Source_Files").mkdir(parents=True)
    (root / "index.json").write_text(json.dumps(
        {"event_id": EVENT, "base_url": BASE, "editable_type": "paper", "papers": []}),
        encoding="utf-8")
    monkeypatch.setenv("INDICO_TOKEN", "indico-test-token-0123456789")
    respx.get(f"{BASE}/event/{EVENT}/editing/api/paper/list").mock(
        return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/export/event/{EVENT}.json").mock(
        return_value=httpx.Response(200, json={"results": [{"contributions": []}]}))

    refresh(root)

    assert [call.request.method for call in respx.calls] == ["GET", "GET"]


def test_only_the_chiefs_sync_uses_the_assignment_writer():
    users = sorted(str(path.relative_to(ROOT)) for path in _sources()
                   if "AssignmentWriter" in path.read_text(encoding="utf-8"))
    assert users == ["src/desk/indico_sync.py", "src/indico_client/assign.py"]


def test_the_assignment_writer_sends_nothing_but_assign_and_unassign():
    from src.indico_client.assign import AssignmentWriter
    from src.indico_client.client import IndicoError

    writer = AssignmentWriter(base_url=BASE, event_id=194, token="t" * 20)
    assert writer.url("assign") == f"{BASE}/event/194/editing/api/paper/editables/assign"
    for action in ("judge", "comment", "../../manage", "assign/me"):
        with pytest.raises(IndicoError):
            writer.url(action)
    with pytest.raises(IndicoError, match="insecure"):
        AssignmentWriter(base_url="http://indico.jacow.org", event_id=194, token="t" * 20)
    assert "t" * 20 not in repr(writer)
