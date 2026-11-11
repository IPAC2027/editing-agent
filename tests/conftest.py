"""Shared pytest fixtures and offline guards."""

import os

# The whole suite runs offline: the reference formatter makes no lookups
# (src.references reads AIAGENT_OFFLINE) and its abbreviation lists are not
# downloaded.  Tests that need the network are marked and skipped.
os.environ.setdefault("AIAGENT_OFFLINE", "1")
os.environ.setdefault("AIAGENT_DISABLE_JABREF", "1")
os.environ.setdefault("AIAGENT_DISABLE_LTWA", "1")
os.environ.setdefault("JACOW_DISABLE_JABREF", "1")

import socket  # noqa: E402

import pytest  # noqa: E402

_LOOPBACK = {"127.0.0.1", "::1"}


@pytest.fixture(autouse=True)
def _own_settings(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Each test gets its own editor settings, never the developer's.

    The desk keeps the editor's name and its desk id in the home folder
    (``src.desk.me``); without this a test run would write there.
    """
    monkeypatch.setenv("AIAGENT_HOME", str(tmp_path_factory.mktemp("aiagent_home")))


@pytest.fixture(autouse=True)
def _no_doi_registries(monkeypatch: pytest.MonkeyPatch):
    """DOI lookups (src.refcheck.doi) answer "unreachable" unless a test fakes a registry."""
    from src.refcheck import doi

    monkeypatch.setattr(doi, "_get", lambda *a, **k: doi.UNREACHABLE)
    monkeypatch.setattr(doi, "CACHE", doi._Cache())
    monkeypatch.setattr(doi.CACHE, "_load", lambda: {})


@pytest.fixture(autouse=True)
def _offline(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """No test may open a connection off this machine — above all not to a live
    Indico, where the editor's token is their whole account.

    The desk's own server on 127.0.0.1 is allowed; anything else is refused
    and fails the test, even when the code under test catches the refusal
    (the author fetch in "Check Indico now" deliberately does).
    """
    if "network" in request.keywords:
        yield
        return
    attempts: list[str] = []
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _allowed(sock: socket.socket, address) -> bool:
        if sock.family == getattr(socket, "AF_UNIX", None):
            return True
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in _LOOPBACK:
            return True
        attempts.append(f"{host}:{address[1]}" if isinstance(address, tuple) else host)
        return False

    def connect(sock, address):
        if not _allowed(sock, address):
            raise ConnectionRefusedError(f"the test suite runs offline ({address!r})")
        return real_connect(sock, address)

    def connect_ex(sock, address):
        if not _allowed(sock, address):
            raise ConnectionRefusedError(f"the test suite runs offline ({address!r})")
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    yield
    assert not attempts, f"a test tried to reach the network: {attempts}"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip external-network tests unless they are explicitly selected."""
    if config.getoption("markexpr") == "network":
        return

    skip_network = pytest.mark.skip(reason="run with pytest -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
