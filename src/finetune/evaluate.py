"""Score a served reference model on held-out examples (eval.jsonl).

For each example the model's answer is compared with the editor's reference
and run through the same damage check the agent applies.  Reported:

* exact     — identical to the editor's version
* loose     — identical after normalising spaces, quotes and dashes
* safe      — passes check_rewrite against the author's reference
* offered   — safe and different from the author's reference (what the desk
              would show as a decision)

The rule-based formatter is scored on the same examples as the baseline, so
the numbers say directly whether the model is worth switching on.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.finetune.prompt import messages


def _loose(text: str) -> str:
    text = text.translate(str.maketrans({"\u201c": '"', "\u201d": '"', "\u2019": "'",
                                         "\u2013": "-", "\u00a0": " "}))
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


def _ask(model: str, raw: str, record: dict | None) -> str:
    from src.llm import client
    msgs = messages(raw, record)
    return client.chat(msgs[0]["content"], msgs[1]["content"], model=model,
                       temperature=0.0, timeout=120).strip()


def evaluate(eval_jsonl: Path, model: str | None = None, limit: int | None = None) -> dict:
    from src.references import _agent, check_rewrite
    formatter = _agent(True, False)
    tallies = {name: {"exact": 0, "loose": 0, "safe": 0, "offered": 0}
               for name in (["formatter"] + ([model] if model else []))}
    n = 0
    for line in eval_jsonl.read_text(encoding="utf-8").splitlines():
        if limit and n >= limit:
            break
        row = json.loads(line)
        user = row["messages"][1]["content"]
        raw = user.split("Reference:\n", 1)[1].split("\n\nVerified record", 1)[0]
        record = json.loads(user.split("JACoW):\n", 1)[1]) if "Verified record" in user else None
        gold = row["messages"][2]["content"]
        answers = {"formatter": (formatter.process_record(raw).get("formatted") or raw)}
        if model:
            answers[model] = _ask(model, raw, record)
        for name, answer in answers.items():
            answer = re.sub(r"\s+", " ", answer).strip()
            t = tallies[name]
            t["exact"] += answer == gold
            t["loose"] += _loose(answer) == _loose(gold)
            safe = check_rewrite(raw, answer, allowed_additions=[str(v) for v in (record or {}).values()]).ok
            t["safe"] += safe
            t["offered"] += safe and answer != raw
        n += 1
    return {"examples": n, **{k: {m: round(v / n, 3) if n else 0 for m, v in t.items()}
                              for k, t in tallies.items()}}
