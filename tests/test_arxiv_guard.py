"""arXiv lookups: cached, and rested after a failure (src.references)."""

from __future__ import annotations

import pytest

from jacow_formatter import net, sources
from src import references

URL = "https://export.arxiv.org/api/query?search_query=ti:%22Adam%22&start=0&max_results=3"


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    monkeypatch.setenv("AIAGENT_CACHE_DIR", str(tmp_path))
    monkeypatch.setitem(references._arxiv, "cache", None)
    monkeypatch.setitem(references._arxiv, "resting_until", 0.0)
    calls = []
    answers = {"body": b"<feed/>"}

    def fake(url, *args, **kwargs):
        calls.append(url)
        return answers["body"]

    return references._guarded_get_raw(fake), calls, answers


def test_the_guard_is_installed_where_the_formatter_calls_arxiv():
    assert hasattr(sources._http_get_raw, "__wrapped__")


def test_other_hosts_pass_straight_through(guard):
    get, calls, _ = guard
    for _ in range(2):
        assert get("https://api.crossref.org/works?q=x") == b"<feed/>"
    assert len(calls) == 2


def test_an_arxiv_answer_is_asked_for_once(guard):
    get, calls, _ = guard
    assert get(URL) == b"<feed/>"
    assert get(URL) == b"<feed/>"
    assert calls == [URL]


def test_after_a_failure_arxiv_is_left_alone_and_counted_as_not_checked(guard, capsys):
    get, calls, answers = guard
    answers["body"] = b""
    before = net.network_error_count()
    assert get(URL) == b""
    assert get(URL + "&other") == b""                  # not asked: arXiv is resting
    assert calls == [URL]
    assert net.network_error_count() > before          # "not checked", never "fabricated"
    assert capsys.readouterr().out.count("arXiv is not answering") == 1


def test_arxiv_is_asked_again_after_its_rest(guard, monkeypatch):
    get, calls, answers = guard
    answers["body"] = b""
    get(URL)
    monkeypatch.setitem(references._arxiv, "resting_until", 0.0)
    answers["body"] = b"<feed/>"
    assert get(URL) == b"<feed/>"
    assert len(calls) == 2
