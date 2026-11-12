"""Countries, US states and Canadian provinces, as JACoW writes them ("Menlo Park, CA, USA")."""

from __future__ import annotations

import re

_COUNTRIES = """
Argentina Armenia Australia Austria Azerbaijan Bangladesh Belarus Belgium Brazil Bulgaria
Canada Chile China Colombia Croatia Cyprus Czechia Denmark Egypt Estonia Finland France
Georgia Germany Ghana Greece Hungary Iceland India Indonesia Iran Iraq Ireland Israel Italy
Japan Jordan Kazakhstan Kenya Latvia Lebanon Lithuania Luxembourg Malaysia Malta Mexico
Mongolia Montenegro Morocco Nepal Netherlands Nigeria Norway Pakistan Peru Philippines Poland
Portugal Qatar Romania Russia Serbia Singapore Slovakia Slovenia Spain Sweden Switzerland
Taiwan Thailand Tunisia Turkey Uganda Ukraine USA UK Uruguay Uzbekistan Venezuela Vietnam
"""

#: Written form -> JACoW's form.
COUNTRY: dict[str, str] = {c.lower(): c for c in _COUNTRIES.split()}
COUNTRY.update({
    "united states": "USA", "united states of america": "USA", "u.s.a.": "USA", "u.s.a": "USA",
    "us": "USA", "u.s.": "USA", "america": "USA",
    "united kingdom": "UK", "u.k.": "UK", "great britain": "UK", "england": "UK",
    "scotland": "UK", "wales": "UK", "northern ireland": "UK",
    "p.r. china": "China", "pr china": "China", "p. r. china": "China",
    "people's republic of china": "China", "prc": "China",
    "south korea": "South Korea", "korea": "Korea", "republic of korea": "South Korea",
    "czech republic": "Czech Republic", "the netherlands": "Netherlands",
    "south africa": "South Africa", "new zealand": "New Zealand", "saudi arabia": "Saudi Arabia",
    "united arab emirates": "UAE", "uae": "UAE", "sri lanka": "Sri Lanka",
    "costa rica": "Costa Rica", "bosnia and herzegovina": "Bosnia and Herzegovina",
    "north macedonia": "North Macedonia", "hong kong": "Hong Kong",
    "russian federation": "Russia", "türkiye": "Turkey",
})

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI",
    "wyoming": "WY", "district of columbia": "DC",
}
CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "québec": "QC", "saskatchewan": "SK",
}
STATE_CODES = set(US_STATES.values()) | set(CA_PROVINCES.values())


def country(text: str) -> str:
    """JACoW's form of a country name, or "" if *text* is not one."""
    key = re.sub(r"\s+", " ", text.strip(" .,;()")).lower()
    key = re.sub(r"^the ", "", key) if key not in COUNTRY else key
    return COUNTRY.get(key, "")


def state(text: str, in_country: str = "") -> str:
    """A US state or Canadian province as its two-letter code, or ""."""
    t = text.strip(" .,;()")
    if t.upper() in STATE_CODES and len(t) == 2 and t.isupper():
        return t.upper()
    key = t.lower()
    if in_country in ("", "USA") and key in US_STATES:
        return US_STATES[key]
    if in_country in ("", "Canada") and key in CA_PROVINCES:
        return CA_PROVINCES[key]
    return ""


__all__ = ["country", "state", "COUNTRY", "US_STATES", "CA_PROVINCES", "STATE_CODES"]


#: Laboratories and universities that appear in accelerator references, and where they are
#: (Appendix B: the institution's city and country; a US or Canadian state as its code).
#: A lab does not move, so its place is a fact; matched on the institution as written.
INSTITUTIONS: tuple[tuple[str, tuple[str, str, str]], ...] = (
    (r"\bCERN\b", ("Geneva", "", "Switzerland")),
    (r"\bSLAC\b|Stanford Linear Accelerator", ("Menlo Park", "CA", "USA")),
    (r"\bFermilab\b|\bFNAL\b|Fermi National Accelerator", ("Batavia", "IL", "USA")),
    (r"\bBNL\b|Brookhaven", ("Upton", "NY", "USA")),
    (r"\bANL\b|Argonne", ("Lemont", "IL", "USA")),
    (r"\bLBNL\b|Lawrence Berkeley|\bLBL\b", ("Berkeley", "CA", "USA")),
    (r"\bLLNL\b|Lawrence Livermore", ("Livermore", "CA", "USA")),
    (r"\bLANL\b|Los Alamos", ("Los Alamos", "NM", "USA")),
    (r"\bORNL\b|Oak Ridge National", ("Oak Ridge", "TN", "USA")),
    (r"\bSNS\b|Spallation Neutron Source", ("Oak Ridge", "TN", "USA")),
    (r"\bJLab\b|Jefferson Lab|Thomas Jefferson National|\bTJNAF\b", ("Newport News", "VA", "USA")),
    (r"\bFRIB\b|Facility for Rare Isotope Beams|\bNSCL\b", ("East Lansing", "MI", "USA")),
    (r"Michigan State University", ("East Lansing", "MI", "USA")),
    (r"\bSNL\b|Sandia National", ("Albuquerque", "NM", "USA")),
    (r"\bPNNL\b|Pacific Northwest National", ("Richland", "WA", "USA")),
    (r"\bINL\b|Idaho National Laboratory", ("Idaho Falls", "ID", "USA")),
    (r"Cornell University|\bCLASSE\b|\bCHESS\b", ("Ithaca", "NY", "USA")),
    (r"\bTRIUMF\b", ("Vancouver", "BC", "Canada")),
    (r"Canadian Light Source", ("Saskatoon", "SK", "Canada")),
    (r"\bDESY\b|Deutsches Elektronen-Synchrotron", ("Hamburg", "", "Germany")),
    (r"European XFEL", ("Schenefeld", "", "Germany")),
    (r"\bGSI\b|Helmholtzzentrum für Schwerionenforschung", ("Darmstadt", "", "Germany")),
    (r"\bHZB\b|Helmholtz-Zentrum Berlin", ("Berlin", "", "Germany")),
    (r"\bHZDR\b|Helmholtz-Zentrum Dresden", ("Dresden", "", "Germany")),
    (r"\bKIT\b|Karlsruhe Institute of Technology|Karlsruher Institut", ("Karlsruhe", "", "Germany")),
    (r"\bPSI\b|Paul Scherrer", ("Villigen", "", "Switzerland")),
    (r"\bESRF\b", ("Grenoble", "", "France")),
    (r"\bILL\b|Institut Laue-Langevin", ("Grenoble", "", "France")),
    (r"\bGANIL\b", ("Caen", "", "France")),
    (r"Synchrotron SOLEIL|\bSOLEIL\b", ("Saint-Aubin", "", "France")),
    (r"\bCEA\b.*Saclay|\bIRFU\b", ("Gif-sur-Yvette", "", "France")),
    (r"\bIJCLab\b|\bLAL\b.*Orsay", ("Orsay", "", "France")),
    (r"\bESS\b|European Spallation Source", ("Lund", "", "Sweden")),
    (r"MAX IV", ("Lund", "", "Sweden")),
    (r"Elettra", ("Trieste", "", "Italy")),
    (r"\bINFN\b.*Frascati|\bLNF\b", ("Frascati", "", "Italy")),
    (r"\bINFN\b.*Legnaro|\bLNL\b", ("Legnaro", "", "Italy")),
    (r"Diamond Light Source", ("Didcot", "", "UK")),
    (r"\bSTFC\b|Rutherford Appleton|\bRAL\b|\bISIS\b", ("Didcot", "", "UK")),
    (r"Daresbury|Cockcroft Institute", ("Daresbury", "", "UK")),
    (r"\bKEK\b|High Energy Accelerator Research Organization", ("Tsukuba", "", "Japan")),
    (r"J-PARC|\bJAEA\b", ("Tokai", "", "Japan")),
    (r"\bRIKEN\b", ("Wako", "", "Japan")),
    (r"SPring-8|\bJASRI\b", ("Sayo", "", "Japan")),
    (r"\bPAL\b|Pohang Accelerator", ("Pohang", "", "South Korea")),
    (r"\bIHEP\b|Institute of High Energy Physics", ("Beijing", "", "China")),
    (r"\bSSRF\b|\bSARI\b|\bSINAP\b|Shanghai Advanced Research", ("Shanghai", "", "China")),
    (r"\bIMP\b|Institute of Modern Physics", ("Lanzhou", "", "China")),
    (r"\bNSRRC\b", ("Hsinchu", "", "Taiwan")),
    (r"\bBINP\b|Budker Institute", ("Novosibirsk", "", "Russia")),
    (r"\bJINR\b|Joint Institute for Nuclear Research", ("Dubna", "", "Russia")),
    (r"\bANSTO\b|Australian Synchrotron", ("Clayton", "", "Australia")),
    (r"\bLNLS\b|Sirius|\bCNPEM\b", ("Campinas", "SP", "Brazil")),
    (r"\bSESAME\b", ("Allan", "", "Jordan")),
    (r"\bITER\b", ("Saint-Paul-lez-Durance", "", "France")),
)


def institution_place(name: str) -> tuple[str, str, str] | None:
    for pattern, place in INSTITUTIONS:
        if re.search(pattern, name or ""):
            return place
    return None
