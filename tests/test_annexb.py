"""src.annexb: every reference in the exact layout of Appendix B of the JACoW style guide.

Offline unless a test fakes a registry (tests/conftest.py blocks Crossref, DataCite,
refs.jacow.org, abbrevIso, JabRef and the JACoW conference list).
"""
from __future__ import annotations

import json
import re

import pytest

from src import references
from src.annexb import conferences, journals
from src.annexb.categories import CATEGORIES, HEADINGS
from src.annexb.engine import build, finish, format_reference
from src.edits import Tier
from src.refcheck import doi as registry
from tests.data.annexb_examples import EXAMPLES


def offline(text: str):
    p, out = build(text, online=False, llm=False)
    return finish(p, out)


# ---------------------------------------------------------------------------
# Appendix B itself
# ---------------------------------------------------------------------------

def test_there_are_sixteen_kinds_as_in_appendix_b():
    assert sorted({c.number for c in CATEGORIES.values()}) == list(range(1, 17))
    assert len(HEADINGS) == 16


@pytest.mark.parametrize("kind,text", EXAMPLES, ids=[f"{k}-{i}" for i, (k, _) in
                                                     enumerate(EXAMPLES)])
def test_every_appendix_b_example_comes_out_exactly_as_printed(kind, text):
    out = offline(text)
    assert out.category == kind
    assert out.text == text
    assert out.conforms and not out.missing


def test_the_latex_form_is_jacows_own():
    out = offline(EXAMPLES[1][1])
    assert out.latex == ("A.~Alpha and B.~T.~Beta, “An overview of modern control systems”, in "
                         "\\emph{Proc.\\ ICALEPCS'23}, Cape Town, South Africa, Oct. 2023, "
                         "pp.~57-59. \\doi{10.18429/JACoW-ICALEPCS2023-PAPERID}")
    journal = offline(EXAMPLES[7][1])
    assert journal.latex.startswith("A.~Alpha \\emph{et al.}, “Title of paper published in "
                                    "journal”, \\emph{Phys. Rev. Lett.}, vol.~114, no.~5, ")


def test_latex_keeps_math_and_escapes_the_rest():
    out = offline("A. Alpha, “Nb$_3$Sn & Nb cavities at 100%”, Phys. Rev. Lett., vol. 1, "
                  "p. 2, 2020.")
    assert "“Nb$_3$Sn \\& Nb cavities at 100\\%”" in out.latex


# ---------------------------------------------------------------------------
# Real references, rewritten
# ---------------------------------------------------------------------------

REAL = [
    # authors family name first, journal numbers without vol./p.
    ("Zampetakis, M., Antoniou, F., “Interplay of space charge”, Phys. Rev. Accel. Beams 27, "
     "064403, Mar. 2024. doi:10.1103/PhysRevAccelBeams.27.064403",
     "M. Zampetakis and F. Antoniou, “Interplay of space charge”, Phys. Rev. Accel. Beams, "
     "vol. 27, p. 064403, Mar. 2024. doi:10.1103/PhysRevAccelBeams.27.064403"),
    # seven authors: et al. (Table 2); the journal's full name -> Annex C
    ("A. Alpha, B. Beta, C. Gamma, D. Delta, E. Epsilon, Z. Zeta, and E. Eta, “Exotic beams”, "
     "Physical Review Letters, vol. 1, p. 013501, 1998.",
     "A. Alpha et al., “Exotic beams”, Phys. Rev. Lett., vol. 1, p. 013501, 1998."),
    ("S. Posen et al., “Advances in Nb$_3$Sn cavities”, Superconductor Science and Technology, "
     "vol. 34, no. 2, p. 025007, 2021.",
     "S. Posen et al., “Advances in Nb$_3$Sn cavities”, Supercond. Sci. Technol., vol. 34, "
     "no. 2, p. 025007, 2021."),
    # a typo in the journal's name; Annex C's own "App." is ISO 4's "Appl."
    ("A. Alpha, “Diamond detectors”, Physical Reveiw Letters, vol. 103, p. 103504, 2013.",
     "A. Alpha, “Diamond detectors”, Phys. Rev. Lett., vol. 103, p. 103504, 2013."),
    ("A. Alpha, “Diamond detectors”, Applied Physics Letters, vol. 103, p. 103504, 2013.",
     "A. Alpha, “Diamond detectors”, Appl. Phys. Lett., vol. 103, p. 103504, 2013."),
    # an arXiv web address: month and year from the identifier, its DOI
    ("C. Balazs et al., “A linear collider vision”, https://arxiv.org/pdf/2503.19983.",
     "C. Balazs et al., “A linear collider vision”, Mar. 2025. doi:10.48550/arXiv.2503.19983"),
    # a submitted paper names no journal
    ("G. D. Read, “Title of paper”, submitted to Phys. Rev. Lett.",
     "G. D. Read, “Title of paper”, submitted for publication."),
    # a talk: the conference's long name becomes its label
    ("A. Alpha, “A talk”, presented at the 6th International Particle Accelerator Conference, "
     "Richmond, VA, USA, May 2015, unpublished.",
     "A. Alpha, “A talk”, presented at IPAC’15, Richmond, VA, USA, May 2015, unpublished."),
    ("Julia Packages, BenchmarkTools.jl. [Online]. Available: "
     "https://juliapackages.com/p/benchmarktools",
     "Julia Packages, BenchmarkTools.jl, https://juliapackages.com/p/benchmarktools"),
    # a state written out; a report number without "Rep."
    ("J.F. Benesch, “Corrector concept for FFA arcs”, Jefferson Lab, Newport News, Virginia, "
     "USA, JLAB-TN-23-016, March 2023.",
     "J. F. Benesch, “Corrector concept for FFA arcs”, Jefferson Lab, Newport News, VA, USA, "
     "Rep. JLAB-TN-23-016, Mar. 2023."),
    # Cyrillic letters that look Latin ("РАС2003", "рр.")
    ("М. Р. Kelly et al., “Microphonics measurements”, in Proc. РАС2003, Portland, OR, USA, "
     "May 2003, рр. 1291-1293.",
     "M. P. Kelly et al., “Microphonics measurements”, in Proc. PAC’03, Portland, OR, USA, "
     "May 2003, pp. 1291-1293."),
    ("A. P. Shishlo, private communication, 2022.",
     "A. P. Shishlo, private communication, 2022."),
    ("A. Student, “Title of thesis”, PhD thesis, Michigan State University, East Lansing, MI, "
     "USA, 2020.",
     "A. Student, “Title of thesis”, Ph.D. thesis, Michigan State University, East Lansing, MI, "
     "USA, 2020."),
    # a book in physics style, details in brackets; a suffix; the edition
    ("H.P. Alpha and T.M. Beta, Jr., Principles of Beam-Driven Lasers (Springer Nature, Cham, "
     "Switzerland, 2024), 4th Edition.",
     "H. P. Alpha and T. M. Beta, Jr., Principles of Beam-Driven Lasers, 4th ed. Cham, "
     "Switzerland: Springer Nature, 2024."),
    # no title (the record would give it), journal block alone
    ("H.P. Alpha, P.J.M. van der Beta, D. Gamma, I.D. Delta, and P. Epsilon, New J. Phys. 19, "
     "023020 (2017).",
     "H. P. Alpha, P. J. M. van der Beta, D. Gamma, I. D. Delta, and P. Epsilon, New J. Phys., "
     "vol. 19, p. 023020, 2017."),
    ("A. Vettel, “Design study for a compact x-ray source”, Proc. IEEE 1995 Particle "
     "Accelerator Conference, Dallas, TX, USA, May 1995, pp. 183-185.",
     "A. Vettel, “Design study for a compact x-ray source”, in Proc. PAC’95, Dallas, TX, USA, "
     "May 1995, pp. 183-185."),
]


@pytest.mark.parametrize("raw,expected", REAL)
def test_real_references_come_out_in_the_layout(raw, expected):
    assert offline(raw).text == expected


def test_what_no_source_gave_is_named_and_never_invented():
    out = offline("A. Alpha, “Title of a paper”, in Proc. IPAC’23.")
    assert out.text == "A. Alpha, “Title of a paper”, in Proc. IPAC’23, 2023."
    assert out.missing == ["city", "country", "month", "pages"]
    assert any(p.code == "REF-MISSING" and p.field == "pages" for p in out.problems)


def test_what_the_layout_has_no_room_for_is_dropped_and_named():
    out = offline("A. Vettel, “Design study”, Proc. IEEE 1995 Particle Accelerator Conference, "
                  "Dallas, TX, USA, May 1995, Vol. 183, IEEE Cat. No. 95CH35843, pp. 1-3.")
    assert "183" not in out.text
    assert "volume “183”" in out.dropped and "IEEE Cat. No. 95CH35843" in out.dropped


def test_a_doi_in_any_form_is_written_doi_and_last():
    for written in ("doi: 10.1063/1.345708", "https://doi.org/10.1063/1.345708",
                    "DOI:10.1063/1.345708.", "https://doi:10.1063/1.345708"):
        out = offline(f"A. Alpha, “Diamond”, Phys. Rev. Lett., vol. 67, p. 983, 1990. {written}")
        assert out.text.endswith("1990. doi:10.1063/1.345708"), written


# ---------------------------------------------------------------------------
# Completing from the registries (faked)
# ---------------------------------------------------------------------------

def fake_registries(monkeypatch, *, refdb=None, crossref=None, datacite=None):
    refdb = refdb or []
    crossref = {k.lower(): v for k, v in (crossref or {}).items()}
    datacite = {k.lower(): v for k, v in (datacite or {}).items()}

    def get(url, params=None, service="crossref"):
        if url == "https://refs.jacow.org/internal/text":
            return 200, {"query": refdb}
        if url.startswith("https://api.crossref.org/works/"):
            item = crossref.get(url.split("/works/", 1)[1].lower())
            return (200, {"message": item}) if item else (404, None)
        if url == "https://api.crossref.org/works":
            return 200, {"message": {"items": list(crossref.values())}}
        if url.startswith("https://api.datacite.org/dois/"):
            item = datacite.get(url.split("/dois/", 1)[1].lower())
            return (200, {"data": item}) if item else (404, None)
        if url.startswith("https://api.datacite.org/dois"):
            return 200, {"data": []}
        if url.startswith("https://doi.org/api/handles/"):
            return 404, None
        raise AssertionError(url)

    monkeypatch.setattr(registry, "_get", get)


IBIC = {"id": 96292, "doi": "10.18429/JACoW-IBIC2020-TUPP37",
        "name": "I. Mateu, M. Alpha, and B. Beta, \u201cA Beam Profile Monitor for High Energy "
                "Proton Beams Using Microfabrication Techniques\u201d, in <em>Proc. 9th Int. Beam "
                "Instrumentation Conf. (IBIC'20)</em>, Santos, Brazil, Sep. 2020, pp. 86-89."}


def test_a_jacow_paper_is_completed_from_refs_jacow_org(monkeypatch):
    fake_registries(monkeypatch, refdb=[IBIC], datacite={
        "10.18429/JACoW-IBIC2020-TUPP37": {"attributes": {
            "doi": "10.18429/JACoW-IBIC2020-TUPP37",
            "titles": [{"title": "A Beam Profile Monitor for High Energy Proton Beams Using "
                                 "Microfabrication Techniques"}],
            "creators": [{"familyName": "Mateu"}], "publicationYear": 2020,
            "types": {"resourceTypeGeneral": "ConferencePaper"}}}})
    out = format_reference("I. Mateu et al., “A beam profile monitor for high energy proton beams "
                           "using microfabrication techniques”, IBIC 2020.", llm=False)
    assert out.text == ("I. Mateu, M. Alpha, and B. Beta, “A beam profile monitor for high "
                        "energy proton beams using microfabrication techniques”, in Proc. "
                        "IBIC’20, Santos, Brazil, Sep. 2020, pp. 86-89. "
                        "doi:10.18429/JACoW-IBIC2020-TUPP37")
    assert not out.missing
    assert "refs.jacow.org" in out.sources
    assert any("et al." in c and "refs.jacow.org" in c for c in out.changes)


def test_a_record_that_itself_says_et_al_does_not_shorten_the_list(monkeypatch):
    record = dict(IBIC, name=IBIC["name"].replace("I. Mateu, M. Alpha, and B. Beta",
                                                  "I. Mateu et al."))
    fake_registries(monkeypatch, refdb=[record])
    out = format_reference("I. Mateu et al., “A beam profile monitor for high energy proton beams "
                           "using microfabrication techniques”, in Proc. IBIC’20.", llm=False)
    assert out.text.startswith("I. Mateu et al., “A beam profile")


def test_a_venue_comes_from_the_jacow_conference_list(monkeypatch):
    fake_registries(monkeypatch)
    monkeypatch.setattr(conferences, "venue", lambda label: {
        "city": "Venice", "country": "Italy", "month": "May"} if label.text == "IPAC’23" else {})
    out = format_reference("A. Alpha, “Title of a paper”, in Proc. IPAC’23, pp. 1-4.", llm=False)
    assert out.text == "A. Alpha, “Title of a paper”, in Proc. IPAC’23, Venice, Italy, May 2023, pp. 1-4."
    assert any("JACoW conference list" in c for c in out.changes)


PRL = {"DOI": "10.1103/physrevlett.114.050511", "type": "journal-article",
       "title": ["Title of paper published in journal"],
       "author": [{"family": "Alpha", "given": "Andrew"}, {"family": "Beta", "given": "Bob T."}],
       "issued": {"date-parts": [[2014, 2]]}, "container-title": ["Physical Review Letters"],
       "short-container-title": ["Phys. Rev. Lett."], "volume": "114", "issue": "5",
       "article-number": "050511",
       "resource": {"primary": {"URL": "https://link.aps.org/doi/10.1103/PhysRevLett.114.050511"}}}


def test_a_journal_article_is_completed_from_its_dois_record(monkeypatch):
    fake_registries(monkeypatch, crossref={"10.1103/physrevlett.114.050511": PRL})
    out = format_reference("A. Alpha et al., “Title of paper published in journal”, Physical "
                           "Review Letters, 2014. doi:10.1103/physrevlett.114.050511", llm=False)
    assert out.text == ("A. Alpha and B. T. Beta, “Title of paper published in journal”, Phys. "
                        "Rev. Lett., vol. 114, p. 050511, 2014. "
                        "doi:10.1103/PhysRevLett.114.050511")


def test_a_missing_title_is_taken_from_the_dois_record(monkeypatch):
    fake_registries(monkeypatch, crossref={"10.1103/physrevlett.114.050511": PRL})
    out = format_reference("A. Alpha, Phys. Rev. Lett. 114, 050511 (2014). "
                           "doi:10.1103/PhysRevLett.114.050511", llm=False)
    assert "“Title of paper published in journal”" in out.text
    assert any(c.startswith("title added from Crossref") for c in out.changes)


def test_a_journal_not_in_annex_c_is_abbreviated_with_abbreviso(monkeypatch):
    monkeypatch.setattr(journals, "_fetch_text", lambda url, service: (
        "J. Phys. D: Appl. Phys." if "abbreviso" in url else None))
    assert journals.abbreviate("Journal of Physics D: Applied Physics") == \
        ("J. Phys. D: Appl. Phys.", "abbrevIso", "")
    # an abbreviation already written is never sent there (it would be garbled)
    assert journals.abbreviate("Prog. Theor. Exp. Phys.")[0] == "Prog. Theor. Exp. Phys."


# ---------------------------------------------------------------------------
# The local model reads; it never writes
# ---------------------------------------------------------------------------

UNREADABLE = ("Smith John and Doe Jane. Beam halo studies; Particle Accelerators "
              "vol 12 p 45-50 (1983)")


def test_the_model_reads_a_reference_the_rules_cannot(monkeypatch):
    from src.llm import client
    monkeypatch.setattr(client, "is_enabled", lambda: True)
    answer = {"kind": "journal", "authors": "Smith John and Doe Jane",
              "title": "Beam halo studies", "journal": "Particle Accelerators", "volume": "12",
              "pages": "45-50", "year": "1983"}
    monkeypatch.setattr(client, "chat", lambda *a, **k: json.dumps(answer))
    out = format_reference(UNREADABLE, lookups=False, llm=True)
    assert out.parsed_by == "model"
    assert out.category == "journal"
    assert "“Beam halo studies”" in out.text and "vol. 12" in out.text and "pp. 45-50" in out.text


def test_a_model_answer_that_is_not_in_the_reference_is_refused(monkeypatch):
    from src.llm import client
    monkeypatch.setattr(client, "is_enabled", lambda: True)
    asked = []

    def chat(system, user, **kw):
        asked.append(user)
        return json.dumps({"kind": "journal", "title": "Beam Halo Studies at CERN",
                           "journal": "Particle Accelerators"})
    monkeypatch.setattr(client, "chat", chat)
    out = format_reference(UNREADABLE, lookups=False, llm=True)
    assert len(asked) == 2 and "is not in the reference" in asked[1]
    assert out.parsed_by == "rules"


# ---------------------------------------------------------------------------
# The paths that use it
# ---------------------------------------------------------------------------

def test_screen_reference_offers_the_layout_as_the_editors_decision():
    result = references.screen_reference(
        "Zampetakis, M., Antoniou, F., “Interplay of space charge”, Phys. Rev. Accel. Beams 27, "
        "064403, Mar. 2024. doi:10.1103/PhysRevAccelBeams.27.064403", label="Reference [2]",
        offline=True)
    assert result.tier is Tier.SUGGEST
    assert result.after.startswith("M. Zampetakis and F. Antoniou, “Interplay")
    assert result.latex.startswith("M.~Zampetakis and F.~Antoniou")
    assert result.message.startswith("Reference [2]: Rewritten in Appendix B's periodical "
                                     "layout: authors as initials and family name")
    assert result.category == "journal"


def test_a_reference_already_in_the_layout_is_left_alone():
    result = references.screen_reference(EXAMPLES[0][1], offline=True)
    assert result.after is None and result.tier is None


def test_an_engine_failure_leaves_the_reference_as_written(monkeypatch):
    import src.annexb as annexb
    monkeypatch.setattr(annexb, "format_reference", lambda *a, **k: 1 / 0)
    result = references.screen_reference("A. Alpha, “T”, 2020.", offline=True)
    assert result.after is None
    assert result.findings[0].check_id == "FMT-REF-03" and "NOT CHECKED" in result.findings[0].message


def test_a_bibitem_gets_the_latex_layout(tmp_path):
    from src.autofix.reference_edits import bibitem_rewrite_edits
    from src.parser.latex_parser import parse_latex
    tex = tmp_path / "p.tex"
    tex.write_text("\\documentclass{jacow}\\begin{document}Text~\\cite{a}.\n"
                   "\\begin{thebibliography}{9}\n\\bibitem{a}\nZampetakis, M., Antoniou, F., "
                   "``Interplay of space charge'', \\textit{Phys. Rev. Accel. Beams} 27, 064403, "
                   "Mar. 2024.\n\\end{thebibliography}\n\\end{document}\n", encoding="utf-8")
    paper = parse_latex(tex)
    edits, _ = bibitem_rewrite_edits(tex.read_text(encoding="utf-8"), paper, offline=True)
    assert len(edits) == 1
    assert edits[0].after.strip() == ("M.~Zampetakis and F.~Antoniou, “Interplay of space "
                                      "charge”, \\emph{Phys. Rev. Accel. Beams}, vol.~27, "
                                      "p.~064403, Mar. 2024.")


# ---------------------------------------------------------------------------
# BibTeX: the fields jacow.bbx needs to print Appendix B's layout
# ---------------------------------------------------------------------------

from src.annexb import bib  # noqa: E402

MESSY_BIB = r"""@inproceedings{conf,
  author    = {Alpha, A. and Beta, B. T.},
  title     = {An Overview of Modern Control Systems at {CERN}},
  booktitle = {Proceedings of the 19th Int. Conf. on Accelerator and Large Experimental Physics Control Systems (ICALEPCS 2023)},
  address   = {Cape Town, South Africa},
  month     = oct,
  year      = {2023},
  volume    = {19},
  pages     = {57-59},
  doi       = {10.18429/JACoW-ICALEPCS2023-PAPERID}
}
@article{jour,
  author  = {Alpha, A. and Beta, B.},
  title   = {Title of paper published in journal},
  journal = {Physical Review Letters},
  shortjournal = {PRL},
  volume  = {114},
  number  = {5},
  pages   = {050511},
  year    = {2014},
  doi     = {10.1103/PhysRevLett.114.050511}
}
@misc{arx,
  author  = {Alpha, A.},
  title   = {Title of arXiv preprint},
  journal = {arXiv preprint arXiv:2501.10602},
  year    = {2025}
}
@misc{web,
  title = {EPICS},
  url   = {https://www.epics-controls.org},
  year  = {2024}
}
@book{book,
  author    = {Alpha, A.},
  title     = {Title of Book},
  edition   = {2nd},
  publisher = {MIT Press},
  address   = {Cambridge, MA, USA},
  year      = {1986}
}
"""


def test_bib_entries_are_set_for_jacow_bbx():
    results = {r.key: r for r in bib.check_entries(MESSY_BIB, lookups=False, llm=False)}
    conf = results["conf"].after
    assert "booktitle = {Proc. ICALEPCS'23}" in conf
    assert "venue = {Cape Town, South Africa}" in conf and "eventdate = {2023-10}" in conf
    assert "volume" not in conf and "pages     = {57--59}" not in conf and "57--59" in conf
    # jacow.bbx sentence-cases it to exactly the right title, so the title is left alone
    assert "title     = {An Overview of Modern Control Systems at {CERN}}" in conf
    assert results["conf"].expected == (
        "A. Alpha and B. T. Beta, “An overview of modern control systems at CERN”, in Proc. "
        "ICALEPCS’23, Cape Town, South Africa, Oct. 2023, pp. 57-59. "
        "doi:10.18429/JACoW-ICALEPCS2023-PAPERID")
    jour = results["jour"].after
    assert "journal = {Phys. Rev. Lett.}" in jour and "shortjournal" not in jour
    arx = results["arx"].after
    assert arx.startswith("@article{arx,") and "journal" not in arx
    assert "date = {2025-01}" in arx and "doi = {10.48550/arXiv.2501.10602}" in arx
    web = results["web"].after
    assert web.startswith("@online{web,") and "title = {{EPICS}}" in web and "year" not in web
    book = results["book"].after
    assert "title = {{Title of Book}}" in book and "titleaddon = {2nd ed.}" in book


def test_an_entry_already_right_is_left_alone():
    right = (r"@article{jour, author={Alpha, A. and Beta, B.}, title={Title of paper}, "
             r"journal={Phys. Rev. Lett.}, volume={114}, number={5}, pages={050511}, "
             r"year={2014}, doi={10.1103/PhysRevLett.114.050511}}")
    edits, _ = bib.bib_edits(right, "refs.bib", lookups=False, llm=False)
    assert edits == []


def test_braces_keep_exactly_the_capitals_sentence_case_must_keep():
    title = "Beam studies at the Oak Ridge National Laboratory with SwissFEL and Nb$_3$Sn"
    braced = bib.braced_title(title)
    assert "{Oak Ridge National Laboratory}" in braced and "{SwissFEL}" in braced
    assert bib.make_sentence_case(braced) == title


def test_the_bib_path_prints_appendix_b_with_the_jacow_class():
    fixed = "\n".join(r.after for r in bib.check_entries(MESSY_BIB, lookups=False, llm=False))
    printed = bib.render_with_jacow(fixed)
    if printed is None:
        pytest.skip("TeX, biber or pdftotext not available")
    results = {r.key: r for r in bib.check_entries(fixed, lookups=False, llm=False)}

    def canon(t):
        return re.sub(r"\s+", "", t.replace("–", "-").replace("’", "'"))
    for key in ("conf", "jour", "arx", "web", "book"):
        assert canon(printed[key]) == canon(results[key].expected), key
