"""src.refcheck: the JACoW reference rules, the difficulty description, the AI skill.

The cases are real references from the IPAC'27 test conference (and the
expected answers are what Annex B asks for), so each test is a mistake an
author really made.
"""
from __future__ import annotations

import pytest

from src.refcheck import EDITOR, MODEL, check_reference, describe, fix, kind_of, lint
from src.refcheck.difficulty import Difficulty
from src.refcheck.skill import clean, repair, verify

# ---------------------------------------------------------------------------
# 1. The rules find and fix
# ---------------------------------------------------------------------------

FIXED = [
    # A JACoW paper whose DOI names its conference, written with the long name.
    ("X. Huang, Z. Zhang, and M. Song, “Multi-objective multi-generation gaussian process "
     "optimizer,\" 12th Int. Particle Acc. Conf., Campinas, SP, Brazil, May 2021, pp. "
     "3383-3386, doi:10.18429/JACoW-IPAC2021-WEPAB304",
     "X. Huang, Z. Zhang, and M. Song, “Multi-objective multi-generation Gaussian process "
     "optimizer”, in Proc. 12th Int. Particle Acc. Conf. (IPAC’21), Campinas, SP, Brazil, May "
     "2021, pp. 3383-3386. "
     "doi:10.18429/JACoW-IPAC2021-WEPAB304"),
    # Surname first, physics-style journal, no full stops in the abbreviation.
    ("Boltz, T., et al., “Leveraging prior mean models for faster Bayesian optimization of "
     "particle accelerators”, Sci Rep 15, 12232 (2025). doi:10.1038/s41598-025-95297-z",
     "T. Boltz et al., “Leveraging prior mean models for faster Bayesian optimization of "
     "particle accelerators”, Sci. Rep., vol. 15, p. 12232, 2025. "
     "doi:10.1038/s41598-025-95297-z"),
    # An initial typed with a comma.
    ("Y, Momozaki, et al., “Proton beam-on-liquid lithium stripper film experiment”, J "
     "Radioanal Nucl Chem, vol. 305, pp. 843–849, 2015. doi:10.1007/s10967-015-4074-9",
     "Y. Momozaki et al., “Proton beam-on-liquid lithium stripper film experiment”, J. "
     "Radioanal. Nucl. Chem., vol. 305, pp. 843–849, 2015. doi:10.1007/s10967-015-4074-9"),
    ("F. C. Iselin, “Lie Transformations and Transport Equations for Combined-Function "
     "Dipoles,\" Part. Accel. 17, pp. 143-155 (1985).",
     "F. C. Iselin, “Lie transformations and transport equations for combined-function "
     "dipoles”, Part. Accel., vol. 17, pp. 143-155, 1985."),
    ("L. Deniau, \"MAD-NG, a standalone multiplatform tool for linear and non-linear optics "
     "design and optimisation,\" arXiv preprint arXiv:2412.16006, 2024. "
     "doi:10.48550/arXiv.2412.16006",
     "L. Deniau, “MAD-NG, a standalone multiplatform tool for linear and non-linear optics "
     "design and optimisation”, arXiv:2412.16006, 2024. doi:10.48550/arXiv.2412.16006"),
    # An arXiv paper gets its DOI, derived from the identifier.
    ("D.P. Kingma and J. Ba, “Adam: A Method for Stochastic Optimization”, arXiv:1412.6980 "
     "[cs.LG], 2014.",
     "D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization”, arXiv:1412.6980 "
     "[cs.LG], 2014. doi:10.48550/arXiv.1412.6980"),
    # An old JACoW paper: its PDF's address gives way to its paper ID.
    ("S. Kondrashev, et al., “Upgrade of the FRIB Prototype Injector for Liquid Lithium Film "
     "Testing”, in Proc. PAC09, Vancouver, BC, Canada, May, 2010, pp. 1656. "
     "https://accelconf.web.cern.ch/PAC2009/papers/tu6rfp048.pdf",
     "S. Kondrashev et al., “Upgrade of the FRIB prototype injector for liquid lithium film "
     "testing”, in Proc. PAC’09, Vancouver, BC, Canada, May 2010, pp. 1656, paper TU6RFP048."),
    ("Yoshida, H., “Construction of higher order symplectic integrators.”, Physics Letters A "
     "150, 262–268, Sept. 1990. doi:https://doi.org/10.1016/0375-9601(90)90092-3",
     "H. Yoshida, “Construction of higher order symplectic integrators”, Phys. Lett. A, vol. "
     "150, pp. 262–268, Sep. 1990. doi:10.1016/0375-9601(90)90092-3"),
    # A bare DOI; the date before the article number.
    ("J. Duris et al., “Bayesian optimization of a free-electron laser,\" Phys. Rev. Lett., "
     "Dec 2020, p. 124801, 10.1103/PhysRevLett.124.124801",
     "J. Duris et al., “Bayesian optimization of a free-electron laser”, Phys. Rev. Lett., "
     "p. 124801, Dec. 2020. doi:10.1103/PhysRevLett.124.124801"),
    ("J. Wan, J. Qiang and Y. Hao, \"Symplectic machine learning model for fast simulation of "
     "space-charge effects\", Phys. Rev. Accel. Beams, Accepted 16 July, 2025. "
     "doi:10.1103/bhpv-bcqk",
     "J. Wan, J. Qiang, and Y. Hao, “Symplectic machine learning model for fast simulation of "
     "space-charge effects”, Phys. Rev. Accel. Beams, to be published. doi:10.1103/bhpv-bcqk"),
    ("J. Wei, et al., “Advances of the FRIB project”, International Journal of Modern Physics "
     "E, vol. 28, no. 03, pp. 1930003, 2019. doi:10.1142/S0218301319300030",
     "J. Wei et al., “Advances of the FRIB project”, Int. J. Mod. Phys. E, vol. 28, no. 03, "
     "p. 1930003, 2019. doi:10.1142/S0218301319300030"),
    # Seven authors; a title in capitals.
    ("K. Hwang, A. Plastun, K. Fukushima, P. Ostroumov, T. Maruta, T. Zhang, and Q. Zhao, "
     "“APPLICATION OF ML TOOLS FOR EXTRACTION OF BPM-Q AND TRANSVERSE BEAM MATCHING”, in "
     "Proc. 16th Int. Conf. on Heavy Ion Accelerator Technology (HIAT’25), East Lansing, MI, "
     "USA, Jun. 2025, doi:10.18429/JACoW-HIAT2025-TUP11",
     "K. Hwang et al., “Application of ML tools for extraction of BPM-Q and transverse beam "
     "matching”, in Proc. 16th Int. Conf. on Heavy Ion Accelerator Technology (HIAT’25), East "
     "Lansing, MI, USA, Jun. 2025. doi:10.18429/JACoW-HIAT2025-TUP11"),
    ("Javier Gonzalez, Zhenwen Dai, Philipp Hennig and Neil Lawrence, “Batch Bayesian "
     "optimization via local penalization”, in Proc. 19th Int. Conf. on Artificial "
     "Intelligence and Statistics, vol. 51, pp. 648–657, May 2016.",
     "J. Gonzalez, Z. Dai, P. Hennig, and N. Lawrence, “Batch Bayesian optimization via local "
     "penalization”, in Proc. 19th Int. Conf. on Artificial Intelligence and Statistics, vol. "
     "51, pp. 648–657, May 2016."),
]


@pytest.mark.parametrize("raw,expected", FIXED, ids=[f"case{i}" for i in range(len(FIXED))])
def test_the_rules_fix_what_annex_b_asks(raw, expected):
    result = fix(raw)
    assert result.text == expected
    assert not result.refused


def test_every_fix_is_declared_to_the_damage_check():
    from src.references import check_rewrite

    for raw, _ in FIXED:
        result = fix(raw)
        assert check_rewrite(raw, result.text, **result.declared).ok, raw


# ---------------------------------------------------------------------------
# 2. ... and leave alone what they cannot read
# ---------------------------------------------------------------------------

LEFT_ALONE = [
    # A book chapter: the quoted words are a section's title, the rest is not
    # a list of authors (once collapsed to "E. Hairer et al.").
    "E. Hairer, C. Lubich, and G. Wanner, Geometric Numerical Integration: Structure-Preserving "
    "Algorithms for Ordinary Differential Equations, 2nd ed., Springer-Verlag, Berlin, 2006, "
    "Section VI.5, “Generating Functions”, Theorem 5.7.",
    # A year among the authors (once became "Qiang, J., and 2018.").
    "Qiang, J., 2018. “A two-and-a-half dimensional symplectic space-charge solver”, LBNL "
    "report, LBNL-2001674, (submitted to Phys. Rev. Accel. Beams), 2025.",
    # Correct already.
    "K. Hwang et al., “Beam tuning at the FRIB front end using machine learning”, in Proc. "
    "IPAC’22, Bangkok, Thailand, Jun. 2022, pp. 983–986. doi:10.18429/JACoW-IPAC2022-TUPOST053",
    "USPAS, https://uspas.fnal.gov/index.shtml",
]


@pytest.mark.parametrize("raw", LEFT_ALONE, ids=["book", "year-in-authors", "correct", "web"])
def test_the_rules_leave_alone_what_they_cannot_read(raw):
    assert fix(raw).text == raw


def test_a_year_is_never_a_volume_and_a_report_is_not_a_journal():
    raw = ("J. A. Nelder and R. Mead, “A simplex function for function minimization”, The "
           "Computer Journal, 1965, pp. 308-313. doi:10.1093/comjnl/7.4.308")
    assert "vol. 1965" not in fix(raw).text
    assert fix(raw).text.endswith("The Computer Journal, pp. 308-313, 1965. "
                                  "doi:10.1093/comjnl/7.4.308")
    report = ("K. L. Brown, “A first-order matrix theory”, SLAC Report No. 75, 1982.")
    assert fix(report).text == report


def test_a_title_with_a_quoted_title_inside_is_one_title():
    raw = ("R. D. Skeel and J. L. Cieśliński, “On the famous unpublished preprint “Methods of "
           "integration” by René De Vogelaere.”, Mar. 2020. doi:10.48550/arXiv.2003.12268")
    assert fix(raw).text == ("R. D. Skeel and J. L. Cieśliński, “On the famous unpublished "
                             "preprint “Methods of integration” by René De Vogelaere”, Mar. "
                             "2020. doi:10.48550/arXiv.2003.12268")


def test_journal_words_that_are_not_abbreviations_get_no_full_stop():
    raw = ("B. Ha et al., “Device design”, Phys. Rev. Fluids, vol. 3, p. 114202, 2018. "
           "doi:10.1103/PhysRevFluids.3.114202")
    assert fix(raw).text == raw


def test_only_presentation_fixes_are_automatic():
    assert fix("A. Alpha, B. Beta and C. Gamma, “Title”, Phys. Rev. Lett., vol. 1, p. 2, "
               "2020. DOI: 10.1103/X.1.2").presentation_only
    assert not fix("Alpha, A., “Title”, Phys. Rev. Lett., vol. 1, p. 2, 2020.").presentation_only


# ---------------------------------------------------------------------------
# 3. What they cannot fix is described, for the model or the editor
# ---------------------------------------------------------------------------

def test_a_doi_for_another_conference_is_for_the_editor():
    raw = ("C. T. Ratcliff, K. Fukushima, Y. Hao, and J. Wan, “Extending JuTrack's "
           "capabilities”, in Proc. HIAT'25, East Lansing, USA, 2025, pp. 50-53. "
           "doi:10.18429/JACoW-IPAC2024-WEPR52")
    d = describe(raw, lint(raw), kind="conference_published")
    assert [i.code for i in d.editor_issues] == ["REF-DOI-OTHER-CONF"]
    assert d.level == "high"
    assert "IPAC'24" in d.for_editor() and "HIAT'25" in d.for_editor()
    assert d.model_issues == []           # never sent to the model


def test_missing_facts_are_named_and_never_guessed():
    raw = ("H. Alamprese and Y. Hao, “Computation model for space charge”, in Proc. HIAT'25, "
           "East Lansing, USA, Jun. 2025. doi:10.18429/JACoW-HIAT2025")
    codes = {i.code: i for i in lint(raw)}
    assert codes["REF-DOI-INCOMPLETE"].who == EDITOR and codes["REF-DOI-INCOMPLETE"].fix is None
    assert "paper ID" in codes["REF-DOI-INCOMPLETE"].needs


def test_a_verified_fact_fills_the_gap_with_its_source():
    raw = ("H. Alamprese and Y. Hao, “Computation model for space charge”, in Proc. HIAT'25, "
           "East Lansing, USA, Jun. 2025. doi:10.18429/JACoW-HIAT2025")
    facts = {"doi": ("10.18429/JACoW-HIAT2025-TUP02", "refs.jacow.org"),
             "pages": ("80-83", "refs.jacow.org")}
    result = fix(raw, facts=facts)
    assert result.text.endswith("Jun. 2025, pp. 80-83. doi:10.18429/JACoW-HIAT2025-TUP02")
    assert result.sources == ["refs.jacow.org"] and not result.presentation_only


def test_pages_that_disagree_with_the_dois_record_are_for_the_editor():
    raw = ("D. Sagan et al., “Bmad-Julia”, in Proc. IPAC’24, Nashville, USA, 2024, pp. "
           "2562-2565. doi:10.18429/JACoW-IPAC2024-WEPR52")
    issues = lint(raw, facts={"pages": ("2612–2615", "refs.jacow.org")})
    conflict = next(i for i in issues if i.code == "REF-FACT-PAGES")
    assert conflict.who == EDITOR and "2612-2615" in conflict.message


def test_judgement_is_for_the_model_with_annex_b_layout_and_example():
    raw = ("D. Sagan, M. Bertz et al., Simulations of future particle accelerators: issues and "
           "mitigations. Journal of Instrumentation, 16(10):T10002, Oct. 2021.")
    result = fix(raw)
    d = describe(result.text, result.remaining, kind=kind_of(result.text))
    assert [i.code for i in d.model_issues] == ["REF-TITLE-MISSING"] and d.level == "medium"
    prompt = d.for_model()
    assert "Annex B example:" in prompt and "Phys. Rev. Lett., vol. 114" in prompt
    assert "where the title begins and ends" in prompt


def test_the_kind_comes_from_the_text_before_the_formatters_guess():
    raw = ("J. Kennedy and R. Eberhart, “Particle swarm optimization”, in Proc. ICNN'95, "
           "Perth, WA, Australia, 1995, pp. 1942-1948.")
    assert kind_of(raw, "journal") == "conference_published"
    assert kind_of("USPAS, https://uspas.fnal.gov/index.shtml") == "web"


# ---------------------------------------------------------------------------
# 4. The AI skill: the model fixes, the rules and the damage check decide
# ---------------------------------------------------------------------------

MISSING_TITLE = ("D. Sagan, M. Bertz et al., Simulations of future particle accelerators: "
                 "issues and mitigations. Journal of Instrumentation, 16(10):T10002, Oct. 2021.")


def _difficulty(raw: str) -> Difficulty:
    result = fix(raw)
    return describe(result.text, result.remaining, kind=kind_of(result.text))


class Model:
    """A stand-in for the local model, answering from a list."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, system, user, **_):
        self.prompts.append(user)
        return self.answers.pop(0)


def test_a_good_answer_is_accepted_and_finished_by_the_rules():
    d = _difficulty(MISSING_TITLE)
    model = Model("<think>the title is…</think>\nD. Sagan, M. Bertz et al., \"Simulations of "
                  "future particle accelerators: issues and mitigations\", Journal of "
                  "Instrumentation, 16(10):T10002, Oct. 2021.")
    answer = repair(d, chat=model, model="test-model")
    # The model only quoted the title; the rules then saw the journal and laid it out.
    assert answer.text == ("D. Sagan, M. Bertz, et al., “Simulations of future particle "
                           "accelerators: issues and mitigations”, J. Instrum., vol. 16, no. "
                           "10, p. T10002, Oct. 2021.")
    assert answer.fixed == ["REF-TITLE-MISSING"] and answer.attempts == 1


def test_an_answer_that_loses_a_number_is_sent_back_with_the_reason():
    d = _difficulty(MISSING_TITLE)
    model = Model("D. Sagan, M. Bertz et al., “Simulations of future particle accelerators: "
                  "issues and mitigations”, J. Instrum., vol. 16, Oct. 2021.",
                  "D. Sagan, M. Bertz et al., “Simulations of future particle accelerators: "
                  "issues and mitigations”, Journal of Instrumentation, 16(10):T10002, Oct. "
                  "2021.")
    answer = repair(d, chat=model, model="test-model")
    assert answer is not None and answer.attempts == 2
    assert "dropped the number(s)" in model.prompts[1]          # the reason went back
    assert "T10002" in answer.text


def test_two_bad_answers_leave_it_to_the_editor():
    d = _difficulty(MISSING_TITLE)
    bad = "D. Sagan et al., “Simulations”, 2021."
    assert repair(d, chat=Model(bad, bad), model="test-model") is None
    result = check_reference(MISSING_TITLE, llm=True, chat=Model(bad, bad), model="test-model")
    assert result.text == fix(MISSING_TITLE).text and result.model_refused
    assert [i.code for i in result.left] == ["REF-TITLE-MISSING"]


def test_an_invented_value_is_refused():
    d = _difficulty(MISSING_TITLE)
    invented = ("D. Sagan, M. Bertz et al., “Simulations of future particle accelerators: "
                "issues and mitigations”, Journal of Instrumentation, 16(10):T10002, Oct. 2021. "
                "doi:10.1088/1748-0221/16/10/T10002")
    problems = verify(d.text, invented, d)
    assert any("added the number" in p or "nothing may be lost or invented" in p
               for p in problems)


def test_a_name_lowercased_by_the_model_is_refused():
    raw = ("P. Hagedorn, “A note on Hamiltonians”, Celest. Mech., vol. 17, pp. 127-129, 1978, "
           "in preparation.")
    d = describe(raw, lint(raw), kind="journal")
    d.model_issues = [i for i in d.editor_issues]  # pretend the model may act
    d.editor_issues = []
    problems = verify(raw, raw.replace("Hamiltonians", "hamiltonians"), d)
    assert any("may be names" in p for p in problems)


def test_titles_are_recased_word_by_word_not_rewritten():
    raw = ("P. Hagedorn, “A Short Note on Hamiltonians Linear in the Momenta”, Celestial "
           "Mechanics, vol. 17, pp. 127-129, 1978. doi:10.1007/BF01371324")
    d = describe(raw, lint(raw), kind="journal")
    assert [i.code for i in d.model_issues] == ["REF-TITLE-CASE"]

    def recase(text):              # the labelling skill (three samples must agree)
        return text.replace("Short Note on Hamiltonians Linear in the Momenta",
                            "short note on hamiltonians linear in the momenta"), ()
    answer = repair(d, chat=Model(), recase=recase, model="test-model")
    # A name the labels lowercased gets its capital back from the rules.
    assert "“A short note on Hamiltonians linear in the momenta”" in answer.text
    assert answer.how == ["title capitals, word by word"]


def test_no_model_means_the_description_is_all():
    result = check_reference(MISSING_TITLE, llm=False)
    assert result.repair is None and not result.model_refused
    assert result.final_description("[1]").model_issues[0].code == "REF-TITLE-MISSING"


def test_the_models_reply_is_cleaned():
    assert clean("<think>x</think>\n```\n[3] A. B, “T”, 2020.\n```") == "A. B, “T”, 2020."
    assert clean("Corrected reference: A. B, “T”, 2020.") == "A. B, “T”, 2020."


# ---------------------------------------------------------------------------
# 5. Through the agent: src.references.screen_reference
# ---------------------------------------------------------------------------

def test_screening_never_asks_the_model_when_told_not_to(monkeypatch):
    from src import references
    from src.llm import client

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("REFERENCE_FIX", "off")
    monkeypatch.setattr(client, "chat", lambda *a, **k: pytest.fail("the model was asked"))
    references.screen_reference(MISSING_TITLE, offline=True)


# ---------------------------------------------------------------------------
# LaTeX on the way in
# ---------------------------------------------------------------------------

def test_latex_references_become_plain_text():
    from src.references import latex_to_plain

    assert latex_to_plain(r"J. Beebe-Wang \textquotedblleft{}Electron-Ion Collider"
                          r"\textquotedblright, BNL, 2021. \ \ \url{https://x.org/a.pdf}") == \
        "J. Beebe-Wang “Electron-Ion Collider”, BNL, 2021. https://x.org/a.pdf"
    assert latex_to_plain(r"F. C. Iselin, ``Lie maps,'' Part. Accel. {\bf 17}, pp. 1-2.") == \
        "F. C. Iselin, “Lie maps,” Part. Accel. 17, pp. 1-2."
    assert latex_to_plain(r"M. M\"uller, J. Garc\'{i}a, \v{S}. Novak, at DA$\Phi$NE") == \
        "M. Müller, J. García, Š. Novak, at DAΦNE"
    assert latex_to_plain(r"X. Y, 2021, \doi{10.1/x} \end{thebibliography}") == \
        "X. Y, 2021, doi:10.1/x"


def test_the_last_bibitem_stops_at_the_end_of_the_bibliography(tmp_path):
    from src.parser.latex_parser import parse_latex

    tex = tmp_path / "P.tex"
    tex.write_text("\\documentclass{jacow}\\begin{document}Text \\cite{a}.\n"
                   "\\begin{thebibliography}{9}\n\\bibitem{a} A. B, ``T'', 2020.\n"
                   "\\end{thebibliography}\n\\end{document}\n", encoding="utf-8")
    assert parse_latex(tex).references[0].raw_text == "A. B, ``T'', 2020."


# ---------------------------------------------------------------------------
# Mistakes the full IPAC'27 test run exposed
# ---------------------------------------------------------------------------

def test_a_talk_never_gets_a_doi_from_a_lookup():
    # refs.jacow.org matched the paper ID MOPC67 to an IPAC'24 paper.
    raw = ("S. Nagaitsev, “The EIC accelerator”, presented at NAPAC’25, Sacramento, CA, Aug. "
           "2025, paper MOPC67, this conference.")
    facts = {"doi": ("10.18429/JACoW-IPAC2024-MOPC67", "refs.jacow.org")}
    assert fix(raw, facts=facts).text == raw


def test_a_looked_up_jacow_doi_must_name_the_same_conference():
    raw = ("A. Alpha, “Title”, in Proc. HIAT'25, East Lansing, MI, USA, Jun. 2025, pp. 1-4.")
    wrong = {"doi": ("10.18429/JACoW-IPAC2024-WEPR52", "refs.jacow.org")}
    right = {"doi": ("10.18429/JACoW-HIAT2025-TUP02", "refs.jacow.org")}
    assert "doi:" not in fix(raw, facts=wrong).text
    assert fix(raw, facts=right).text.endswith("pp. 1-4. doi:10.18429/JACoW-HIAT2025-TUP02")


def test_an_arxiv_doi_is_not_added_to_a_proceedings_paper():
    raw = ("D. Eriksson et al., “Scalable global optimization”, in Proc. NeurIPS 2019, "
           "Vancouver, Canada, Dec. 2019.")
    assert fix(raw, facts={"doi": ("10.48550/arXiv.1910.01739", "Crossref")}).text == raw


def test_a_found_doi_takes_the_place_of_the_web_address():
    raw = ("J. Beebe-Wang et al., “Electron-Ion Collider: conceptual design report”, "
           "Brookhaven National Laboratory, 2021. https://www.bnl.gov/EC/files/EIC_CDR_Final.pdf")
    result = fix(raw, facts={"doi": ("10.2172/1765663", "Crossref")})
    assert result.text.endswith("Brookhaven National Laboratory, 2021. doi:10.2172/1765663")
    assert result.sources == ["Crossref"] and not result.presentation_only


def test_a_bare_volume_is_laid_out_not_added_twice():
    raw = ("Z. He et al., “Linear envelope model”, Phys. Rev. ST Accel. Beams, 17, p. 034001, "
           "2014. doi:10.1103/PhysRevSTAB.17.034001")
    facts = {"volume": ("17", "Crossref"), "issue": ("3", "Crossref")}
    text = fix(raw, facts=facts).text
    assert text.count("17,") + text.count("17 ") <= 1 and "vol. 17, p. 034001, 2014" in text


def test_a_repeated_month_and_a_garbled_title_are_found():
    assert fix("E. J. Stahlman, “Revision 3”, May, May 1996. doi:10.2172/243454").text == \
        "E. J. Stahlman, “Revision 3”, May 1996. doi:10.2172/243454"
    garbled = ("Wang, “B., Rosales-Fernandez, C., tang, W., improve performance: A guide”, 2019.")
    assert "REF-TITLE-NAMES" in {i.code for i in lint(garbled)}


def test_small_punctuation_before_a_url_and_in_a_title():
    assert fix("EPIC code., https://github.com/yuehao/EPIC.jl.git").text == \
        "EPIC code, https://github.com/yuehao/EPIC.jl.git"
    assert "“Linear envelope model for multi-charge state linac”" in fix(
        "Z. He, “Linear envelope model for multi- charge state linac”, Phys. Rev. Lett., "
        "vol. 1, p. 2, 2014.").text


def test_a_report_number_is_never_taken_for_a_journal_name():
    from src import references

    raw = ("E. Forest, “Fringe effects in MAD”, KEK Preprint 2005-109, Mar. 2006.")
    assert references._journal_substitutions(raw, {"rec": {"journal": "KEK Preprint"}}) == []


def test_a_suspended_hyphen_is_kept():
    raw = ("K. L. Brown, “A first- and second-order matrix theory”, SLAC Report No. 75, 1982.")
    assert fix(raw).text == raw


def test_a_garbled_formatter_rewrite_loses_to_the_rules(monkeypatch):
    from src import references

    raw = ("Wang, B., Rosales-Fernandez, C., Tang, W., Improve Performance by Vectorizing "
           "Particle-in-Cell Codes: A Guide, Intel.com, 2019")

    class Garbling:
        def process_record(self, text):
            return {"rec": {}, "flags": [], "derived_fields": [], "provenance": {},
                    "integrity": {"verdict": "verified"}, "source": "heuristic",
                    "type": "journal",
                    "formatted": ("Wang, “B., Rosales-Fernandez, C., Tang, W., Improve "
                                  "Performance by Vectorizing Particle-in-Cell Codes: A "
                                  "Guide, Intel.com”, 2019.")}
    monkeypatch.setattr(references, "_agent", lambda offline, llm: Garbling())
    monkeypatch.setenv("LLM_ENABLED", "false")
    result = references.screen_reference(raw)
    assert "“B.," not in (result.after or "")



# ---------------------------------------------------------------------------
# What NAPAC'25's editors taught (author's original against their final)
# ---------------------------------------------------------------------------

def test_a_name_with_a_digit_is_never_lowercased():
    raw = ("K. Harrig et al., “Simulation of Bunch Formation for the Mu2e Experiment”, in Proc. "
           "IPAC’22, Bangkok, Thailand, Jun. 2022, pp. 1-4.")
    assert "Mu2e" in fix(raw).text


def test_a_doi_on_its_own_line_is_fine():
    raw = ("S. Seletskiy et al., “Magnetic shielding”, in Proc. NAPAC’16, Chicago, IL, USA, Oct. "
           "2016, pp. 1030-1032.\ndoi:10.18429/JACoW-NAPAC2016-WEPOB61")
    assert "REF-DOI-SEP" not in {i.code for i in lint(raw)}


def test_initials_without_full_stops_are_fixed_alike():
    raw = ("A. L. Edelen, SG Biedron, BE Chase, D Edstrom, SV Milton, and P Stabile, “Neural "
           "networks for modeling and control of particle accelerators”, IEEE Trans. Nucl. Sci., "
           "vol. 63, no. 2, pp. 878-897, 2016.")
    assert fix(raw).text.startswith("A. L. Edelen, S. G. Biedron, B. E. Chase, D. Edstrom, "
                                    "S. V. Milton, and P. Stabile, “")
    assert fix("CMS Collaboration, “Title”, Phys. Rev. Lett., vol. 1, p. 2, 2020.").text \
        .startswith("CMS Collaboration")


def test_one_standard_for_every_conference(monkeypatch):
    raw = ("N. Eddy et al., “Beam Instrumentation at the Fermilab IOTA Ring,” in Proc. IBIC’19, "
           "Malmö, Sweden, Sep. 2019, pp. 22-28. doi:10.18429/JACoW-IBIC2019-MOBO02")
    results = []
    for profile in ("jacow", "napac"):
        monkeypatch.setenv("HOUSE_STYLE", profile)
        results.append(fix(raw).text)
    assert results[0] == results[1]
    assert "IOTA Ring”, in Proc." in results[0]          # the comma goes outside


def test_the_authors_conference_name_stays_with_the_label_added():
    raw = ("X. Huang, Z. Zhang, and M. Song, “Multi-objective optimizer,” 12th Int. Particle Acc. "
           "Conf., Campinas, SP, Brazil, May 2021, pp. 3383-3386. doi:10.18429/JACoW-IPAC2021-WEPAB304")
    assert fix(raw).text == ("X. Huang, Z. Zhang, and M. Song, “Multi-objective optimizer”, in "
                             "Proc. 12th Int. Particle Acc. Conf. (IPAC’21), Campinas, SP, Brazil, "
                             "May 2021, pp. 3383-3386. doi:10.18429/JACoW-IPAC2021-WEPAB304")


def test_a_degenerate_range_of_article_numbers_stays_pp():
    raw = ("S. Antipov et al., “IOTA”, J. Instrum., vol. 12, no. 3, pp. T03002–T03002, Mar. 2017.")
    assert "pp. T03002–T03002" in fix(raw).text


def test_cyrillic_lookalikes_become_latin():
    raw = ("S. Simrock et al., “First demonstration of microphonic control of а superconducting "
           "cavity”, in Proc. РАС'О3, Portland, OR, USA, May 2003, рр. 470-472.")
    text = fix(raw).text
    assert "PAC" in text and "pp. 470-472" in text and not any("\u0400" <= c <= "\u04ff" for c in text)


def test_a_doi_in_a_web_address_becomes_the_doi():
    raw = ("J. Amundson et al., “Calibration of the Fermilab Booster ionization profile monitor”, "
           "Phys. Rev. Spec. Top. Accel. Beams, vol. 6, no. 10, Oct. 2003. "
           "https://link.aps.org/doi/10.1103/PhysRevSTAB.6.102801")
    assert fix(raw).text.endswith("Oct. 2003. doi:10.1103/PhysRevSTAB.6.102801")


def test_no_rewrite_may_lose_a_doi_or_a_url():
    from src.references import _keeps_links

    raw = "A. B, “T”, 2003. https://link.aps.org/doi/10.1103/PhysRevSTAB.6.102801"
    assert not _keeps_links(raw, "A. B, “T”, 2003.")
    assert _keeps_links(raw, "A. B, “T”, 2003. doi:10.1103/PhysRevSTAB.6.102801")



def test_a_repeated_state_is_found():
    raw = ("S. Nagaitsev, “The EIC accelerator”, presented at NAPAC’25, Sacramento, CA, CA, Aug. "
           "2025, paper MOXP01, this conference.")
    assert "Sacramento, CA, Aug. 2025" in fix(raw).text
