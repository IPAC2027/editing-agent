"""src.refcheck.doi: finding a missing DOI, correcting a wrong one, never guessing.

The registries are faked (Crossref, DataCite, doi.org): each case is one NAPAC'25's
editors met, author's reference against their final version.
"""
from __future__ import annotations

import pytest

from src.refcheck import doi as D
from src.refcheck import fix


def registry(monkeypatch, *, works=None, search=None, datacite=None, jacow_search=None,
             handles=None):
    works = {k.lower(): v for k, v in (works or {}).items()}
    datacite = {k.lower(): v for k, v in (datacite or {}).items()}
    asked = []

    def get(url, params=None, service="crossref"):
        asked.append(url)
        if url == "https://api.crossref.org/works":
            return 200, {"message": {"items": search or []}}
        if url.startswith("https://api.crossref.org/works/"):
            item = works.get(url.split("/works/", 1)[1].lower())
            return (200, {"message": item}) if item else (404, None)
        if url == "https://api.datacite.org/dois":
            return 200, {"data": jacow_search or []}
        if url.startswith("https://api.datacite.org/dois/"):
            item = datacite.get(url.split("/dois/", 1)[1].lower())
            return (200, {"data": item}) if item else (404, None)
        if url.startswith("https://doi.org/api/handles/"):
            known = (handles or {}).get(url.rsplit("/handles/", 1)[1].lower())
            return (200, {"responseCode": 1}) if known else (404, None)
        raise AssertionError(url)

    monkeypatch.setattr(D, "_get", get)
    return asked


def article(doi, title, family, year, journal, volume, page, kind="journal-article"):
    return {"DOI": doi, "title": [title], "author": [{"family": family}],
            "issued": {"date-parts": [[year]]}, "container-title": [journal],
            "volume": str(volume), "page": str(page), "type": kind}


def jacow(doi, title, family, year, container):
    return {"id": doi.lower(), "attributes": {"doi": doi, "titles": [{"title": title}],
            "creators": [{"familyName": family}], "publicationYear": year,
            "container": {"title": container}, "types": {"resourceTypeGeneral": "ConferencePaper"}}}


TAC = article("10.1109/TAC.2012.2225514", "Minimum-seeking for CLFs: Universal semiglobally "
              "stabilizing feedback under unknown control directions", "Scheinker", 2013,
              "IEEE Transactions on Automatic Control", 58, "1107-1122")
CDC = article("10.1109/CDC.2012.6426821", "Minimum-seeking for CLFs: Universal semiglobally "
              "stabilizing feedback under unknown control directions", "Scheinker", 2012,
              "2012 IEEE 51st Conference on Decision and Control (CDC)", "", "1234-1239",
              kind="proceedings-article")


def test_a_missing_doi_is_found_and_the_journal_article_is_not_the_conference_paper(monkeypatch):
    registry(monkeypatch, search=[CDC, TAC])
    raw = ("A. Scheinker and M. Krstić, “Minimum-seeking for CLFs: Universal semiglobally "
           "stabilizing feedback under unknown control directions”, IEEE Trans. Autom. Control, "
           "vol. 58, no. 5, pp. 1107-1122, 2013.")
    report = D.check(raw)
    assert (report.status, report.doi) == ("found", "10.1109/TAC.2012.2225514")
    result = fix(raw, facts={"doi": (report.doi, report.source)})
    assert result.text.endswith("pp. 1107-1122, 2013. doi:10.1109/TAC.2012.2225514")


def test_a_doi_that_does_not_exist_is_corrected_from_the_title(monkeypatch):
    right = article("10.1103/PhysRevSTAB.2.114202", "Space charge dynamics in high intensity "
                    "rings", "Holmes", 1999, "Physical Review Special Topics - Accelerators and "
                    "Beams", 2, "114202")
    registry(monkeypatch, search=[right])
    raw = ("J. A. Holmes et al., “Space charge dynamics in high intensity rings”, Phys. Rev. "
           "Spec. Top. Accel. Beams, vol. 2, p. 114202, Nov. 1999. doi:10.1103/PhysRevSTAB.2114202")
    report = D.check(raw)
    assert report.status == "corrected" and report.doi == "10.1103/PhysRevSTAB.2.114202"
    assert "does not exist, a typo" in report.reason
    text = fix(raw, facts={"doi_fix": (report.written, report.doi, report.source,
                                       report.reason)}).text
    assert text.endswith("Nov. 1999. doi:10.1103/PhysRevSTAB.2.114202")


def test_another_papers_doi_is_corrected(monkeypatch):
    other = article("10.1103/PhysRevAccelBeams.27.094601", "Something else entirely about "
                    "lattices", "Nobody", 2024, "Physical Review Accelerators and Beams", 27,
                    "094601")
    right = jacow("10.18429/JACoW-IPAC2024-WEPR52", "Bmad-Julia: a Julia environment for "
                  "accelerator simulations including machine learning", "Sagan", 2024,
                  "Proc. IPAC'24")
    registry(monkeypatch, works={other["DOI"]: other}, jacow_search=[right])
    raw = ("D. Sagan et al., “Bmad-Julia: a Julia environment for accelerator simulations "
           "including machine learning”, in Proc. IPAC’24, Nashville, TN, USA, May 2024, pp. "
           "2612-2615. doi:10.1103/PhysRevAccelBeams.27.094601")
    report = D.check(raw)
    assert report.status == "corrected" and report.doi == "10.18429/JACoW-IPAC2024-WEPR52"
    assert "another paper's" in report.reason


def test_a_jacow_doi_cut_short_or_with_a_typo_is_completed(monkeypatch):
    right = jacow("10.18429/JACoW-ERL2019-THCOYBS02", "Commissioning of the energy recovery "
                  "linac at Cornell", "Hoffstaetter", 2019, "Proc. ERL'19")
    registry(monkeypatch, jacow_search=[right])
    raw = ("G. Hoffstaetter et al., “Commissioning of the energy recovery linac at Cornell”, in "
           "Proc. ERL’19, Berlin, Germany, Sep. 2019, pp. 1-4. doi:10.18429/JACoW-ERL2019-THCOBS02")
    report = D.check(raw)
    assert report.status == "corrected" and report.doi == "10.18429/JACoW-ERL2019-THCOYBS02"


def test_a_jacow_paper_id_makes_its_doi(monkeypatch):
    paper = jacow("10.18429/JACoW-NAPAC2019-TUPLM24", "Electron heating by ions in cooling "
                  "rings", "Zhao", 2019, "Proc. NAPAC'19")
    registry(monkeypatch, datacite={paper["attributes"]["doi"]: paper})
    raw = ("H. Zhao and M. Blaskiewicz, “Electron heating by ions in cooling rings”, in Proc. "
           "NAPAC’19, Lansing, MI, USA, Sep. 2019, paper TUPLM24.")
    report = D.check(raw)
    assert (report.status, report.doi) == ("found", "10.18429/JACoW-NAPAC2019-TUPLM24")


def test_two_records_that_fit_equally_are_offered_for_the_editor_to_choose(monkeypatch):
    third = article("10.1142/8335", "Accelerator physics", "Lee", 2018, "", "", "", kind="book")
    fourth = article("10.1142/11111", "Accelerator physics", "Lee", 2018, "", "", "", kind="book")
    registry(monkeypatch, search=[third, fourth])
    raw = "S.-Y. Lee, Accelerator Physics. Singapore: World Scientific, 2018."
    report = D.check(raw, "book")
    # Not "found": two editions fit; one is offered, the other named.
    assert report.status == "possible" and len(report.others) == 1
    assert "Other close records" in report.reason


def test_a_right_doi_is_left_alone_and_no_answer_changes_nothing(monkeypatch):
    right = article("10.1103/PhysRevLett.104.174801", "Test of crab-waist collisions at the "
                    "DAΦNE Φ factory", "Zobov", 2010, "Physical Review Letters", 104, "174801")
    registry(monkeypatch, works={right["DOI"]: right})
    raw = ("M. Zobov et al., “Test of crab-waist collisions at DAΦNE Φ-factory”, Phys. Rev. "
           "Lett., vol. 104, p. 174801, 2010. doi:10.1103/PhysRevLett.104.174801")
    assert D.check(raw).status == "ok"
    monkeypatch.setattr(D, "_get", lambda *a, **k: D.UNREACHABLE)
    assert D.check(raw).status == "unknown"


def test_a_talk_or_an_arxiv_paper_is_not_searched(monkeypatch):
    asked = registry(monkeypatch, search=[TAC])
    assert D.check("S. Nagaitsev, “The EIC accelerator”, presented at NAPAC’25, Sacramento, CA, "
                   "USA, Aug. 2025, paper MOXP01, this conference.").status == "none"
    assert D.check("A. B, “Title of preprint”, Jan. 2025, arXiv:2501.10602.").status == "none"
    assert asked == []


def test_a_doi_that_does_not_exist_and_no_replacement_is_for_the_editor(monkeypatch):
    registry(monkeypatch)
    raw = ("A. Alpha, “A title nobody indexed”, J. Unknown Res., vol. 1, p. 2, 2020. "
           "doi:10.9999/does.not.exist")
    report = D.check(raw)
    assert report.status == "unresolved"
    issues = {i.code: i for i in __import__("src.refcheck", fromlist=["lint"]).lint(
        raw, facts={"doi_problem": (report.written, report.reason)})}
    assert issues["REF-DOI-UNRESOLVED"].who == "editor"


def test_a_dois_spelling_is_repaired_without_asking():
    assert fix("A. B, “T”, Phys. Rev. Lett., vol. 1, p. 2, 2020. doi:10,1103/PhysRevLett.1.2").text \
        .endswith("doi:10.1103/PhysRevLett.1.2")
    assert fix("A. B, “T”, Phys. Rev. Lett., vol. 1, p. 2, 2020. "
               "doi:10.1103/physrevstab.17.021007\\vskip3mm").text.endswith(
        "doi:10.1103/physrevstab.17.021007")


def test_screening_offers_the_corrected_doi_with_its_reason(monkeypatch):
    from src import references

    right = article("10.1080/00295450.2021.1997057", "Neutron yields from accelerator targets",
                    "Smith", 2021, "Nuclear Technology", 208, "1-12")
    registry(monkeypatch, search=[right])
    monkeypatch.setenv("AIAGENT_OFFLINE", "0")
    monkeypatch.setenv("LLM_ENABLED", "false")

    class Formatter:
        def process_record(self, raw):
            return {"rec": {}, "flags": [], "derived_fields": [], "provenance": {},
                    "integrity": {"verdict": "verified"}, "source": "heuristic", "formatted": raw}
    monkeypatch.setattr(references, "_agent", lambda offline, llm: Formatter())
    raw = ("J. Smith, “Neutron yields from accelerator targets”, Nucl. Technol., vol. 208, pp. "
           "1-12, 2021. doi:10.1080/00295450.2021")
    result = references.screen_reference(raw, offline=False)
    assert result.after.endswith("doi:10.1080/00295450.2021.1997057")
    assert "does not exist" in result.message or "Wrong DOI" in result.message or \
        "wrong DOI corrected" in result.message



def test_page_numbers_are_not_years_and_a_year_is_not_a_volume():
    f = D.fields_of("C. Liu et al., “Reconfiguration of RHIC straight sections”, in Proc. IPAC’22, "
                    "Bangkok, Thailand, Jun. 2022, pp. 1916–1919. doi:10.18429/JACoW-IPAC2022-WEPOPT034")
    assert f.year == 2022
    f = D.fields_of("J. Duris et al., “Bayesian optimization of a free-electron laser”, Phys. Rev. "
                    "Lett., Dec 2020, p. 124801.")
    assert f.volume == "" and f.year == 2020


def test_a_record_title_with_markup_still_matches():
    f = D.fields_of("Z. Omarov et al., “Comprehensive symmetric-hybrid ring design for a proton EDM "
                    "experiment at below 10^-29 e cm”, Phys. Rev. D, vol. 105, p. 032001, 2022.")
    w = D.Work("10.1103/PhysRevD.105.032001", title="Comprehensive symmetric-hybrid ring design "
               "for a proton EDM experiment at below <mml:math><mml:msup>10</mml:msup></mml:math> "
               "e cm", surnames=["Omarov"], year=2022, volume="105", page="032001",
               type="journal-article", container="Physical Review D")
    assert D.match(f, w, strict=False)[0] and D.match(f, w)[0]


def test_without_a_title_the_record_must_show_volume_and_page(monkeypatch):
    report = D.Work("10.2172/809659", title="Something at Fermilab", surnames=["Mokhov"], year=2003,
                    type="report")
    f = D.fields_of("N. V. Mokhov, Nucl. Instrum. Methods Phys. Res., Sect. A, vol. 506, no. 1-2, "
                    "pp. 99-115, 2003.")
    assert not D.match(f, report)[0]


def test_a_bare_title_gives_only_a_possible_doi(monkeypatch):
    found = article("10.2172/2203271", "Localized beam-induced heating analysis of the EIC vacuum "
                    "chamber components", "Sangroula", 2023, "", "", "", kind="report")
    registry(monkeypatch, search=[found])
    report = D.check("M. Sangroula et al., “Localized Beam-induced Heating Analysis of the EIC "
                     "Vacuum Chamber Components”.")
    # Too little to be sure, so not "found": offered for the editor to check.
    assert report.status == "possible" and report.doi == "10.2172/2203271"


def test_a_looser_match_says_what_differs(monkeypatch):
    near = article("10.1103/PhysRevAccelBeams.24.044001", "Beam intensity effects in the Fermilab "
                   "Booster synchrotron", "Eldred", 2021, "Physical Review Accelerators and Beams",
                   24, "044001")
    registry(monkeypatch, search=[near])
    raw = ("J. Eldred et al., “Beam intensity effects in Fermilab Booster synchrotron”, Phys. Rev. "
           "Accel. Beams, 2020.")
    report = D.check(raw)
    assert report.status in ("found", "possible")
    if report.status == "possible":
        assert "check" not in report.reason and "2021, not 2020" in report.reason
    text = fix(raw, facts={"doi_possible": ("", report.doi, report.source, report.reason)}).text \
        if report.status == "possible" else ""
    if text:
        assert text.endswith("doi:10.1103/PhysRevAccelBeams.24.044001")


def test_a_possible_doi_is_never_automatic():
    raw = "A. B, “Some title of a paper”, Phys. Rev. Lett., vol. 1, p. 2, 2020."
    result = fix(raw, facts={"doi_possible": ("", "10.1103/PhysRevLett.1.2", "Crossref",
                                              "possibly 10.1103/PhysRevLett.1.2")})
    assert result.text.endswith("doi:10.1103/PhysRevLett.1.2")
    assert not result.presentation_only
    assert result.applied[-1].message.startswith("Possible DOI, check it before accepting")


def test_an_arxiv_web_address_is_an_arxiv_paper(monkeypatch):
    asked = registry(monkeypatch, search=[TAC])
    assert D.check("A. Shemyakin, “Orbit response measurements with oscillating trajectories”, "
                   "FERMILAB-TM-2763-AD, Sep. 2021. https://arxiv.org/abs/2109.11589").status == "none"
    assert asked == []



def test_the_publisher_and_the_kind_of_work_must_agree():
    f = D.fields_of("K. Khare et al., “Fourier optics and computational imaging”, Springer, 2015.")
    wiley = D.Work("10.1002/9781118900352", title="Fourier Optics and Computational Imaging",
                   surnames=["Khare"], year=2015, type="book", publisher="Wiley")
    assert f.kind == "book" and not D.match(f, wiley)[0]
    f = D.fields_of("A. Zelenski et al., “Optically pumped polarized H- ion source for RHIC spin "
                    "physics”, Rev. Sci. Instr., 73, 2002, 888")
    proceedings = D.Work("10.1142/9789812777683_0031", title="Optically pumped polarized H- ion "
                         "source for RHIC spin physics", surnames=["Zelenski"], year=2002,
                         type="proceedings-article", container="Spin 2000 proceedings")
    assert not D.match(f, proceedings)[0]
    f = D.fields_of("J. T. M. Lyles et al., “New concept for a high power 805 MHz RF amplifier”, in "
                    "Proc. LINAC’24, Chicago, IL, USA, Aug. 2024, pp. 1-4.")
    report = D.Work("10.2172/2447583", title="New concept for a high power 805 MHz RF amplifier",
                    surnames=["Lyles"], year=2024, type="report")
    assert not D.match(f, report)[0]



def test_a_chapters_doi_is_right_when_the_chapter_is_named(monkeypatch):
    chapter = article("10.1007/978-3-031-59979-8_11", "FFAG, Linear", "Méot", 2024, "Understanding "
                      "the Physics of Particle Accelerators", "", "", kind="book-chapter")
    registry(monkeypatch, works={chapter["DOI"]: chapter})
    raw = ("F. Méot, “Understanding the Physics of Particle Accelerators”, Chapter 11- FFAG, Linear, "
           "Springer, 2024. doi:10.1007/978-3-031-59979-8_11")
    assert D.check(raw).status == "ok"



def test_a_correction_keeps_the_authors_capitals_and_jacows_form():
    assert D.display("10.1103/physrevstab.2.114202", "10.1103/PhysRevSTAB.2114202") == \
        "10.1103/PhysRevSTAB.2.114202"
    assert D.display("10.18429/jacow-ipac2025-tupm114", "10.18429/JACoW-IPAC25-TUPM114") == \
        "10.18429/JACoW-IPAC2025-TUPM114"
    raw = ("R. Kazimi, “An extraction scheme”, in Proc. IPAC’25, Taipei, Taiwan, Jun. 2025, pp. "
           "1407-1410. doi:10.18429/JACoW-IPAC25-TUPM114")
    text = fix(raw, facts={"doi_fix": ("10.18429/JACoW-IPAC25-TUPM114",
                                       "10.18429/JACoW-IPAC2025-TUPM114", "DataCite",
                                       "the cited DOI does not exist")}).text
    assert text.endswith("doi:10.18429/JACoW-IPAC2025-TUPM114")



def test_a_conference_label_is_not_a_paper_id(monkeypatch):
    paper = jacow("10.18429/JACoW-HB2023-TUA2I1", "Xsuite: an integrated beam physics simulation "
                  "framework", "Iadarola", 2024, "Proc. HB'23")
    registry(monkeypatch, datacite={paper["attributes"]["doi"]: paper})
    report = D.check("G. Iadarola et al., “Xsuite: An Integrated Beam Physics Simulation "
                     "Framework,” JACoW HB2023, TUA2I1 (2024).")
    assert (report.status, report.doi) == ("found", "10.18429/JACoW-HB2023-TUA2I1")


def test_a_looser_match_with_two_disagreements_is_not_offered():
    f = D.fields_of("J. D. Jackson, “Classical electrodynamics”, Wiley, 1999.")
    review = D.Work("10.1119/1.19136", title="Classical Electrodynamics, 3rd ed.",
                    surnames=["Jackson"], year=1999, type="journal-article",
                    container="American Journal of Physics", publisher="AAPT")
    assert not D.loose_match(f, review)[0]
