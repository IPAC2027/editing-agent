"""The CI gate on the agent's confirmation rate against real editors."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "scripts" / "confirmation_gate.py"


def _score(path: Path, rate: float, contradicted: int = 2) -> Path:
    path.write_text(json.dumps({"papers": 40, "zones": {"references": {
        "proposals": 200, "confirmed": int(200 * rate), "contradicted": contradicted,
        "rate": rate}}, "checks": {}}), encoding="utf-8")
    return path


def _run(score: Path, baseline: Path) -> int:
    return subprocess.run([sys.executable, str(GATE), str(score), str(baseline)],
                          capture_output=True, text=True, encoding="utf-8").returncode


def test_first_run_records_a_baseline(tmp_path):
    baseline = tmp_path / "baseline.json"
    assert _run(_score(tmp_path / "s.json", 0.52), baseline) == 0 and baseline.exists()


def test_a_drop_or_a_new_contradiction_fails(tmp_path):
    baseline = _score(tmp_path / "baseline.json", 0.52)
    assert _run(_score(tmp_path / "same.json", 0.51), baseline) == 0
    assert _run(_score(tmp_path / "drop.json", 0.45), baseline) == 1
    assert _run(_score(tmp_path / "contra.json", 0.52, contradicted=5), baseline) == 1
