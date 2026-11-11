"""Per-conference house style.

The Style Guide leaves some presentation choices open, and conferences have
settled them differently — measured on finished conferences, NAPAC2025's
editors wrote measurements as ``\\qty{}`` (270 to 27) and HIAT2025's as ``~``
(43 to 6).  One profile per conference holds those choices, so a check
confirmed on one conference is not contradicted by the next.

Choose a profile with ``HOUSE_STYLE`` in ``.env`` and override any single
setting with the variables below:

==========================  ====================  ===========================
Setting                     Variable              Values
==========================  ====================  ===========================
units in LaTeX              HOUSE_STYLE_UNITS     ``auto`` (``\\qty`` when
                                                  siunitx is loaded), ``qty``,
                                                  ``tilde``
page ranges                 HOUSE_STYLE_PAGE_DASH ``hyphen`` (pp. 57-59) or
                                                  ``endash`` (pp. 57–59)
conference label            HOUSE_STYLE_APOSTROPHE ``straight`` (IPAC'23) or
                                                  ``typographic`` (IPAC’23)
Applied Physics journals    HOUSE_STYLE_APPLIED   ``App.`` (Annex C) or
                                                  ``Appl.`` (ISO 4)
==========================  ====================  ===========================

References follow one standard everywhere (Annex B); how strictly it is
applied is each editor's decision, made card by card at the desk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class HouseStyle:
    name: str
    units: str = "auto"                 # auto | qty | tilde
    page_range_dash: str = "-"          # "-" or "\u2013"
    label_apostrophe: str = "\u2019"    # "'" or "\u2019"
    applied_physics: str = "App."       # "App." (Annex C) or "Appl." (ISO 4)
    curly_quotes: bool = True


# "jacow" follows the Style Guide's own examples: "pp. 57-59", "IPAC’23",
# Annex C's "App. Phys. Lett.".
PROFILES: dict[str, HouseStyle] = {
    "jacow": HouseStyle("jacow"),
    "napac": HouseStyle("napac", units="qty"),
    "hiat": HouseStyle("hiat", units="tilde"),
    "iso4": HouseStyle("iso4", page_range_dash="\u2013", label_apostrophe="'",
                       applied_physics="Appl."),
}

_DASHES = {"hyphen": "-", "-": "-", "endash": "\u2013", "\u2013": "\u2013"}
_APOSTROPHES = {"straight": "'", "'": "'", "typographic": "\u2019", "\u2019": "\u2019"}


def load_house_style() -> HouseStyle:
    """The profile named by ``HOUSE_STYLE`` (default ``jacow``) plus overrides."""
    name = os.getenv("HOUSE_STYLE", "jacow").strip().lower() or "jacow"
    style = PROFILES.get(name, PROFILES["jacow"])
    units = os.getenv("HOUSE_STYLE_UNITS", "").strip().lower()
    if units in ("auto", "qty", "tilde"):
        style = replace(style, units=units)
    dash = _DASHES.get(os.getenv("HOUSE_STYLE_PAGE_DASH", "").strip().lower())
    if dash:
        style = replace(style, page_range_dash=dash)
    apostrophe = _APOSTROPHES.get(os.getenv("HOUSE_STYLE_APOSTROPHE", "").strip().lower())
    if apostrophe:
        style = replace(style, label_apostrophe=apostrophe)
    applied = os.getenv("HOUSE_STYLE_APPLIED", "").strip()
    if applied in ("App.", "Appl."):
        style = replace(style, applied_physics=applied)
    return style
