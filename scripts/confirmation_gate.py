"""Fail CI when the agent's confirmation rate against real editors falls.

Usage: python scripts/confirmation_gate.py score.json baseline.json

score.json comes from `main.py corpus-score <corpus> --json score.json`.
The first run, with no baseline yet, records one and passes; commit it.  After
that a zone fails when its confirmation rate drops by more than TOLERANCE, or
when its contradicted count rises — contradiction (the editors changed the
same text to something else) is the one column that is evidence of a defect.
Zones with fewer than MIN_PROPOSALS proposals are reported but never fail.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOLERANCE = 0.03
MIN_PROPOSALS = 30


def main(score_path: str, baseline_path: str) -> int:
    score = json.loads(Path(score_path).read_text(encoding="utf-8"))
    baseline_file = Path(baseline_path)
    if not baseline_file.exists():
        baseline_file.write_text(json.dumps(score, indent=1), encoding="utf-8")
        print(f"No baseline yet: recorded {baseline_file}. Commit it.")
        return 0
    baseline = json.loads(baseline_file.read_text(encoding="utf-8"))

    failures = []
    for zone, now in score["zones"].items():
        was = baseline["zones"].get(zone)
        if not was:
            continue
        line = (f"{zone:20} rate {was['rate']:.0%} -> {now['rate']:.0%}   "
                f"contradicted {was['contradicted']} -> {now['contradicted']}")
        print(line)
        if now["proposals"] < MIN_PROPOSALS:
            continue
        if now["rate"] < was["rate"] - TOLERANCE or now["contradicted"] > was["contradicted"]:
            failures.append(line)
    if failures:
        print("\nConfirmation fell in:\n  " + "\n  ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
