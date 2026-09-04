"""Shared pytest fixtures and offline guards for the src/refs/ tests."""

import os

# Disable network-dependent loaders for the entire test run.  L1 (the
# hand-curated JACoW journal table) is always available, so the
# normalize_journal tests still cover the most important code path.
os.environ.setdefault("AIAGENT_DISABLE_JABREF", "1")
os.environ.setdefault("AIAGENT_DISABLE_LTWA", "1")

import pytest

from src.refs.conference_db import JacoWConnector


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip external-network tests unless they are explicitly selected."""
    if config.getoption("markexpr") == "network":
        return

    skip_network = pytest.mark.skip(reason="run with pytest -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


@pytest.fixture
def connector() -> JacoWConnector:
    """Offline JacoWConnector (does not fetch jacow-events.bib)."""
    return JacoWConnector(allow_network=False)
