"""The model backend: what the desk promises and what it must not claim.

The failure these guard against is not a crash — it is a desk that an editor
asked to use a model, that quietly screened forty papers without one.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.desk import server as server_module
from src.llm import classify, client


# ---------------------------------------------------------------------------
# Reachability is checked, not assumed
# ---------------------------------------------------------------------------

def test_a_model_that_is_switched_off_is_not_described_as_reachable(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    ok, reason = client.reachable()
    assert ok is False
    assert "no model configured" in reason


def test_an_unreachable_server_says_so_without_naming_an_exception(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")

    ok, reason = client.reachable(timeout=1.0)

    assert ok is False
    assert "http://127.0.0.1:1/v1" in reason
    assert "Ollama" in reason  # tells the editor what to do about it


def test_a_server_without_the_requested_model_is_a_failure_not_a_silent_swap(monkeypatch):
    """Asking for a model the server does not have must not fall back to another."""
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_MODEL", "qwen3.8:27b-mlx")

    class _Model:
        def __init__(self, name: str) -> None:
            self.id = name

    class _Listing:
        data = [_Model("llama3.1:8b"), _Model("qwen2.5:14b")]

    class _Models:
        def list(self):
            return _Listing()

    class _Client:
        models = _Models()

        def with_options(self, **_kwargs):
            return self

    monkeypatch.setattr(client, "_get_client", lambda: _Client())

    ok, reason = client.reachable()

    assert ok is False
    assert "qwen3.8:27b-mlx" in reason
    assert "llama3.1:8b" in reason  # and says what it could have instead


# ---------------------------------------------------------------------------
# Unanimity has to be able to fail
# ---------------------------------------------------------------------------

def test_repeated_samples_are_not_drawn_greedily(monkeypatch):
    """Three samples at temperature 0 are one sample counted three times."""
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.setattr(classify, "SAMPLES", 3)
    assert classify._sample_temperature() > 0


def test_a_single_sample_is_drawn_greedily(monkeypatch):
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.setattr(classify, "SAMPLES", 1)
    assert classify._sample_temperature() == 0.0


def test_the_temperature_can_be_pinned(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setattr(classify, "SAMPLES", 3)
    assert classify._sample_temperature() == pytest.approx(0.7)


def test_a_nonsense_temperature_falls_back_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "warm")
    monkeypatch.setattr(classify, "SAMPLES", 3)
    assert classify._sample_temperature() > 0


def test_the_sampled_temperature_reaches_the_server(monkeypatch):
    seen: list[float | None] = []

    def fake_chat(_system, _user, *, json_mode=False, temperature=None, **_kw):
        seen.append(temperature)
        return '{"ok": true}'

    monkeypatch.setattr(client, "chat", fake_chat)
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.setattr(classify, "SAMPLES", 3)

    classify._ask_json("anything")

    assert seen == [classify._sample_temperature()]
    assert seen[0] > 0


# ---------------------------------------------------------------------------
# The desk honours the flag it was started with
# ---------------------------------------------------------------------------

def test_the_desk_passes_its_model_preference_to_every_paper(monkeypatch, tmp_path: Path):
    seen: list[bool] = []

    def fake_prescreen(folder, *, compile=True, git=True, llm=False):  # noqa: A002
        seen.append(llm)

    import src.workflow.prescreen as prescreen_module

    monkeypatch.setattr(prescreen_module, "prescreen", fake_prescreen)

    for requested in (True, False):
        runner = server_module.JobRunner(llm=requested)
        job_id = runner.start("two", [tmp_path / "a", tmp_path / "b"],
                              compile_pdf=False)
        deadline = time.monotonic() + 10
        while not runner.status(job_id).get("finished"):
            if time.monotonic() > deadline:
                raise AssertionError("the job never finished")
            time.sleep(0.01)

    assert seen == [True, True, False, False]


def test_the_page_is_told_which_model_is_in_use(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")

    on = server_module._llm_state(True)
    assert on == {"enabled": True, "model": "llama3.1:8b",
                  "base_url": "http://localhost:11434/v1"}

    off = server_module._llm_state(False)
    assert off["enabled"] is False
    assert off["model"] == ""  # nothing to advertise when nothing is running


def test_the_desk_command_accepts_the_model_options():
    """The regression that prompted this: `desk --llm` was "No such option"."""
    import main

    params = {
        name
        for command in main.app.registered_commands
        if command.callback.__name__ == "desk"
        for name in command.callback.__code__.co_varnames
    }
    assert {"llm", "model", "base_url"} <= params

# ---------------------------------------------------------------------------
# One answer to "is a model in play?", not two
# ---------------------------------------------------------------------------

def test_an_unusable_model_is_switched_off_everywhere_not_just_on_the_flag(monkeypatch):
    """The half-on state is the one nobody can describe afterwards.

    One sanctioned use of a model — resolving sentence-case abstentions — asks
    the environment rather than the caller, so a failed start-up check has to
    put the environment back too.
    """
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")

    in_use, line = server_module._settle_model(True)

    assert in_use is False
    assert "NOT USED" in line
    assert client.is_enabled() is False


def test_a_reachable_model_is_announced_with_its_name(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setattr(client, "reachable",
                        lambda **_kw: (True, "llama3.1:8b at http://x/v1"))

    in_use, line = server_module._settle_model(True)

    assert in_use is True
    assert "llama3.1:8b" in line
    assert "NOT USED" not in line


def test_nothing_is_announced_when_no_model_was_asked_for(monkeypatch):
    monkeypatch.setattr(client, "reachable",
                        lambda **_kw: pytest.fail("must not be probed"))
    assert server_module._settle_model(False) == (False, "")


def test_the_environment_decides_when_neither_flag_is_given(monkeypatch):
    import main

    monkeypatch.setenv("LLM_ENABLED", "true")
    assert main._configure_llm(None, None, None) is True

    monkeypatch.setenv("LLM_ENABLED", "false")
    assert main._configure_llm(None, None, None) is False


def test_an_explicit_flag_overrides_the_environment(monkeypatch):
    import main

    monkeypatch.setenv("LLM_ENABLED", "true")
    assert main._configure_llm(False, None, None) is False
    assert client.is_enabled() is False   # and the environment agrees

    monkeypatch.setenv("LLM_ENABLED", "false")
    assert main._configure_llm(True, None, None) is True
    assert client.is_enabled() is True
