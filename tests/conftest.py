"""Shared pytest fixtures and offline guards."""

import os

# The whole suite runs offline: the reference formatter makes no lookups
# (src.references reads AIAGENT_OFFLINE) and its abbreviation lists are not
# downloaded.  Tests that need the network are marked and skipped.
os.environ.setdefault("AIAGENT_OFFLINE", "1")
os.environ.setdefault("AIAGENT_DISABLE_JABREF", "1")
os.environ.setdefault("AIAGENT_DISABLE_LTWA", "1")
os.environ.setdefault("JACOW_DISABLE_JABREF", "1")

import pytest  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip external-network tests unless they are explicitly selected."""
    if config.getoption("markexpr") == "network":
        return

    skip_network = pytest.mark.skip(reason="run with pytest -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
