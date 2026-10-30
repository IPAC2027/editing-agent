"""The formatter's own test bibliography, run through the agent's adapter.

Shared between the two repositories' CI (see .github/workflows): a formatter
change that alters what the agent would do to a reference — the tier, or
whether a rewrite survives the damage check — shows up here as a diff against
``tests/data/shared_bibliography_decisions.json`` before it reaches editors.

The bibliography lives in the formatter repository (``data/test.txt``).  Set
``JACOW_FORMATTER_DIR`` to a checkout of it; CI checks out the pinned tag.
To accept a deliberate change, rerun with ``UPDATE_SNAPSHOT=1``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src import references
from src.references import check_rewrite, screen_reference, split_refs

SNAPSHOT = Path(__file__).with_name("data") / "shared_bibliography_decisions.json"


def _bibliography() -> Path | None:
    for candidate in (os.getenv("JACOW_FORMATTER_DIR", ""),
                      str(Path(__file__).resolve().parents[2] / "jacow-reference-formatter")):
        if candidate and (Path(candidate) / "data" / "test.txt").is_file():
            return Path(candidate) / "data" / "test.txt"
    return None


@pytest.fixture(scope="module")
def decisions(monkeypatch_module=None):
    path = _bibliography()
    if path is None:
        pytest.skip("set JACOW_FORMATTER_DIR to a checkout of jacow-reference-formatter")
    os.environ["HOUSE_STYLE"] = "jacow"
    references._agents.clear()
    rows = []
    for number, raw in enumerate(split_refs(path.read_text(encoding="utf-8")), start=1):
        result = screen_reference(raw, label=f"[{number}]", offline=True)
        rows.append({"n": number, "raw": raw, "after": result.after,
                     "tier": result.tier.value if result.tier else None,
                     "declared": result.declared})
    return rows


def test_every_rewrite_the_agent_would_offer_passes_the_damage_check(decisions):
    for row in decisions:
        if row["after"]:
            # Re-check with exactly what the adapter declared (journal
            # abbreviations, values from lookups) — nothing more.
            assert check_rewrite(row["raw"], row["after"], **row["declared"]).ok, row


def test_the_agents_decisions_on_the_shared_bibliography_are_unchanged(decisions):
    current = [{"n": r["n"], "tier": r["tier"], "after": r["after"]} for r in decisions]
    if os.getenv("UPDATE_SNAPSHOT") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    changed = [(e["n"], e["tier"], c["tier"]) for e, c in zip(expected, current) if e != c]
    assert len(expected) == len(current) and not changed, (
        f"{len(changed)} reference decision(s) changed (n, was, now): {changed[:10]}. "
        "If the formatter change is intended, rerun with UPDATE_SNAPSHOT=1 and commit.")
