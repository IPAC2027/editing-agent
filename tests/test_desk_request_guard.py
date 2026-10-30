"""The review desk refuses requests that did not come from its own page.

Regression: the desk parsed any POST body as JSON whatever its declared type
and never looked at Host or Origin, so a page the editor happened to visit
could send ``text/plain`` POSTs (no CORS preflight) to /api/decide or
/api/my-edit, and a rebinding domain could read /api/setup.
"""
from __future__ import annotations

import http.client
import json
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.desk.server import DeskHandler, JobRunner


@pytest.fixture()
def desk(tmp_path: Path):
    handler = partial(DeskHandler, root=tmp_path, jobs=JobRunner(llm=False))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _request(port: int, method: str, path: str, *, body: str | None = None,
             headers: dict[str, str] | None = None) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    status = conn.getresponse().status
    conn.close()
    return status


def test_the_desk_page_itself_still_works(desk: int):
    assert _request(desk, "GET", "/api/setup") == 200
    status = _request(desk, "POST", "/api/editor",
                      body=json.dumps({"editor": "A. Editor"}),
                      headers={"Content-Type": "application/json",
                               "Origin": f"http://127.0.0.1:{desk}"})
    assert status != 403


def test_a_foreign_host_header_is_refused(desk: int):
    assert _request(desk, "GET", "/api/setup",
                    headers={"Host": f"evil.example:{desk}"}) == 403


def test_a_plain_text_post_from_another_site_is_refused(desk: int):
    status = _request(desk, "POST", "/api/decide",
                      body=json.dumps({"folder": "x", "edit": "E001", "decision": "accept"}),
                      headers={"Content-Type": "text/plain",
                               "Origin": "https://evil.example"})
    assert status == 403


def test_a_json_post_with_a_foreign_origin_is_refused(desk: int):
    status = _request(desk, "POST", "/api/my-edit",
                      body=json.dumps({"folder": "x"}),
                      headers={"Content-Type": "application/json",
                               "Origin": "https://evil.example"})
    assert status == 403


def test_a_post_without_a_json_content_type_is_refused(desk: int):
    status = _request(desk, "POST", "/api/editor",
                      body=json.dumps({"editor": "x"}))
    assert status == 403


def test_the_reference_list_tab(desk: int):
    assert _request(desk, "GET", "/references") == 200
    conn = http.client.HTTPConnection("127.0.0.1", desk, timeout=30)
    conn.request("POST", "/api/format-references", body=json.dumps({
        "text": "[1] D. Okonkwo and S. Quist, “Gas-cooled thermal shields”, submitted to Cryogenics.\n"
                "[2] A. Alpha, “Exotic beams”, Phys. Rev. Lett., vol. 1, p. 011001, 2020.",
        "lookups": False}),
        headers={"Host": f"127.0.0.1:{desk}", "Content-Type": "application/json",
                 "Origin": f"http://127.0.0.1:{desk}"})
    data = json.loads(conn.getresponse().read())
    conn.close()
    rows = data["references"]
    assert [r["n"] for r in rows] == [1, 2]
    assert rows[0]["after"].endswith("submitted for publication.")
    assert rows[0]["kind"] == "suggested"


def test_the_reference_list_tab_refuses_other_sites(desk: int):
    status = _request(desk, "POST", "/api/format-references",
                      body=json.dumps({"text": "[1] x"}),
                      headers={"Content-Type": "text/plain", "Origin": "https://evil.example"})
    assert status == 403
