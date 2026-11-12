"""src.references: the formatter's answer in the agent's vocabulary.

One test per row of the mapping table in the module docstring, using a stub
formatter so each row is exercised exactly; then one real offline run.
"""
from __future__ import annotations

import pytest

from src import references
from src.edits import Tier


class _Stub:
    def __init__(self, result: dict):
        self.result = result

    def process_record(self, raw: str) -> dict:
        return {"rec": {}, "flags": [], "derived_fields": [], "provenance": {},
                "integrity": {"verdict": "verified"}, "source": "heuristic", **self.result}


@pytest.fixture
def stub(monkeypatch):
    def install(**result):
        monkeypatch.setattr(references, "_agent", lambda offline, llm: _Stub(result))
    return install


RAW = ("J. Halvorsen, K. Lindqvist and P. Ortiz, “Lattice design”, in Proc. IPAC’23, "
       "Venice, Italy, May 2023, pp. 112-115. DOI: 10.18429/JACoW-IPAC2023-MOPA001")
# What the JACoW rules make of RAW on their own: Annex B's comma before "and"
# for three authors, and the DOI's form. Nothing else.
RULED = RAW.replace("Lindqvist and", "Lindqvist, and").replace("DOI: ", "doi:")


def test_a_verified_reformat_is_a_suggestion(stub):
    raw = "J. Halvorsen, “Lattice Design”, IPAC 2023, Venice, Italy, May 2023, pp. 112-115."
    stub(formatted=("J. Halvorsen, “Lattice design”, in Proc. IPAC’23, Venice, Italy, "
                    "May 2023, pp. 112–115."))
    result = references.screen_reference(raw)
    assert result.tier is Tier.SUGGEST and not result.added_from


def test_a_rewrite_that_damages_the_reference_is_discarded(stub):
    stub(formatted="J. Halvorsen et al., “Lattice design”, 2023.")
    result = references.screen_reference(RAW)
    assert result.after == RULED          # the damaging rewrite is not used; the rules' fixes are
    # The rejection is not reported: the rules corrected the reference instead.
    assert not any(f.check_id == "FMT-REF-03" for f in result.findings)


def test_settings_come_from_one_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("CROSSREF_EMAIL", "editor@example.org")
    monkeypatch.setenv("AIAGENT_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("HOUSE_STYLE", "iso4")
    cfg = references.formatter_config(offline=True, llm=True)
    assert cfg.mailto == "editor@example.org"
    assert cfg.cache_path == tmp_path / "lookups.sqlite"
    assert cfg.llm_endpoint == "http://localhost:11434/v1/chat/completions"
    assert cfg.llm_model == "qwen2.5:14b" and cfg.llm_provider == "openai-compatible"
    assert cfg.page_range_dash == "\u2013" and cfg.applied_physics == "Appl."
    assert not cfg.use_crossref


def test_latex_round_trip():
    body = r"A. Alpha, ``Title'', in \emph{Proc. IPAC'23}, pp. 1--3. \doi{10.18429/JACoW-IPAC2023-X_1}"
    plain = references.latex_to_plain(body)
    assert plain == "A. Alpha, “Title”, in Proc. IPAC'23, pp. 1–3. doi:10.18429/JACoW-IPAC2023-X_1"
    back = references.plain_to_latex(plain)
    assert r"\doi{10.18429/JACoW-IPAC2023-X_1}" in back and "pp. 1--3" in back


def test_a_real_offline_run(monkeypatch):
    monkeypatch.setenv("HOUSE_STYLE", "jacow")
    references._agents.clear()
    result = references.screen_reference(
        "D. Okonkwo and S. Quist, “Gas-cooled thermal shields”, submitted to Cryogenics.")
    assert result.after == ("D. Okonkwo and S. Quist, “Gas-cooled thermal shields”, "
                            "submitted for publication.")
    assert result.tier is Tier.SUGGEST


def test_offline_runs_do_not_repeat_not_checked_per_reference(stub):
    stub(formatted=RAW, integrity={"verdict": "unverifiable"})
    assert references.screen_reference(RAW, offline=True).findings == []


def test_a_journal_abbreviation_is_not_damage(monkeypatch):
    references._agents.clear()
    result = references.screen_reference(
        "R. Smith, “A compact Thomson scattering source”, Review of Scientific Instruments, "
        "vol. 90, p. 033301, 2019.")
    assert result.after and "Rev. Sci. Instrum." in result.after
    assert "Thomson" in result.after


def test_latex_output_uses_latex_quotes():
    assert references.plain_to_latex("A. Alpha, “Title”, 2020.") == "A. Alpha, ``Title'', 2020."


def test_units_inside_the_bibliography_are_left_to_the_reference_engine():
    from src.autofix.latex_edits import unit_edits

    source = ("\\documentclass{jacow}\\begin{document}At 16 MV/m.\n"
              "\\begin{thebibliography}{9}\\bibitem{a} A. Alpha, ``A 1.3 GHz cavity'', 2020.\n"
              "\\end{thebibliography}\\end{document}")
    edits = unit_edits(source)
    befores = [e.before for e in edits]
    assert any("16 MV" in b for b in befores)
    assert not any("1.3 GHz" in b for b in befores)


# --- Authoritative values reach the editor -------------------------------------
# A real formatter run with Crossref simulated: the search returns a record,
# the formatter merges it, and the adapter must let the added and corrected
# values through as a suggestion that names them.

def _formatter_with_crossref(monkeypatch, tmp_path, record, *, corrections=True):
    import jacow_formatter.agent as fa
    from jacow_formatter import AgentConfig, JacowAgent

    monkeypatch.setattr(fa, "_load_jabref", lambda *a, **k: None)
    monkeypatch.setattr(fa, "search_and_fill",
                        lambda rec, cache=None, cfg=None: ("verified", dict(record), "title search"))
    agent = JacowAgent(AgentConfig(
        use_crossref=True, use_datacite=False, use_inspirehep=False, use_ltwa=False,
        use_jacow_remote=False, use_refdb=False, use_llm=False,
        prefer_authoritative=corrections, cache_path=tmp_path / "c.sqlite"))
    monkeypatch.setattr(references, "_agent", lambda offline, llm: agent)


CROSSREF = {"doi": "10.1103/PhysRevAccelBeams.26.041002", "volume": "26",
            "title": "Operational experience with a compact energy-recovery linac",
            "journal": "Physical Review Accelerators and Beams", "pages": "041002",
            "year": "2023", "month": "Apr", "authors_raw": "L. Fontaine"}


def test_an_invented_value_with_no_source_is_still_rejected(stub):
    stub(formatted="D. Okonkwo, “Thermal design”, Cryogenics, vol. 7, 2026.")
    result = references.screen_reference("D. Okonkwo, “Thermal design”, Cryogenics.")
    assert result.after is None


# --- DOI form even when the rest is left as written (test-run references) ----------

def test_doi_form_only():
    assert references.doi_form_only(
        "M.Kappa (ed.), “Accelerator Overview”, HEP Conference, Springfield, 2025. "
        "https://doi.org/10.22323/1.999.0001") == (
        "M.Kappa (ed.), “Accelerator Overview”, HEP Conference, Springfield, 2025. "
        "doi:10.22323/1.999.0001")
    assert references.doi_form_only("…, 2022. DOI: 10.23731/CYRM-2099-001.") == \
        "…, 2022. doi:10.23731/CYRM-2099-001."
    assert references.doi_form_only("https://indico.cern.ch/event/1/") == "https://indico.cern.ch/event/1/"


def test_qwen3_is_the_default_model_with_thinking_off(monkeypatch):
    from src.llm.client import no_think
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert references.formatter_config(offline=True).llm_model == "qwen3:14b"
    assert no_think("qwen3:14b", "Answer in JSON.").endswith("/no_think")
    assert no_think("llama3.1:8b", "Answer in JSON.") == "Answer in JSON."
    assert no_think("qwen3:14b", "x /no_think") == "x /no_think"


# --- The fine-tuned reference model (REFERENCE_MODEL) ---------------------------

def _served(monkeypatch, answer):
    from src.llm import client
    asked = []
    def fake_chat(system, user, **kw):
        asked.append((system, user, kw.get("model")))
        return answer
    monkeypatch.setattr(client, "chat", fake_chat)
    return asked


def test_the_reference_model_is_off_unless_named(monkeypatch, stub):
    monkeypatch.delenv("REFERENCE_MODEL", raising=False)
    asked = _served(monkeypatch, "anything")
    stub(formatted="damaged")
    references.screen_reference("A. Alpha, “Title”, 2020.")
    assert asked == []


def test_a_model_answer_that_invents_is_rejected(monkeypatch, stub):
    monkeypatch.setenv("REFERENCE_MODEL", "jacow-refs")
    raw = "D. Okonkwo, “Thermal design”, Cryogenics."
    _served(monkeypatch, "D. Okonkwo, “Thermal design”, Cryogenics, vol. 12, 2021.")
    stub(formatted="garbage")
    assert references.screen_reference(raw).after is None

