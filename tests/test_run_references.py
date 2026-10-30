"""References from an October 2026 test run, offline.

Each was either rejected or left unconfirmed in that run.  Offline, the
formatting must now pass the damage check; finding the title-less ones in
Crossref is tested in the formatter with simulated answers.
"""
from __future__ import annotations

import pytest

from src import references
from src.edits import Tier

TEST_RUN = {
    1: "Arno Vettel, Design study for a compact x-ray source driven by the SLAC linac, "
       "Proc. IEEE 1995 Particle Accelerator Conference, Vol. 183, IEEE Cat. No. 95CH35843 (1995).",
    2: "H.P. Alpha, P.J.M. van der Beta, D. Gamma, I.D. Delta, and P. Epsilon, New J. Phys. 19, "
       "023020 (2017).",
    4: "P. Delta et al., Nat. Photon. 7, 123 (2013).",
    8: "H.P. Alpha and T.M. Beta, Jr., Principles of Beam-Driven Lasers (Springer Nature, "
       "Cham, Switzerland, 2024), 4th Edition, Chap. 12.",
}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("HOUSE_STYLE", "jacow")
    references._agents.clear()


def test_ieee_era_proceedings_is_offered():
    result = references.screen_reference(TEST_RUN[1], offline=True)
    assert result.after and "in Proc. PAC’95" in result.after and "vol. 183" in result.after
    assert result.tier is Tier.SUGGEST


def test_book_keeps_edition_and_chapter():
    result = references.screen_reference(TEST_RUN[8], offline=True)
    assert result.after == ("H. P. Alpha and T. M. Beta, Jr., Principles of Beam-Driven "
                            "Lasers, 4th ed. Cham, Switzerland: Springer Nature, 2024, ch. 12.")


def test_spaced_initials_and_journal_forms():
    assert references.screen_reference(TEST_RUN[2], offline=True).after.startswith(
        "H. P. Alpha, P. J. M. van der Beta,")
    assert "Nat. Photonics" in references.screen_reference(TEST_RUN[4], offline=True).after
