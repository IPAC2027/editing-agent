"""Tests for the dynamic JabRef CSV discovery in src.refs.journal_abbrev.

The hardcoded URL list was deleted after the user observed that
``journal_abbreviations_aps.csv`` had been removed from the JabRef repo
(it returned HTTP 404).  The loader now queries the GitHub Contents API
to discover the live set of ``*.csv`` files and falls back to a snapshot
when the API is unreachable.

These tests are offline by default: they exercise the fallback path and
the parsing of a synthesised response.  A live-network test (marked
``network``) is included for when the suite is run with internet access.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make sure the offline test guard is in place even if conftest.py is
# reordered; the discovery fallback must not depend on network here.
import os

os.environ.setdefault("AIAGENT_DISABLE_JABREF", "1")

from src.refs import journal_abbrev as jabref_module
from src.refs.journal_abbrev import (
    JABREF_FALLBACK_NAMES,
    list_jabref_csvs,
    normalize_journal,
)


# ── fallback (offline) ──────────────────────────────────────────────────────

def test_fallback_list_is_non_empty():
    assert len(JABREF_FALLBACK_NAMES) >= 6, (
        "fallback should snapshot the most-recently-known JabRef CSVs; "
        "shrinking below 6 would mean the snapshot has rotted"
    )


def test_fallback_all_names_end_with_csv():
    for name in JABREF_FALLBACK_NAMES:
        assert name.endswith(".csv"), name


def test_fallback_omits_aps_that_was_404():
    """Regression: the broken ``aps`` file must NOT be in the fallback."""
    assert "journal_abbreviations_aps.csv" not in JABREF_FALLBACK_NAMES


def test_fallback_includes_major_subjects():
    # These are the well-known categories that have been stable for years.
    expected = {
        "journal_abbreviations_acs.csv",
        "journal_abbreviations_ieee.csv",
        "journal_abbreviations_general.csv",
        "journal_abbreviations_entrez.csv",
        "journal_abbreviations_mechanical.csv",
    }
    missing = expected - set(JABREF_FALLBACK_NAMES)
    assert not missing, f"fallback missing expected CSVs: {missing}"


def test_list_jabref_csvs_falls_back_when_api_down(monkeypatch):
    """When the GitHub API is unreachable, list_jabref_csvs returns the
    hardcoded fallback list, shaped like the API response."""
    import httpx

    def _raise(*_args, **_kwargs):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(jabref_module.httpx, "get", _raise)
    # Also reset the cache so the new behaviour is observed
    jabref_module._jabref_csv_list = None

    result = list_jabref_csvs()
    assert isinstance(result, list)
    assert len(result) == len(JABREF_FALLBACK_NAMES)
    for entry in result:
        assert set(entry.keys()) == {"name", "download_url", "size"}
        assert entry["name"].endswith(".csv")
        assert "abbrv.jabref.org" in entry["download_url"]
        assert entry["size"] == 0  # fallback records carry no size


def test_list_jabref_csvs_falls_back_on_http_error(monkeypatch):
    """Non-200 responses from the API also trigger the fallback."""
    import httpx

    class _Resp:
        status_code = 503

    def _fake_get(*_args, **_kwargs):
        return _Resp()

    monkeypatch.setattr(jabref_module.httpx, "get", _fake_get)
    jabref_module._jabref_csv_list = None

    result = list_jabref_csvs()
    assert len(result) == len(JABREF_FALLBACK_NAMES)


def test_list_jabref_csvs_parses_api_response(monkeypatch):
    """A successful API response is parsed into the expected shape."""
    fake_payload = [
        {"name": "README.md", "type": "file", "size": 100,
         "download_url": "https://example.com/README.md"},
        {"name": "journal_abbreviations_acs.csv", "type": "file", "size": 99154,
         "download_url": "https://example.com/journal_abbreviations_acs.csv"},
        {"name": "journal_abbreviations_ieee.csv", "type": "file", "size": 21348,
         "download_url": "https://example.com/journal_abbreviations_ieee.csv"},
        {"name": "subdir", "type": "dir", "size": 0,
         "download_url": None},
    ]

    class _Resp:
        status_code = 200
        def json(self):
            return fake_payload

    def _fake_get(*_args, **_kwargs):
        return _Resp()

    monkeypatch.setattr(jabref_module.httpx, "get", _fake_get)
    jabref_module._jabref_csv_list = None

    result = list_jabref_csvs()
    # README.md and the subdirectory are filtered out — only *.csv files
    names = [e["name"] for e in result]
    assert names == ["journal_abbreviations_acs.csv", "journal_abbreviations_ieee.csv"]
    for e in result:
        assert e["size"] > 0  # real API responses carry sizes
        assert e["download_url"].startswith("https://example.com/")


def test_list_jabref_csvs_is_cached(monkeypatch):
    """After the first call, the result is cached and the network is not
    touched again."""
    call_count = {"n": 0}

    class _Resp:
        status_code = 200
        def json(self):
            return [
                {"name": "journal_abbreviations_general.csv", "type": "file",
                 "size": 1000,
                 "download_url": "https://example.com/general.csv"},
            ]

    def _fake_get(*_args, **_kwargs):
        call_count["n"] += 1
        return _Resp()

    monkeypatch.setattr(jabref_module.httpx, "get", _fake_get)
    jabref_module._jabref_csv_list = None

    first = list_jabref_csvs()
    second = list_jabref_csvs()
    third = list_jabref_csvs()
    assert first == second == third
    assert jabref_module._jabref_csv_list is first
    # The API was only hit on the first call; the cache served the rest.
    assert call_count["n"] == 1


# ── _parse_jabref_csv ────────────────────────────────────────────────────────

def test_parse_jabref_csv_basic():
    combined: dict[str, str] = {}
    text = "Full Journal Name;Abbrev.\nAnother Journal;An. J."
    added = jabref_module._parse_jabref_csv(text, combined)
    assert added == 2
    assert combined["full journal name"] == "Abbrev."
    assert combined["another journal"] == "An. J."


def test_parse_jabref_csv_skips_comments_and_blanks():
    combined: dict[str, str] = {}
    text = "# header comment\n\nFull Name;Abbrev.\n  \n# another"
    added = jabref_module._parse_jabref_csv(text, combined)
    assert added == 1


def test_parse_jabref_csv_first_seen_wins():
    """The original loader takes the first occurrence of each full name
    so earlier-list entries (e.g. ACS) take precedence over later ones
    (e.g. General)."""
    combined: dict[str, str] = {"existing journal": "Existing."}
    text = "Existing Journal;Overwrite.\nNew Journal;New."
    added = jabref_module._parse_jabref_csv(text, combined)
    # "existing journal" already had a value — no overwrite
    assert combined["existing journal"] == "Existing."
    assert added == 1
    assert combined["new journal"] == "New."


def test_parse_jabref_csv_handles_tab_separator():
    """Some JabRef files use tab separation; the parser should accept
    either ``;`` or tab."""
    combined: dict[str, str] = {}
    text = "Full Name\tAbbrev."
    added = jabref_module._parse_jabref_csv(text, combined)
    assert added == 1
    assert combined["full name"] == "Abbrev."


def test_parse_jabref_csv_skips_lines_with_no_separator():
    combined: dict[str, str] = {}
    text = "no_separator_here\nHas;Separator"
    added = jabref_module._parse_jabref_csv(text, combined)
    assert added == 1
    assert "no_separator_here" not in combined


# ── live-network test (skipped by default) ─────────────────────────────────

@pytest.mark.network
def test_list_jabref_csvs_live(monkeypatch):
    """Hits the real GitHub API.  Skipped unless the test session was
    started with a way to enable network access (e.g. ``pytest -m network``).

    On 2026-06-10 the live list contained 19 CSVs; this assertion guards
    against the loader silently going empty if the API changes shape.
    """
    monkeypatch.delenv("AIAGENT_DISABLE_JABREF", raising=False)
    jabref_module._jabref_csv_list = None  # force a fresh fetch
    result = list_jabref_csvs()
    assert len(result) >= 10, (
        f"expected at least 10 JabRef CSVs live, got {len(result)}; "
        "the GitHub Contents API may have changed shape"
    )
    for entry in result:
        assert entry["name"].endswith(".csv")
        assert "abbrv.jabref.org" in entry["download_url"]
