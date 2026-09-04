"""Heuristic field extractor for plain-text reference strings.

Migrated from the v1.0.0 standalone formatter (sections 3 and 3a).
The orchestrator :func:`extract_from_raw` runs a sequence of
sub-extractors that each populate a subset of the rec dict, e.g.::

    raw = 'A. Smith, "T", in Proc. NAPAC\'16, Chicago, IL, USA, Oct. 2016, pp. 1-3. doi:10.x/y'
    rec = extract_from_raw(raw)
    # rec['doi'], rec['conference'], rec['city'], rec['country'],
    # rec['month'], rec['year'], rec['pages'] all populated

The sub-extractors are also exported individually so the autofix
pipeline can call e.g. :func:`extract_conference` on its own to
upgrade a body that already has authors + title but is missing
location / month / pages.

No external dependencies beyond :mod:`src.refs.text_utils` (for
``to_initials`` / ``pages_fmt`` / ``norm_month`` / ``clean_title``)
and the local ``journal_abbrev.normalize_journal``.  Pure functions,
no HTTP, no I/O.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from src.refs.text_utils import (
    clean_title,
    norm_month,
    pages_fmt,
    to_initials,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants used by sub-extractors
# ─────────────────────────────────────────────────────────────────────────────

# Short-name institutions that may be embedded at the end of a quoted
# title, e.g. "TRAVEL v4.06 User Manual, CERN, 2003" (malformatted but
# common).  Used by :func:`_extract_report_fields` to lift the
# institution out of the title and into the ``institution`` field.
TITLE_TAIL_INSTITUTIONS: frozenset = frozenset({
    # National labs / large facilities (accelerator community)
    "CERN", "SLAC", "DESY", "BNL", "FNAL", "ANL", "LBNL", "LANL", "ORNL",
    "KEK", "PSI", "ESS", "SNS", "JINR", "IHEP", "GSI", "RIKEN",
    "TRIUMF", "ANSTO", "NSRRC", "INFN", "STFC", "CEA", "FZJ", "CIEMAT",
    # Synchrotron light sources (the facility itself, not the machine inside it)
    "ESRF", "ALBA", "DIAMOND", "ELETTRA", "SOLEIL", "BESSY", "NSLS", "ALS",
    "HZB", "SLS",
})

# Recognised publishers — used by :func:`_extract_book_fields` to lift
# the publisher name out of the body when it's listed inline.  Duplicates
# the table in the standalone but kept here for self-containment.
_KNOWN_PUBLISHERS: tuple = (
    "Springer", "Wiley", "Elsevier", "CRC Press", "Taylor & Francis",
    "Cambridge University Press", "Oxford University Press", "MIT Press",
    "World Scientific", "IOP Publishing", "AIP Publishing",
    "IEEE Press", "McGraw-Hill", "Pergamon", "Academic Press",
    "Kluwer", "Birkhauser", "De Gruyter", "Routledge",
)

# Proper-noun blocklist for the no-quote title parser.  When the parser
# sees one of these as the first token of a chunk, it bails out because
# the chunk is almost certainly a venue/institution name, not a paper
# title — preventing e.g. "CERN" from being treated as a one-word title.
_NQ_PROPER_NOUN_BLOCKLIST: frozenset = frozenset({
    "CERN", "Stanford", "MIT", "DESY", "KEK", "SLAC", "Fermilab", "BNL",
    "ANL", "LBNL", "LANL", "ORNL", "PSI", "ESRF", "NSLS", "APS", "Spring",
    "Diamond", "ALBA", "Elettra", "BESSY", "HZB", "GSI", "FAIR", "RIKEN",
    "IHEP", "BINP", "JINR", "TRIUMF", "ATNF", "ANSTO", "Oxford", "Cambridge",
    "Harvard", "Caltech", "Cornell", "Berkeley", "Princeton", "Tokyo",
    "Kyoto", "Beijing", "Tsinghua",
    "Geneva", "Hamburg", "Darmstadt", "Villigen", "Saclay", "Grenoble",
    "Trieste", "Barcelona", "Valencia", "Batavia", "Upton", "Argonne",
    "Chicago", "Vancouver", "Sydney", "Melbourne", "Shanghai", "Wuhan",
    "Moscow", "Novosibirsk", "Zurich", "Vienna", "Prague", "Venice",
    "Copenhagen", "Stockholm", "Helsinki", "Seoul", "Tsukuba", "Pohang",
    "Novel", "New", "Design", "Development", "Study", "Analysis",
    "Simulation", "Measurement", "Status", "Performance", "Upgrade",
    "Beam", "Lattice", "Optics", "Linac", "Synchrotron", "Storage",
    "Free", "Compact", "High", "Low", "Ultra", "Super", "Advanced",
    "Experimental", "Theoretical", "Numerical", "Preliminary",
    "Commissioning", "Operation", "Diagnostics", "Controls", "Results",
    "Progress", "Overview", "Review", "Introduction", "Summary",
})

# Sentinel used by the no-quote title parser so it can split on "and"
# without losing the "and" in the join step.
_NQ_SENTINEL = "|||AND|||"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: identifier extractor
# ─────────────────────────────────────────────────────────────────────────────

def _extract_identifiers(raw: str, rec: dict) -> None:
    """Populate DOI, arXiv, URL, accessed date, and ISBN from *raw*.

    Mutates *rec* in place.  Idempotent — sub-extractors below may run
    after this one without overwriting the values it sets.

    Recognised patterns
    -------------------
    - DOI: ``doi:10.xxxx/...`` / ``https://doi.org/10.xxxx/...`` / bare ``10.xxxx/...``
    - JACoW DOI: ``10.18429/JACoW-CONF2023-PAPERID`` → conf / year / paper_id
    - arXiv: ``arXiv:XXXX.YYYYY`` and the category tag ``[cs.LG]``
    - URL: any ``http(s)://...`` not already a doi.org link
    - Accessed date: ``accessed: <date>`` / ``retrieved: <date>``
    - ISBN: ``ISBN: 978-...`` or bare ``ISBN 978...``
    """
    m = re.search(r"(?:doi\.org/|doi[:\s]+)(10\.\d{4,}/\S+)", raw, re.IGNORECASE)
    if m:
        rec["doi"] = _clean_doi(m.group(1))
    else:
        m = re.search(r"\b(10\.\d{4,}/\S+)", raw)
        if m:
            rec["doi"] = _clean_doi(m.group(1))

    # arXiv canonical DOI for an arXiv ID, when we have the DOI but no arxiv_id
    if rec.get("doi") and not rec.get("arxiv_id"):
        m = re.match(
            r"^10\.48550/arXiv\.(\d{4}\.\d{4,5})$",
            rec["doi"], re.IGNORECASE,
        )
        if m:
            rec["arxiv_id"] = m.group(1)

    # JACoW DOI prefix: 10.18429/JACoW-CONF2023-PAPERID
    if rec.get("doi") and not rec.get("conference"):
        jm = re.match(
            r"^10\.18429/JACoW-([A-Za-z]+)(\d{4})-([A-Z0-9]+)$",
            rec["doi"], re.IGNORECASE,
        )
        if jm:
            rec["conference"] = jm.group(1).upper()
            if not rec.get("year"):
                rec["year"] = jm.group(2)
            if not rec.get("paper_id"):
                rec["paper_id"] = jm.group(3).upper()

    m = re.search(r"arXiv[:\s]*(\d{4}\.\d{4,5})", raw, re.IGNORECASE)
    if m:
        rec["arxiv_id"] = m.group(1)
    m = re.search(r"arXiv:\d{4}\.\d+\s*\[([^\]]+)\]", raw, re.IGNORECASE)
    if m:
        rec["arxiv_cat"] = m.group(1)

    m = re.search(r"https?://(?!doi\.org)\S+", raw)
    if m:
        rec["url"] = m.group(0).rstrip(".,)>]")
    m = re.search(
        r"(?:accessed|retrieved)[:\s]+"
        r"(\d{1,2}[- ]?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[.,-]?\s*\d{4}|\d{4})",
        raw, re.IGNORECASE,
    )
    if m:
        rec["accessed"] = m.group(1).strip()

    isbn_m = re.search(
        r"\bISBN[:\s-]*"
        r"((?:97[89][- ]?)?\d[- ]?\d[- ]?\d[- ]?\d[- ]?\d[- ]?\d[- ]?\d"
        r"[- ]?\d[- ]?\d[- ]?[\dX])",
        raw, re.IGNORECASE,
    )
    if isbn_m:
        rec["isbn"] = re.sub(r"[- ]", "", isbn_m.group(1))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: bibliographic extractor
# ─────────────────────────────────────────────────────────────────────────────

def _extract_bibliographic(raw: str, rec: dict) -> None:
    """Populate pages, volume, issue, year, and month from *raw*.

    Year is set as a *fallback* — :func:`_extract_conference` overrides
    it when a conference pattern provides a more specific year.
    """
    m = re.search(r"pp\.\s*(\d+\s*[-–]\s*\d+)", raw)
    if not m:
        m = re.search(r"(?:,\s*|^|\s)p\.\s*(\d+(?:\s*[-–]\s*\d+)?)", raw)
    if m:
        rec["pages"] = pages_fmt(m.group(1))

    m = re.search(r"\bvol\.\s*(\d+)", raw, re.IGNORECASE)
    if m:
        rec["volume"] = m.group(1)
    m = re.search(r"\bno\.\s*(\d+)", raw, re.IGNORECASE)
    if m:
        rec["issue"] = m.group(1)

    # Year: prefer (YYYY) at end, then any 4-digit year.
    paren_m = re.search(r"\((19[5-9]\d|20\d\d)\)\s*\.?\s*$", raw)
    if paren_m:
        rec["year"] = paren_m.group(1)
    else:
        m = re.search(r"\b(19[5-9]\d|20\d\d)\b", raw)
        if m:
            rec["year"] = m.group(1)

    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
        r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
        r"|Dec(?:ember)?)\.?[\s,]",
        raw, re.IGNORECASE,
    )
    if m:
        rec["month"] = norm_month(m.group(1))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: title / authors extractor
# ─────────────────────────────────────────────────────────────────────────────

def _extract_title_authors(raw: str, rec: dict) -> None:
    """Populate title and authors from *raw*.

    Handles three input styles:

    1. Quoted-title style:  ``Authors, "Title", venue, year.``
    2. Nature-style no-quote:  ``Family, I., Family, I. & Family, I.T.
       Title sentence. Journal Vol, Pages (Year).``
    3. Plain no-quote fallback:  ``Authors. Title. Venue, year.``

    Strategy
    --------
    - If the text contains a quoted title, lift it directly.
    - Otherwise, try the Nature-style parser first (most common in
      Nature/Springer/IEEE journals).  If it returns a title, use it.
    - Otherwise, fall back to the chunked no-quote parser.
    """
    open_q = re.search(r'["“«]', raw)
    if open_q:
        m = re.search(r'["“«](.*?)["”»]', raw, re.DOTALL)
        if m:
            rec["title"] = m.group(1).strip()
        if open_q.start() > 1:
            ar = re.sub(r"^\s*(?:\[\d+\]\.?\s*|\d+\.\s*)", "", raw[: open_q.start()])
            rec["authors_raw"] = ar.rstrip(", ").strip()
        return

    # No quoted title.  Check for DOI-only or arXiv-only strings (these
    # have no authors/title, just an identifier).
    doi_only = bool(
        re.match(r"^(?:doi[:\s]+)?10\.\d{4,}/\S+$", raw.strip(), re.IGNORECASE)
        or re.match(r"^https?://doi\.org/10\.\d{4,}/\S+$", raw.strip(), re.IGNORECASE)
        or re.match(
            r"^arXiv:\d{4}\.\d{4,5}(?:\s*\[[^\]]+\])?$", raw.strip(), re.IGNORECASE
        )
    )
    if doi_only:
        return

    if not _try_parse_nature_style(raw, rec) or not rec.get("title"):
        nq_authors, nq_title, nq_hit = _extract_no_quote_title(raw)
        if nq_authors and not rec.get("authors_raw"):
            rec["authors_raw"] = nq_authors
        if nq_title and not rec.get("title"):
            rec["title"] = nq_title
        if nq_hit:
            rec["nq_blocklist_hit"] = True


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: conference extractor
# ─────────────────────────────────────────────────────────────────────────────

# Inline copy of the US/Canadian state set so this module stays
# self-contained.  See ``src.refs.conference_db._VENUE_STATE_PROVS``
# for the canonical list.  Used by Pattern 1 to disambiguate
# "City, State, Country" (3 tokens) from "City, Country" (2 tokens).
_VENUE_STATE_PROVS_INLINE: frozenset = frozenset({
    # US states
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
    # Canadian provinces
    "BC", "ON", "QC", "AB", "MB", "SK", "NS", "NB", "PE", "NL",
})


def _extract_conference(raw: str, rec: dict) -> None:
    """Populate conference, year, city, country, paper_id from in-proc patterns.

    Recognised patterns (5 of them):

    1. ``in Proc. ACRONYM2025, City, Country,`` (4-digit year, no space)
       — also handles the 3-token "City, State, Country" form for US/CA
       venues, e.g. ``Chicago, IL, USA,`` → city=Chicago, country=USA.
    2. ``in Proc. ACRONYM'25, City, Country,`` (2-digit year with apostrophe)
    3. ``in Proc. ACRONYM'25 City Country`` (no commas, tolerant)
    4. ``presented at ACRONYM2025/ACRONYM'25, City, Country,`` (unpublished)
    5. ``in <Spelled-out full name> (ACRONYM'YY), City, Country,``

    Also lifts ``paper XXXXX`` from the body.
    """
    # Pattern 1: in Proc. ACRONYM2025, [City, [State,] Country,]
    m = re.search(
        r"\bin\s+Proc\.?\s+([A-Z][A-Z0-9\-]+?)\s*((?:19|20)\d{2})"
        r"\s*,\s*([^,]+),\s*([^,]+)(?:,\s*([^,]+))?,",
        raw,
    )
    if m:
        acronym = m.group(1).rstrip().upper()
        year4 = m.group(2)
        raw_conf_segment = m.group(0)
        if re.search(r"[A-Z]\s+" + re.escape(year4), raw_conf_segment):
            rec["conference"] = f"{acronym} {year4}"
        else:
            rec["conference"] = f"{acronym}{year4}"
        rec["year"] = rec.get("year") or year4
        # Disambiguate City / State / Country:
        #   2-token: "Chicago, Italy"          → city=Chicago, country=Italy
        #   3-token: "Chicago, IL, USA"        → city=Chicago, country=USA
        #            "Champaign, IL"           → city=Champaign, country=IL
        #   (state detection: if the second-to-last token is a US/CA
        #   state/province abbreviation, it's a state and the country is
        #   the last token.)
        city = m.group(3).strip()
        second = m.group(4).strip()
        third = (m.group(5) or "").strip()
        if third and second in _VENUE_STATE_PROVS_INLINE:
            rec["city"] = city
            rec["country"] = third
        elif third:
            # 3-token but the second isn't a state — assume "City, Country, Extra"
            rec["city"] = city
            rec["country"] = second
        else:
            rec["city"] = city
            rec["country"] = second
    else:
        # Pattern 2: in Proc. ACRONYM'25, [City, [State,] Country,]
        m = re.search(
            r"\bin\s+Proc\.?\s+([A-Z][A-Z0-9\-]+)['’](\d{2})"
            r"\s*,?\s*([^,]+),\s*([^,]+)(?:,\s*([^,]+))?,",
            raw, re.IGNORECASE,
        )
        if m:
            rec["conference"] = m.group(1).upper()
            rec["year"] = rec.get("year") or "20" + m.group(2)
            city = m.group(3).strip()
            second = m.group(4).strip()
            third = (m.group(5) or "").strip()
            if third and second in _VENUE_STATE_PROVS_INLINE:
                rec["city"] = city
                rec["country"] = third
            elif third:
                rec["city"] = city
                rec["country"] = second
            else:
                rec["city"] = city
                rec["country"] = second

    # Pattern 2b: in Proc. ACRONYM'25 City Country (no commas)
    if not rec.get("conference"):
        m = re.search(
            r"\bin\s+Proc\.?\s+([A-Z][A-Z0-9\-]+)['’](\d{2})\s+"
            r"([A-Z][a-zA-Z]+)\s+([A-Z][a-zA-Z]+)",
            raw,
        )
        if m:
            rec["conference"] = m.group(1).upper()
            rec["year"] = rec.get("year") or "20" + m.group(2)
            rec["city"] = m.group(3).strip()
            rec["country"] = m.group(4).strip()

    # Pattern 3: presented at ACRONYM'YY (unpublished)
    # Handles 4-digit year, 2-digit apostrophe year, and 2- or 3-token
    # City[, State], Country.
    if not rec.get("conference"):
        m = re.search(
            r"presented\s+at\s+([A-Z][A-Z0-9\-]+?)\s*((?:19|20)\d{2})"
            r"\s*,\s*([^,]+),\s*([^,]+)(?:,\s*([^,]+))?,",
            raw,
        )
        if m:
            acronym = m.group(1).rstrip().upper()
            year4 = m.group(2)
            raw_seg = m.group(0)
            if re.search(r"[A-Z]\s+" + re.escape(year4), raw_seg):
                rec["conference"] = f"{acronym} {year4}"
            else:
                rec["conference"] = f"{acronym}{year4}"
            rec["year"] = rec.get("year") or year4
            city = m.group(3).strip()
            second = m.group(4).strip()
            third = (m.group(5) or "").strip()
            if third and second in _VENUE_STATE_PROVS_INLINE:
                rec["city"] = city
                rec["country"] = third
            elif third:
                rec["city"] = city
                rec["country"] = second
            else:
                rec["city"] = city
                rec["country"] = second
        else:
            m = re.search(
                r"presented\s+at\s+([A-Z][A-Z0-9\-]+)[’\'](\d{2})"
                r"\s*,\s*([^,]+),\s*([^,]+)(?:,\s*([^,]+))?,",
                raw, re.IGNORECASE,
            )
            if m:
                rec["conference"] = m.group(1).upper()
                rec["year"] = rec.get("year") or "20" + m.group(2)
                city = m.group(3).strip()
                second = m.group(4).strip()
                third = (m.group(5) or "").strip()
                if third and second in _VENUE_STATE_PROVS_INLINE:
                    rec["city"] = city
                    rec["country"] = third
                elif third:
                    rec["city"] = city
                    rec["country"] = second
                else:
                    rec["city"] = city
                    rec["country"] = second

# Pattern 4: in <Full Name> (ACRONYM, Year)
    if not rec.get("conference"):
        m = re.search(
            r"\bin\s+((?:\d+(?:st|nd|rd|th)\s+)?[A-Z][^(]{3,120}?)"
            r"\s*\(([A-Z][A-Za-z0-9\-]{1,15})\s*[,\s]\s*(\d{4})\)",
            raw,
        )
        if m:
            full_name = m.group(1).strip().rstrip(",")
            acronym = m.group(2)
            year = m.group(3)
            rec["conference"] = f"{full_name} ({acronym})"
            rec["year"] = rec.get("year") or year

    # Pattern 5: in Proc. <Spelled-out full name> (ACRONYM'YY), City, Country
    if not rec.get("conference"):
        m = re.search(
            r"\bin\s+Proc\.?\s+"
            r"(?:\d+(?:st|nd|rd|th)\s+)?[A-Z][^(]{3,80}"
            r"\(([A-Z][A-Z0-9\-]+)['’]?(\d{2,4})\)"
            r"[\s,]+([^,]+),\s*([^,]+),",
            raw, re.IGNORECASE,
        )
        if m:
            acronym = m.group(1).upper()
            yr_raw = m.group(2)
            year4 = ("20" + yr_raw) if len(yr_raw) == 2 else yr_raw
            rec["conference"] = acronym
            rec["year"] = rec.get("year") or year4
            rec["city"] = m.group(3).strip()
            rec["country"] = m.group(4).strip()

    # Catch "in <BookTitle>, ... Eds. (Publisher, Year)" (e.g. NeurIPS)
    if not rec.get("conference"):
        m = re.search(
            r",\s*in\s+([A-Z][^,]{10,80}?),\s.*?\bEds?\.\s*\(",
            raw, re.DOTALL,
        )
        if m:
            rec["conference"] = m.group(1).strip()

    # Lift ``paper XXXXX`` from the body.  Independent of the conference
    # pattern (it can appear anywhere — "in Proc. IPAC'23, ..., paper
    # MOPA001." is the common case).  The 2-5 capital letters + 2-4
    # digits pattern is a reasonable heuristic for JACoW paper IDs.
    if not rec.get("paper_id"):
        m = re.search(r"\bpaper\s+([A-Z]{2,5}\d{2,4}[A-Z]?\d*)", raw)
        if m:
            rec["paper_id"] = m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: book fields
# ─────────────────────────────────────────────────────────────────────────────

def _extract_book_fields(raw: str, rec: dict) -> None:
    """Populate editor, edition, publisher, city, booktitle from book refs."""
    m = re.search(r"([A-Z][A-Za-z.\-\s]{3,40}),\s*Eds?\.", raw)
    if m:
        rec["editor"] = m.group(1).strip()

    m = re.search(
        r"([A-Z][a-zA-Z\s]{2,20}):\s+"
        r"(" + "|".join(re.escape(p) for p in _KNOWN_PUBLISHERS) + r")"
        r"(?:,\s*\d{4})?",
        raw,
    )
    if m:
        rec.setdefault("city", m.group(1).strip())
        rec.setdefault("publisher", m.group(2).strip())
    else:
        for pub in _KNOWN_PUBLISHERS:
            if pub.lower() in raw.lower():
                rec.setdefault("publisher", pub)
                break

    m = re.search(r"\b(\d+(?:st|nd|rd|th))\s+[Ee]d\.", raw)
    if m:
        rec["edition"] = m.group(1)

    m = re.search(r"\bin\s+([A-Z][^,\.]{5,80})", raw)
    if m and "Proc" not in m.group(1):
        rec.setdefault("booktitle", m.group(1).strip())


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6: type flags
# ─────────────────────────────────────────────────────────────────────────────

def _extract_type_flags(raw: str, rec: dict) -> None:
    """Populate is_thesis / degree / is_patent / school / patent_number."""
    if re.search(r"ph\.?d\.?\s+thesis|doctoral\s+thesis", raw, re.IGNORECASE):
        rec["is_thesis"] = True
        rec.setdefault("degree", "Ph.D.")
    if re.search(
        r"m\.?sc?\.?\s+thesis|master['’]?s\s+thesis|msc\s+thesis|"
        r"m\.?\s*eng\.?\s+thesis|master\s+of\s+(?:science|engineering)",
        raw, re.IGNORECASE,
    ):
        rec["is_thesis"] = True
        rec.setdefault("degree", "M.Sc.")
    if re.search(
        r"pat\.\s*\d|patent\s+(?:no\.?\s*|number\s*|application\s*)?"
        r"[A-Z]{0,3}\s*\d",
        raw, re.IGNORECASE,
    ):
        rec["is_patent"] = True
    m = re.search(
        r"(?:Ph\.D\.|M\.Sc?\.?|thesis),\s+"
        r"([^,]+(?:Dept|Univ|Institut|College)[^,]*)",
        raw, re.IGNORECASE,
    )
    if m:
        rec["school"] = m.group(1).strip()
    m = re.search(
        r"\bpatent\s+([A-Z]{0,3}\s*\d[\d\s,]+)", raw, re.IGNORECASE
    )
    if m:
        rec["patent_number"] = re.sub(r"\s+", "", m.group(1))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7: report fields
# ─────────────────────────────────────────────────────────────────────────────

def _extract_report_fields(raw: str, rec: dict) -> None:
    """Populate rep_id and institution from technical/internal report strings.

    Patterns (JACoW ANNEX B §23-26):
      ``Rep. CERN-2012-333``            → rep_id = 'CERN-2012-333'
      ``Rep. SLAC-REP-474``             → rep_id = 'SLAC-REP-474'
      ``Rep. 17-03``                    → rep_id = '17-03'
      ``"Title, CERN, 2003"``           → institution = 'CERN', title stripped
    """
    m = re.search(r"\bRep(?:ort)?\.\s+([A-Z0-9][\w\-\.]{1,40})", raw)
    if m:
        rec.setdefault("rep_id", m.group(1).rstrip(".,"))

    if not rec.get("institution") and not rec.get("conference"):
        m = re.search(
            r'"[^"]+",\s+'
            r'([A-Z][A-Za-z\s&\-]+?)'
            r",\s+"
            r"[A-Z][a-zA-Z\s]+,",
            raw,
        )
        if m:
            rec.setdefault("institution", m.group(1).strip())

    if not rec.get("institution") and not rec.get("conference") and rec.get("title"):
        tm = re.search(r",\s*([A-Z][A-Z0-9]{1,9})(?:,\s*\d{4})?\s*$", rec["title"])
        if tm and tm.group(1) in TITLE_TAIL_INSTITUTIONS:
            rec["institution"] = tm.group(1)
            rec["title"] = rec["title"][: tm.start()].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: journal name (between title quote and vol./no.)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_journal(raw: str, rec: dict) -> None:
    """Populate journal name from the segment between the title quote
    and the first volume / issue marker.

    Imported here as a soft dependency to avoid a circular import
    at module load (the journal_abbrev module loads JabRef and LTWA
    at import time).  Falls back gracefully if import fails.
    """
    try:
        from src.refs.journal_abbrev import normalize_journal
    except Exception:
        return
    open_q = re.search(r'["“«]', raw)
    if not open_q:
        return
    after_open = raw[open_q.end():]
    close_q = re.search(r'["”»]', after_open)
    if not close_q:
        return
    after = after_open[close_q.end():]
    jm = re.match(
        r"^,\s*(?!(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s*(?:,|\d))"
        r"((?:[A-Z][A-Za-z.&\-]*\.?\s*"
        r"(?:\b(?:and|of|for|in|the|on|to)\b\s*)?){1,8})"
        r"(?=:|,|\s+vol\.|\s+\d{4})",
        after,
    )
    if jm:
        rec["journal"] = normalize_journal(jm.group(1).rstrip(", "))


# ─────────────────────────────────────────────────────────────────────────────
# No-quote title parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _nq_is_author(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if re.search(r"\bet\s+al\.?$", s, re.IGNORECASE):
        return True
    if re.match(r"^(?:[A-Z]\.[-\s]?)+\s+[A-Z][a-z]", s):
        return True
    if re.match(r"^[A-Z]\.\s+[A-Z]", s):
        return True
    if re.match(
        r"^[A-Z][a-z\-]+(?:\s+[A-Z][a-z\-]+)*,\s*[A-Z]\.", s
    ):
        return True
    if re.match(r"^[A-Z][a-z\-]{1,20}$", s):
        return True
    return False


def _nq_is_terminal(s: str) -> bool:
    """True when *s* looks like a venue marker (not a name or title)."""
    s = s.strip()
    if not s:
        return False
    if re.match(r"^(19[5-9]\d|20\d\d)$", s):
        return True
    if re.match(r"^(vol|no|pp?)\b", s, re.IGNORECASE):
        return True
    if re.match(r"^arXiv:", s, re.IGNORECASE):
        return True
    if re.match(r"^in\s+(?:Proc\.|Advances\s+in)\b", s, re.IGNORECASE):
        return True
    if re.match(r"^in\s+\d+(?:st|nd|rd|th)\b", s, re.IGNORECASE):
        return True
    if re.match(r"^[A-Z][a-z]+\.\s+[A-Z]", s):
        return True
    if re.match(r"^(IEEE|Nature|Science|Optica)\b", s):
        return True
    if re.match(r"^doi[:\s]|^10\.\d{4}/", s, re.IGNORECASE):
        return True
    if re.search(r"\bEds?\.\s*\(", s):
        return True
    # Conference acronym + year suffix → venue, not a title word
    if re.match(r"^[A-Z][A-Z0-9\-]+['’]\d{2}\b", s):
        return True
    # "City, Country" style location token → venue, not title
    if re.match(r"^[A-Z][a-zA-Z]+,\s+[A-Z][a-zA-Z]+,?$", s):
        return True
    return False


def _nq_is_single_cap(s: str) -> bool:
    return bool(re.match(r"^[A-Z][a-z\-]{1,20}$", s.strip()))


def _extract_no_quote_title(raw: str) -> tuple[str | None, str | None, bool]:
    """Fallback chunked parser for citations with no quoted title.

    Returns ``(authors_str, title_str, blocklist_hit)``:
    - ``authors_str`` / ``title_str`` may be None if not identified.
    - ``blocklist_hit`` is True when a known institution / proper-noun
      blocklist word was found — the caller may want to flag the
      reference for manual review because the author/title split is
      ambiguous.
    """
    s = re.sub(r"^\s*(?:\[\d+\]\.?\s*|\d+\.\s*)", "", raw).strip()
    s2 = re.sub(r"\s+and\s+", " " + _NQ_SENTINEL + " ", s)
    chunks = [c.strip() for c in s2.split(",") if c.strip()]
    sentinel_before = [c.startswith(_NQ_SENTINEL) for c in chunks]

    def _restore(c: str) -> str:
        return re.sub(
            r"^\|\|\|AND\|\|\|\s*", "", c.strip()
        ).replace(_NQ_SENTINEL, "and").strip()

    author_parts: List[Tuple[str, bool]] = []
    prev_singlecap = False
    blocklist_hit = False
    i = 0
    while i < len(chunks):
        c, had_and = _restore(chunks[i]), sentinel_before[i]
        if _nq_is_terminal(c) and not _nq_is_author(c):
            break
        if _nq_is_author(c):
            is_sc = _nq_is_single_cap(c) and not re.search(
                r"\bet\s+al", c, re.IGNORECASE
            )
            if is_sc:
                if c in _NQ_PROPER_NOUN_BLOCKLIST:
                    blocklist_hit = True
                    break
                if not (i == 0 or had_and or prev_singlecap):
                    break
                prev_singlecap = True
            else:
                prev_singlecap = False
            author_parts.append((c, had_and))
            i += 1
        else:
            first_token = c.split()[0] if c.split() else ""
            if first_token in _NQ_PROPER_NOUN_BLOCKLIST and author_parts:
                blocklist_hit = True
            break

    def _join(parts: List[Tuple[str, bool]]) -> str:
        if not parts:
            return ""
        res = parts[0][0]
        for display, had_and in parts[1:]:
            res += (", and " if had_and else ", ") + display
        # If the list has exactly 2 authors joined via 'and', drop the comma
        if len(parts) == 2 and ", and " in res:
            res = res.replace(", and ", " and ", 1)
        return res

    authors_str = _join(author_parts) if author_parts else None

    title_parts: List[Tuple[str, bool]] = []
    while i < len(chunks):
        c, had_and = _restore(chunks[i]), sentinel_before[i]
        if _nq_is_terminal(c) and title_parts:
            break
        if not _nq_is_terminal(c):
            title_parts.append((c, had_and))
        i += 1
    title_str = _join(title_parts).strip() if title_parts else None
    return authors_str, title_str, blocklist_hit


# ─────────────────────────────────────────────────────────────────────────────
# Nature-style citation parser
# ─────────────────────────────────────────────────────────────────────────────

_NAT_ONE_AUTHOR = (
    r"[A-Z][a-zÀ-ɏ\-]+,\s+[A-Z]\.(?:\s+[A-Z]\.)*"
)
_NAT_SEP = r"(?:,\s+|\s+&\s+)"
_NAT_AUTHOR_BLOCK_RE = re.compile(
    r"^(?:\[\d+\]\s*)?"
    r"((?:" + _NAT_ONE_AUTHOR + _NAT_SEP + r")*" + _NAT_ONE_AUTHOR + r")"
    r"\s+((?:[A-Z][a-z])|(?:[A-Z]\s+[a-z])|(?:[A-Z]{2})|(?:[A-Z]\d))",
)
_NAT_ET_AL_RE = re.compile(
    r"^(?:\[\d+\]\s*)?"
    r"(" + _NAT_ONE_AUTHOR + r"\s+et\s+al\.)"
    r"(?:\s+[A-Z][A-Z]?\.(?:\s+[A-Z][A-Z]?\.)*,?)*"
    r"\s+((?:[A-Z][A-Za-z0-9])|(?:[A-Z]\s+[a-z]))",
)


def _parse_nature_authors(author_str: str) -> List[dict]:
    """Parse a Nature-style author block (Family, I., …) into a list of
    ``{'given', 'family'}`` dicts.
    """
    parts = [
        p.strip()
        for p in re.split(r",\s+|\s+&\s+", author_str)
        if p.strip()
    ]
    authors: List[dict] = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if re.match(r"^[A-Z][a-zÀ-ɏ\-]+$", p):
            family = p
            given_parts: List[str] = []
            while (
                i + 1 < len(parts)
                and re.match(r"^[A-Z]\.(?:\s+[A-Z]\.)*$", parts[i + 1])
            ):
                i += 1
                given_parts.append(parts[i])
            given = " ".join(given_parts)
            authors.append({"given": to_initials(given), "family": family})
        i += 1
    return authors


def _try_parse_nature_style(raw: str, rec: dict) -> bool:
    """Detect and parse a Nature/Springer-style citation (no quoted title).

    Sets rec fields for authors_raw, title, journal, volume, pages, year.
    Returns True when the Nature author-block pattern was recognised.
    """
    m = _NAT_AUTHOR_BLOCK_RE.match(raw)
    is_et_al = False
    if not m:
        m = _NAT_ET_AL_RE.match(raw)
        is_et_al = bool(m)
    if not m:
        return False

    author_str = m.group(1)
    remainder = raw[m.start(2):].strip()

    def _try_venue_ranked(tail: str):
        """Return (rank, applier) for the best pattern matching *tail*,
        or None if nothing matches.  Lower rank = more specific match.
        """

        def _r1(_rec, m):
            rec.setdefault("journal", m.group(1).rstrip(", "))
            rec.setdefault("volume", m.group(2))
            rec.setdefault("pages", pages_fmt(m.group(3)))
            rec.setdefault("year", m.group(4))

        def _r2(_rec, m):
            rec.setdefault("journal", m.group(1).rstrip(", "))
            rec.setdefault("volume", m.group(2))
            rec.setdefault("year", m.group(3))

        def _r3(_rec, m):
            rec.setdefault("arxiv_id", m.group(1))

        def _r4(_rec, m):
            venue = m.group(1).strip()
            rec.setdefault("year", m.group(2))
            if (re.search(r"\b[A-Z][a-z]*\.\s", venue)
                    or re.search(
                        r"\b(?:J\.|Rev\.|Phys\.|Lett\.|Commun\.|"
                        r"Trans\.|Proc\.)",
                        venue,
                    )):
                rec.setdefault("journal", venue)
            else:
                rec.setdefault("conference", venue)

        def _r5(_rec, m):
            rec.setdefault("year", m.group(1))

        # Rank 0: Nature-publisher format e.g.
        # "Nature Methods 2024 21:8  21, 1462-1465 (2024)"
        vm = re.match(
            r"^([A-Za-z][A-Za-z ]{2,40}?)"
            r"\s+(?:19|20)\d{2}"
            r"\s+\d{1,4}:\d{1,4}"
            r"\s+\d{1,4},\s*"
            r"([A-Za-z]?\d[\w–\-]*)"
            r"\s*\((\d{4})\)\.?\s*$",
            tail,
        )
        if vm:

            def apply0(_rec, _m=vm):
                rec.setdefault("journal", _m.group(1).strip())
                rec.setdefault("pages", pages_fmt(_m.group(2)))
                rec.setdefault("year", _m.group(3))

            return (0, apply0)

        # Rank 1: Journal + vol + pages + (year)
        vm = re.match(
            r"^([A-Z][A-Za-z. &]{1,60}?),?\s+(\d{1,4}),\s*"
            r"([A-Za-z]?\d[\w–\-]*)\s*\((\d{4})\)\.?\s*$",
            tail,
        )
        if vm:
            return (1, lambda _r, _m=vm: _r1(rec, _m))

        # Rank 2: Journal + vol + (year), no pages
        vm = re.match(
            r"^([A-Z][A-Za-z. &]{1,60}?),?\s+(\d{1,4})\s*"
            r"\((\d{4})\)\.?\s*$",
            tail,
        )
        if vm:
            return (2, lambda _r, _m=vm: _r2(rec, _m))

        # Rank 3: arXiv preprint
        vm = re.match(
            r"^arXiv\s+preprint\s+arXiv:(\d{4}\.\d{4,5})\.?\s*$",
            tail, re.IGNORECASE,
        )
        if vm:
            return (3, lambda _r, _m=vm: _r3(rec, _m))

        # Rank 4: Venue/conference (year)
        vm = re.match(
            r"^((?:\d+(?:st|nd|rd|th)\s+)?[A-Z][A-Za-z].+?)\s*"
            r"\((\d{4})\)\.?\s*$",
            tail,
        )
        if vm:
            return (4, lambda _r, _m=vm: _r4(rec, _m))

        # Rank 5: bare (year)
        vm = re.match(r"^\((\d{4})\)\.?\s*$", tail)
        if vm:
            return (5, lambda _r, _m=vm: _r5(rec, _m))

        return None

    # Find every ". " position (sentence boundaries) in remainder.
    # Skip positions where the next token looks like a journal abbrev.
    _JABBREV_RE = re.compile(
        r"^\s+(?:"
        r"J\.|Nat\.|Sci\.|Phys\.|Rev\.|Lett\.|Proc\.|Conf\.|"
        r"Ann\.|Adv\.|Int\.|Eur\.|IEEE\s|ACM\s|BMJ\s|Lancet\s|"
        r"JMIR\s|NPJ\s|npj\s|Radiol\.|Theranostics"
        r")"
    )
    dot_positions = [
        i for i in range(len(remainder) - 1)
        if remainder[i] == "." and i + 1 < len(remainder)
        and remainder[i + 1] in " \t"
        and not _JABBREV_RE.match(remainder[i + 1:])
    ]

    best_rank = 999
    best_pos = -1
    best_app = None

    for pos in dot_positions:
        tail = remainder[pos + 1:].strip()
        res = _try_venue_ranked(tail)
        if res is None:
            continue
        rank, app = res
        if rank < best_rank:
            best_rank = rank
            best_pos = pos
            best_app = app

    if best_app is None:
        return False

    title_end = best_pos if best_pos > 0 else len(remainder)
    title = remainder[:title_end].strip().rstrip(".")
    rec["title"] = clean_title(title)
    if not rec.get("title"):
        return False

    # Authors
    nature_authors = _parse_nature_authors(author_str)
    if nature_authors:
        rec["authors_raw"] = nature_authors
        rec["crossref_authors"] = nature_authors  # so merge_crossref recognises
    elif is_et_al:
        rec["authors_raw"] = author_str.strip()
    else:
        rec["authors_raw"] = author_str.strip()

    # Venue / year / etc.
    best_app(rec)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Local helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_doi(value: str) -> str:
    """Strip ``doi:`` / ``https://doi.org/`` prefixes and trailing punctuation."""
    if not value:
        return ""
    s = str(value).strip()
    s = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi[:\s]+)",
        "", s, flags=re.IGNORECASE,
    )
    s = s.strip().rstrip(".,)>]\"'")
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def extract_from_raw(raw: str) -> dict:
    """Run all sub-parsers over a raw citation string and return a unified
    metadata dict.

    The orchestrator runs the sub-extractors in dependency order:
    identifiers → bibliographic → title/authors → conference → book →
    type flags → report → journal.  Sub-extractors are idempotent and
    merge-friendly — a later extractor only sets a field if the earlier
    extractors didn't already populate it.
    """
    rec: dict = {"raw": raw}
    _extract_identifiers(raw, rec)
    _extract_bibliographic(raw, rec)
    _extract_title_authors(raw, rec)
    _extract_conference(raw, rec)
    _extract_book_fields(raw, rec)
    _extract_type_flags(raw, rec)
    _extract_report_fields(raw, rec)
    _extract_journal(raw, rec)
    return rec


# Public alias for the conference sub-extractor, since it's the most
# useful standalone entry point for the autofix reformat pass.
extract_conference = _extract_conference
