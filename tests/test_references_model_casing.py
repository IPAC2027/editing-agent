"""The local model decides title words the formatter left as written.

Word and \\bibitem references go through the formatter, whose sentence case
leaves a capitalised word it cannot classify exactly as written.  When a local
model is configured, the adapter asks it about those words only — labels, not
text, under the unanimity rule in src/llm/classify.py — and re-runs the damage
check.  A model-assisted change is always a suggestion.
"""
from __future__ import annotations

import pytest

from src import references
from src.edits import Tier
from src.llm import classify

RAW = "A. Alpha, “Testing of Strongback Prototypes”, Cryogenics, vol. 5, pp. 1-4, 2020."


@pytest.fixture(autouse=True)
def _fresh_formatter():
    references._agents.clear()


def _model(monkeypatch, labels: dict[str, classify.WordLabel], *, on: bool = True):
    asked: list[list[str]] = []

    def fake_classify(title, words):
        asked.append(list(words))
        return {w: labels.get(w, classify.WordLabel.UNSURE) for w in words}

    monkeypatch.setattr(classify, "available", lambda: on)
    monkeypatch.setattr(classify, "classify_title_words", fake_classify)
    return asked


def test_a_name_the_model_keeps_stays_capitalised(monkeypatch):
    _model(monkeypatch, {"Strongback": classify.WordLabel.KEEP})
    result = references.screen_reference(RAW)
    assert "Strongback prototypes" in result.after
    assert "local model" not in result.message


def test_an_undecided_model_leaves_the_formatters_title(monkeypatch):
    _model(monkeypatch, {})                                # every word UNSURE
    assert "Strongback" in RAW
    result = references.screen_reference(RAW)
    assert "local model" not in result.message


def test_no_model_no_question(monkeypatch):
    asked = _model(monkeypatch, {"Strongback": classify.WordLabel.LOWER}, on=False)
    references.screen_reference(RAW)
    assert asked == []


def test_llm_false_overrides_a_configured_model(monkeypatch):
    asked = _model(monkeypatch, {"Strongback": classify.WordLabel.LOWER})
    references.screen_reference(RAW, llm=False)
    assert asked == []


def test_the_dead_model_helpers_are_gone():
    assert not hasattr(classify, "classify_reference_type")
    assert not hasattr(classify, "segment_reference")
