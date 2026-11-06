"""Nothing in the agent writes to Indico — yet.

Writing back (comments, judgments, revisions, a changed title or author list)
is planned, and every write needs a ``full:everything`` token, which is the
editor's whole account. Until that work is done on purpose, these tests make
"the desk only reads Indico" a fact of the code rather than a habit:

* a client refuses anything but GET unless it was opened to write;
* no code opens one to write, or sends a modifying request;
* "Check Indico now", the one place the desk talks to Indico, sends GETs only.

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
