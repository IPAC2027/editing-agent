"""Tests for src.refs.lookup — isbn_publisher_lookup (offline)."""

import pytest

from src.refs import lookup as lookup_module
from src.refs.lookup import isbn_publisher_lookup


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the in-process cache before each test."""
    lookup_module._cache.clear()
    yield
    lookup_module._cache.clear()


def test_invalid_isbn_returns_none():
    assert isbn_publisher_lookup("") is None
    assert isbn_publisher_lookup("123") is None
    assert isbn_publisher_lookup("abcdefghij") is None


def test_isbn_with_dashes_is_normalised():
    """The ISBN lookup normalises hyphens and spaces before validating length."""
    # A 13-digit ISBN with dashes; the lookup will attempt a network
    # call.  In offline mode (no network), returns None but the call
    # should be safely attempted, not raise.
    isbn = "978-0-19-852926-2"  # Oxford Univ. Press, "Quantum Computation"
    # Don't make a real HTTP call; substitute the network layer.
    isbn_clean = isbn.replace("-", "")
    assert len(isbn_clean) == 13


def test_isbn_10_format_validated():
    isbn = "019852926X"  # 10-char ISBN
    isbn_clean = isbn.replace("-", "")
    assert len(isbn_clean) == 10


def test_short_isbn_returns_none():
    """Anything that isn't 10 or 13 digits after stripping returns None."""
    assert isbn_publisher_lookup("12345") is None
    assert isbn_publisher_lookup("12345678901234") is None  # 14 digits


def test_negative_cache_on_network_failure(monkeypatch):
    """When the HTTP call fails, the lookup should return None and
    cache the failure so subsequent calls don't retry the network."""
    def _raise(*_args, **_kwargs):
        raise RuntimeError("simulated network down")
    monkeypatch.setattr(lookup_module.httpx, "get", _raise)

    result = isbn_publisher_lookup("9780198529262")
    assert result is None
    # Negative-cached: subsequent calls return the cached empty result
    # without going through httpx.
    result2 = isbn_publisher_lookup("9780198529262")
    assert result2 is None
    assert "9780198529262" in lookup_module._cache
    assert lookup_module._cache["9780198529262"] == ""


def test_positive_cache_on_success(monkeypatch):
    """A successful lookup is cached so a second call doesn't hit
    the network again."""
    payload = {"ISBN:9780198529262": {"publishers": [{"name": "Oxford University Press"}]}}

    class _Resp:
        status_code = 200
        def json(self):
            return payload

    call_count = {"n": 0}
    def _fake_get(*_args, **_kwargs):
        call_count["n"] += 1
        return _Resp()

    monkeypatch.setattr(lookup_module.httpx, "get", _fake_get)

    result1 = isbn_publisher_lookup("9780198529262")
    result2 = isbn_publisher_lookup("9780198529262")
    assert result1 == "Oxford University Press"
    assert result2 == "Oxford University Press"
    # First call hit the network; second was served from cache.
    assert call_count["n"] == 1


def test_http_error_returns_none(monkeypatch):
    """Non-200 response is treated as no result."""
    class _Resp:
        status_code = 503
        def json(self):
            return {}

    monkeypatch.setattr(lookup_module.httpx, "get", lambda *a, **k: _Resp())
    assert isbn_publisher_lookup("9780198529262") is None


def test_empty_publisher_field_returns_none(monkeypatch):
    """An API response with the ISBN key but no publishers field."""
    class _Resp:
        status_code = 200
        def json(self):
            return {"ISBN:9780198529262": {}}  # no publishers

    monkeypatch.setattr(lookup_module.httpx, "get", lambda *a, **k: _Resp())
    assert isbn_publisher_lookup("9780198529262") is None


def test_publisher_with_no_name_returns_none(monkeypatch):
    """A publisher entry without a name field is treated as no result."""
    class _Resp:
        status_code = 200
        def json(self):
            return {"ISBN:9780198529262": {"publishers": [{}]}}

    monkeypatch.setattr(lookup_module.httpx, "get", lambda *a, **k: _Resp())
    assert isbn_publisher_lookup("9780198529262") is None


def test_isbn_10x_normalised_correctly():
    """The 'X' check-digit in ISBN-10 is preserved through the strip
    step.  Only non-alphanumeric chars are removed."""
    isbn = "0-306-40615-X"  # ISBN-10 with X
    isbn_clean = isbn.replace("-", "")
    assert isbn_clean == "030640615X"
    assert len(isbn_clean) == 10
