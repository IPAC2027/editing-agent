"""JACoW journal-name → ISO 4 abbreviation cascade.

L1  – hand-curated JACoW table (ANNEX C + accelerator-physics overrides)
L2  – JabRef combined CSV abbreviation lists (~18 000 entries, optional)
L2.5 – ISSN LTWA word-by-word abbreviation (optional, network)
L3  – pass-through (return input unchanged, debug-logged)

L1 is always available with zero network. L2/L2.5 are lazily loaded the first
time :func:`normalize_journal` is called and gracefully fall back to L1 only
when the network is unavailable. Set the environment variable
``AIAGENT_DISABLE_JABREF=1`` / ``AIAGENT_DISABLE_LTWA=1`` to skip downloads.

Migrated from the v1.0.0 standalone formatter, with these adaptations:
- HTTP client is :mod:`httpx` (matches the rest of the package) instead of
  ``urllib`` from the standalone script.
- No SqliteCache wired in this Tier-1 pass — the loaders cache the parsed map
  in module-level state for the life of the process. Persistent caching can
  be layered on later by replacing :func:`_download_text`.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# L1 — hand-curated JACoW ANNEX C overrides (lower-case keys)
# ─────────────────────────────────────────────────────────────────────────────

JACOW_ABBREVS: dict[str, str] = {
    # ── Particle-accelerator journals (priority overrides) ────────────────
    "physical review accelerators and beams":
        "Phys. Rev. Accel. Beams",
    "physical review special topics - accelerators and beams":
        "Phys. Rev. Spec. Top. Accel. Beams",
    "physical review special topics accelerators and beams":
        "Phys. Rev. Spec. Top. Accel. Beams",
    "nuclear instruments and methods in physics research section a: accelerators, spectrometers, detectors and associated equipment":
        "Nucl. Instrum. Methods Phys. Res. A",
    "nuclear instruments and methods in physics research section a":
        "Nucl. Instrum. Methods Phys. Res. A",
    "nuclear instruments and methods in physics research section b: beam interactions with materials and atoms":
        "Nucl. Instrum. Methods Phys. Res. B",
    "nuclear instruments and methods in physics research section b":
        "Nucl. Instrum. Methods Phys. Res. B",
    "nuclear instruments and methods in physics research":
        "Nucl. Instrum. Methods Phys. Res.",
    "particle accelerators": "Part. Accel.",
    "accelerators":          "Part. Accel.",
    # ── JACoW style guide ANNEX C (~125 entries, alphabetical) ────────────
    "acm transactions on computer systems":                    "ACM Trans. Comput. Syst.",
    "acm transactions on modelling and computer systems":      "ACM Trans. Model. Comput. Syst.",
    "acm transactions on software engineering and methodology": "ACM Trans. Software Eng. Methodol.",
    "advances in cryogenic engineering":                       "Adv. Cryog. Eng.",
    "advanced energy materials":                               "Adv. Energy Mater.",
    "advances in mechanical engineering":                      "Adv. Mech. Eng.",
    "advances in synchrotron radiation":                       "Adv. Synchrotron Radiat.",
    "annals of mathematical statistics":                       "Ann. Math. Stat.",
    "annals of mathematics":                                   "Ann. Math.",
    "annual review of nuclear and particle science":           "Annu. Rev. Nucl. Part. Sci.",
    "applied physics a":                                       "App. Phys. A",
    "applied physics b":                                       "App. Phys. B",
    "applied physics b: lasers and optics":                    "App. Phys. B: Lasers Opt.",
    "applied physics express":                                 "App. Phys. Express",
    "applied physics letters":                                 "App. Phys. Lett.",
    "applied physics research":                                "App. Phys. Res.",
    "applied physics reviews":                                 "App. Phys. Rev.",
    "applied superconductivity":                               "App. Supercond.",
    "artificial intelligence":                                 "Artif. Intell.",
    "artificial intelligence review":                          "Artif. Intell. Rev.",
    "atomic data and nuclear data tables":                     "At. Data Nucl. Data Tables",
    "australian journal of physics":                           "Aust. J. Phys.",
    "canadian journal of physics":                             "Can. J. Phys.",
    "chinese journal of electrical engineering":               "Chin. J. Electr. Eng.",
    "chinese journal of mechanical engineering":               "Chin. J. Mech. Eng.",
    "chinese journal of physics":                              "Chin. J. Phys.",
    "communications physics":                                  "Commun. Phys.",
    "computer science review":                                 "Comp. Sci. Rev.",
    "european journal of physics":                             "Eur. J. Phys.",
    "european journal of radiology":                           "Eur. J. Radiol.",
    "european physical journal applied physics":               "Eur. Phys. J. Appl. Phys.",
    "european physical journal d: atomic, molecular, optical and plasma physics":
        "Eur. Phys. J. D",
    "european physical journal d":                             "Eur. Phys. J. D",
    "european physical journal special topics":                "Eur. Phys. J. Spec. Top.",
    "frontiers in big data":                                   "Front. Big Data",
    "frontiers in imaging":                                    "Front. Imaging",
    "frontiers in mechanical engineering":                     "Front. Mech. Eng.",
    "frontiers in physics":                                    "Front. Phys.",
    "frontiers in photonics":                                  "Front. Photonics",
    "frontiers in signal processing":                          "Front. Signal Process.",
    "high power laser and particle beams":                     "High Power Laser Part. Beams",
    "high power laser science and engineering":                "High Power Laser Sci. Eng.",
    "ieee journal of quantum electronics":                     "IEEE J. Quantum Electron.",
    "ieee software":                                           "IEEE Software",
    "ieee transactions on applied superconductivity":          "IEEE Trans. Appl. Supercond.",
    "ieee transactions on big data":                           "IEEE Trans. Big Data",
    "ieee transactions on communications":                     "IEEE Trans. Commun.",
    "ieee transactions on computer imaging":                   "IEEE Trans. Comp. Imaging",
    "ieee transactions on control systems technology":         "IEEE Trans. Control Syst. Technol.",
    "ieee transactions on image processing":                   "IEEE Trans. Image Process.",
    "ieee transactions on instrumentation and measurement":    "IEEE Trans. Instrum. Meas.",
    "ieee transactions on magnetics":                          "IEEE Trans. Magnetics",
    "ieee transactions on neural networks":                    "IEEE Trans. Neural Networks",
    "ieee transactions on nuclear science":                    "IEEE Trans. Nucl. Sci.",
    "ieee transactions on power electronics":                  "IEEE Trans. Power Electron.",
    "ieee transactions on power systems":                      "IEEE Trans. Power Syst.",
    "ieee transactions on plasma science":                     "IEEE Trans. Plasma Sci.",
    "ieee transactions on quantum engineering":                "IEEE Trans. Quantum Eng.",
    "ieee transactions on signal processing":                  "IEEE Trans. Signal Process.",
    "ieee transactions on software engineering":               "IEEE Trans. Software Eng.",
    "imaging science journal":                                 "Imaging Sci. J.",
    "instruments":                                             "Instruments",
    "instruments and experimental techniques":                 "Instrum. Exp. Tech.",
    "international journal of modern physics a: particles and fields, gravitation, cosmology, nuclear physics":
        "Int. J. Mod. Phys. A",
    "international journal of modern physics a":               "Int. J. Mod. Phys. A",
    "international journal of modern physics b: condensed matter physics, statistical physics, applied physics":
        "Int. J. Mod. Phys. B",
    "international journal of modern physics b":               "Int. J. Mod. Phys. B",
    "international journal of modern physics c: computational physics and physics computation":
        "Int. J. Mod. Phys. C",
    "international journal of modern physics c":               "Int. J. Mod. Phys. C",
    "international journal of modern physics d: gravitation, astrophysics, cosmology":
        "Int. J. Mod. Phys. D",
    "international journal of modern physics d":               "Int. J. Mod. Phys. D",
    "international journal of modern physics e: nuclear physics": "Int. J. Mod. Phys. E",
    "international journal of modern physics e":               "Int. J. Mod. Phys. E",
    "international journal of modern physics: conference series": "Int. J. Mod. Phys.: Conf. Ser.",
    "journal of computational physics":                        "J. Comput. Phys.",
    "journal of control science and engineering":              "J. Control Sci. Eng.",
    "journal of engineering thermophysics":                    "J. Eng. Thermophys",
    "journal of instrumentation":                              "J. Instrum.",
    "journal of the korean physical society":                  "J. Korean Phys. Soc.",
    "journal of laser applications":                           "J. Laser Appl.",
    "journal of nuclear science and technology":               "J. Nucl. Sci. Technol.",
    "journal of physics a: general physics":                   "J. Phys. A: Gen. Phys.",
    "journal of physics a: mathematical and general":          "J. Phys. A: Math. Gen.",
    "journal of physics a: mathematical and theoretical":      "J. Phys. A: Math. Theor.",
    "journal of physics a: mathematical, nuclear and general": "J. Phys. A: Math. Nucl. Gen.",
    "journal of physics b: atomic and molecular physics":      "J. Phys. B: At. Mol. Phys.",
    "journal of physics b: atomic, molecular and optical physics": "J. Phys. B: At. Mol. Opt. Phys.",
    "journal of physics g: nuclear and particle physics":      "J. Phys. G: Nucl. Part. Phys.",
    "journal of physics g: nuclear physics":                   "J. Phys. G: Nucl. Phys.",
    "journal of physical and chemical reference":              "J. Phys. Chem. Ref. Data",
    "journal of physics: conference series":                   "J. Phys.: Conf. Ser.",
    "journal of physics: photonics":                           "J. Phys.: Photonics",
    "journal of quantum computing":                            "J. Quantum Comput.",
    "journal of radiation research":                           "J. Radiat. Res.",
    "journal of radioanalytical and nuclear chemistry":        "J. Radioanal. Nucl. Chem.",
    "journal of radioanalytical and nuclear chemistry articles": "J. Radioanal. Nucl. Chem. Art.",
    "journal of radioanalytical and nuclear chemistry letters": "J. Radioanal. Nucl. Chem. Lett.",
    "journal of superconductivity":                            "J. Superconductivity",
    "journal of synchrotron radiation":                        "J. Synchrotron Radiat.",
    "japanese journal of applied physics":                     "Jpn. J. Appl. Phys.",
    "japanese journal of radiology":                           "Jpn. J. Radiol.",
    "korean journal of material research":                     "Korean J. Mater. Res",
    "korean journal of metals and materials":                  "Korean J. Met. Mater",
    "laser physics":                                           "Laser Phys.",
    "laser physics letters":                                   "Laser Phys. Lett.",
    "natural language engineering":                            "Nat. Lang. Eng.",
    "nature human behaviour":                                  "Nat. Hum. Behav.",
    "nature":                                                  "Nature",
    "nature astronomy":                                        "Nat. Astron.",
    "nature communications":                                   "Nat. Commun.",
    "nature photonics":                                        "Nat. Photonics",
    "nature physics":                                          "Nat. Phys.",
    "nuclear instruments":                                     "Nucl. Instrum.",
    "nuclear instruments and methods":                         "Nucl. Instrum. Methods",
    "nuclear science and engineering":                         "Nucl. Sci. Eng.",
    "nuclear science and techniques":                          "Nucl. Sci. Tech.",
    "nuovo cimento a":                                         "Nuovo Cimento A",
    "nuovo cimento b":                                         "Nuovo Cimento B",
    "nuovo cimento c":                                         "Nuovo Cimento C",
    "nuovo cimento d":                                         "Nuovo Cimento D",
    "optica":                                                  "Optica",
    "optics communications":                                   "Opt. Communic.",
    "optics express":                                          "Opt. Express",
    "optics and laser technology":                             "Opt. Laser Technol.",
    "optics and lasers in engineering":                        "Opt. Lasers Eng.",
    "optical materials":                                       "Opt. Mater.",
    "optical materials express":                               "Opt. Mater. Express",
    "optics and photonics letters":                            "Opt. Photonics Lett.",
    "optics and photonics news":                               "Opt. Photonics News",
    "optical and quantum electronics":                         "Opt. Quantum Electron.",
    "photonics":                                               "Photonics",
    "physics letters a":                                       "Phys. Lett. A",
    "physics letters b":                                       "Phys. Lett. B",
    "physics of plasmas":                                      "Phys. Plasma",
    "physics reports":                                         "Phys. Rep.",
    "physica scripta":                                         "Phys. Scr.",
    "physica scripta t":                                       "Phys. Scr. T",
    "physical review a":                                       "Phys. Rev. A",
    "physical review e":                                       "Phys. Rev. E",
    "physical review letters":                                 "Phys. Rev. Lett.",
    "physica c: superconductivity and its applications":       "Physica C",
    "physica c":                                               "Physica C",
    "plasma physics":                                          "Plasma Phys.",
    "progress in particle and nuclear physics":                "Prog. Part. Nucl. Phys.",
    "progress in quantum electronics":                         "Prog. Quantum Electron.",
    "physics today":                                           "Phys. Today",
    "quantum beam science":                                    "Quantum Beam Sci.",
    "quantum electronics":                                     "Quantum Electron.",
    "quantum engineering":                                     "Quantum Eng.",
    "quantum optics":                                          "Quantum Opt.",
    "quantum reports":                                         "Quantum Rep.",
    "review of accelerator science and technology":            "Rev. Accel. Sci. Technol.",
    "reviews of modern physics":                               "Rev. Mod. Phys.",
    "reviews of modern plasma physics":                        "Rev. Mod. Plasma Phys.",
    "reviews of scientific instruments":                       "Rev. Sci. Instrum.",
    "science":                                                 "Science",
    "scientific reports":                                      "Sci. Rep.",
    "superconductor science and technology":                   "Supercond. Sci. Technol.",
    "symmetry":                                                "Symmetry",
    "synchrotron radiation news":                              "Synchrotron Radiat. News",
}


# ─────────────────────────────────────────────────────────────────────────────
# L2 — JabRef combined list (downloaded once, in-memory cached for the session)
# ─────────────────────────────────────────────────────────────────────────────

# Hardcoded fallback list — the 19 CSV files that were live in the JabRef
# abbrv.jabref.org repo as of 2026-06.  Used when the GitHub Contents API
# is unreachable (rate-limited, offline, blocked) so the L2 lookup is still
# populated after the first process start.  Kept up-to-date by the loader
# itself whenever the API *is* reachable — see :func:`_list_jabref_csvs`.
_JABREF_FALLBACK_CSVS: list[str] = [
    "journal_abbreviations_acs.csv",
    "journal_abbreviations_aea.csv",
    "journal_abbreviations_ams.csv",
    "journal_abbreviations_annee-philologique.csv",
    "journal_abbreviations_astronomy.csv",
    "journal_abbreviations_dainst.csv",
    "journal_abbreviations_entrez.csv",
    "journal_abbreviations_general.csv",
    "journal_abbreviations_geology_physics.csv",
    "journal_abbreviations_geology_physics_variations.csv",
    "journal_abbreviations_ieee.csv",
    "journal_abbreviations_ieee_strings.csv",
    "journal_abbreviations_lifescience.csv",
    "journal_abbreviations_mathematics.csv",
    "journal_abbreviations_mechanical.csv",
    "journal_abbreviations_medicus.csv",
    "journal_abbreviations_meteorology.csv",
    "journal_abbreviations_sociology.csv",
    "journal_abbreviations_ubc.csv",
]

_JABREF_REPO = "JabRef/abbrv.jabref.org"
_JABREF_PATH = "journals"
_JABREF_BRANCH = "main"
_JABREF_API_URL = (
    f"https://api.github.com/repos/{_JABREF_REPO}/contents/{_JABREF_PATH}"
    f"?ref={_JABREF_BRANCH}"
)
_JABREF_RAW_BASE = (
    f"https://raw.githubusercontent.com/{_JABREF_REPO}/{_JABREF_BRANCH}/{_JABREF_PATH}"
)

_jabref_lock: threading.Lock = threading.Lock()
_jabref_map: Optional[dict[str, str]] = None

# Cache of the discovered CSV file list.  Populated lazily by
# :func:`_list_jabref_csvs`; survives until the process exits.
_jabref_csv_lock: threading.Lock = threading.Lock()
_jabref_csv_list: Optional[list[dict[str, object]]] = None


# ─────────────────────────────────────────────────────────────────────────────
# L2.5 — ISSN LTWA (word-by-word ISO 4 abbreviation)
# ─────────────────────────────────────────────────────────────────────────────

_LTWA_URL = (
    "https://www.issn.org/wp-content/uploads/2021/07/ltwa_20210702.csv"
)

# Fallback omission set used when LTWA is unavailable (covers the most common
# ISO 4 stop-words that LTWA marks as "n.a.").
_ISO4_OMIT: frozenset = frozenset({
    "a", "an", "the", "and", "or", "for", "of", "in", "on", "at",
    "by", "to", "with", "from", "de", "der", "des", "del", "di",
    "la", "le", "les", "und", "et", "en", "e",
})

# Languages we accept from the LTWA (English + multilingual + unspecified).
_LTWA_KEEP_LANGS: frozenset = frozenset({"eng", "mul", "n.a.", "und"})

_ltwa_lock: threading.Lock = threading.Lock()
_ltwa_exact: Optional[dict[str, str]] = None        # word → abbrev | 'n.a.'
_ltwa_prefix: Optional[list[tuple[str, str]]] = None  # (prefix, abbrev) longest-first


# ─────────────────────────────────────────────────────────────────────────────
# HTTP loader (shared by JabRef and LTWA)
# ─────────────────────────────────────────────────────────────────────────────

_HTTP_TIMEOUT = 30.0
_HTTP_HEADERS = {"User-Agent": "aiagent-formatter/0.1"}


def _download_text(url: str, *, encoding: str = "utf-8") -> str:
    """GET *url* and return the decoded body, or ``''`` on any failure.

    Used by the L2 and L2.5 loaders; deliberately silent on errors so that the
    cascade falls through to lower tiers (or the original input) when offline.
    """
    try:
        resp = httpx.get(url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Download %s returned HTTP %d", url, resp.status_code)
            return ""
        try:
            return resp.content.decode(encoding)
        except UnicodeDecodeError:
            return resp.content.decode("latin-1", errors="replace")
    except Exception as exc:
        logger.warning("Download failed for %s: %s", url, exc)
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# JabRef loader
# ─────────────────────────────────────────────────────────────────────────────

def _list_jabref_csvs() -> list[dict[str, object]]:
    """Discover the live set of ``*.csv`` files in the JabRef journals dir.

    Calls the GitHub Contents API to enumerate the directory.  Each entry is
    a dict ``{"name", "download_url", "size"}``.  Result is cached in
    process memory for the life of the interpreter.

    If the API is unreachable (rate-limited, offline, blocked), falls back
    to :data:`_JABREF_FALLBACK_CSVS` so the L2 lookup still works against
    the most-recently-known file set.
    """
    global _jabref_csv_list
    if _jabref_csv_list is not None:
        return _jabref_csv_list
    with _jabref_csv_lock:
        if _jabref_csv_list is not None:
            return _jabref_csv_list
        try:
            resp = httpx.get(
                _JABREF_API_URL,
                headers={
                    "User-Agent": _HTTP_HEADERS["User-Agent"],
                    "Accept": "application/vnd.github+json",
                },
                timeout=15.0,
            )
            if resp.status_code == 200:
                entries: list[dict[str, object]] = []
                for item in resp.json():
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "file":
                        continue
                    name = item.get("name", "")
                    if not name.endswith(".csv"):
                        continue
                    entries.append({
                        "name": name,
                        "download_url": item.get("download_url", ""),
                        "size": item.get("size", 0),
                    })
                if entries:
                    _jabref_csv_list = entries
                    logger.info(
                        "JabRef: discovered %d CSVs via GitHub API", len(entries),
                    )
                    return _jabref_csv_list
                logger.warning(
                    "JabRef: API returned no .csv files; using fallback list",
                )
            else:
                logger.warning(
                    "JabRef Contents API returned HTTP %d; using fallback list",
                    resp.status_code,
                )
        except Exception as exc:
            logger.warning(
                "JabRef Contents API unreachable (%s); using fallback list", exc,
            )
        # Fallback: build the same dict shape from the hardcoded list
        _jabref_csv_list = [
            {
                "name": name,
                "download_url": f"{_JABREF_RAW_BASE}/{name}",
                "size": 0,
            }
            for name in _JABREF_FALLBACK_CSVS
        ]
        return _jabref_csv_list


# Public alias — also accessible as ``src.refs.list_jabref_csvs``
list_jabref_csvs = _list_jabref_csvs

# Public snapshot of the offline-fallback file list.  Updated whenever the
# GitHub API is reachable; otherwise the loader pins the most-recently-
# known good snapshot.  Useful for tests and for the package's public API.
JABREF_FALLBACK_NAMES: list[str] = list(_JABREF_FALLBACK_CSVS)


def _parse_jabref_csv(text: str, combined: dict[str, str]) -> int:
    """Parse one JabRef ``full;abbrev`` CSV and merge into *combined*.

    Returns the number of new entries added.
    """
    added = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle both `;` and tab separators — some JabRef files use tabs.
        for sep in (";", "\t"):
            if sep in line:
                parts = line.split(sep, 1)
                break
        else:
            parts = line.split(";", 1)
        if len(parts) < 2:
            continue
        full = parts[0].strip().lower()
        iso4 = parts[1].strip()
        if full and iso4 and full not in combined:
            combined[full] = iso4
            added += 1
    return added


def _load_jabref() -> None:
    """Populate :data:`_jabref_map`. Thread-safe; idempotent.

    Discovery: queries the GitHub Contents API for the current set of CSV
    files (rather than relying on a hand-maintained list — the repo has
    been seen to remove files, e.g. ``journal_abbreviations_aps.csv``).
    Falls back to a hardcoded snapshot of the live list when the API is
    unreachable, so the L2 lookup still works offline.
    """
    global _jabref_map
    if _jabref_map is not None:
        return
    if os.environ.get("AIAGENT_DISABLE_JABREF", "").lower() in ("1", "true", "yes"):
        _jabref_map = {}
        return
    with _jabref_lock:
        if _jabref_map is not None:
            return
        csvs = _list_jabref_csvs()
        combined: dict[str, str] = {}
        for entry in csvs:
            name = entry.get("name", "")
            url = entry.get("download_url", "")
            if not url:
                continue
            text = _download_text(url)
            if not text:
                logger.debug("JabRef: empty body for %s", name)
                continue
            added = _parse_jabref_csv(text, combined)
            logger.debug("JabRef: %d new entries from %s", added, name)
        if combined:
            logger.info(
                "JabRef map built: %d entries from %d CSVs",
                len(combined), len(csvs),
            )
        else:
            logger.warning("JabRef: all downloads failed — L2 lookup disabled")
        _jabref_map = combined


# ─────────────────────────────────────────────────────────────────────────────
# LTWA loader and applier
# ─────────────────────────────────────────────────────────────────────────────

def _load_ltwa() -> None:
    """Populate :data:`_ltwa_exact` / :data:`_ltwa_prefix`. Idempotent."""
    global _ltwa_exact, _ltwa_prefix
    if _ltwa_exact is not None:
        return
    if os.environ.get("AIAGENT_DISABLE_LTWA", "").lower() in ("1", "true", "yes"):
        _ltwa_exact, _ltwa_prefix = {}, []
        return
    with _ltwa_lock:
        if _ltwa_exact is not None:
            return
        text = _download_text(_LTWA_URL, encoding="utf-8-sig")
        if not text:
            logger.warning("LTWA download failed — L2.5 disabled")
            _ltwa_exact, _ltwa_prefix = {}, []
            return
        exact: dict[str, str] = {}
        prefix: list[tuple[str, str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.upper().startswith("WORD"):
                continue
            parts = line.split(";")
            if len(parts) < 3:
                continue
            word_raw = parts[0].strip()
            langs = {l.strip().lower() for l in parts[1].split(",")}
            abbrev = parts[2].strip()
            if not word_raw or not abbrev:
                continue
            if not (langs & _LTWA_KEEP_LANGS):
                continue
            if word_raw.endswith("*"):
                pfx = word_raw[:-1].lower()
                if pfx:
                    prefix.append((pfx, abbrev))
            else:
                w = word_raw.lower()
                # First-seen wins (file is ordered; earlier = higher priority).
                if w not in exact:
                    exact[w] = abbrev
        # Sort prefix list longest-first for greedy matching.
        prefix.sort(key=lambda x: -len(x[0]))
        _ltwa_exact = exact
        _ltwa_prefix = prefix
        logger.info("LTWA loaded: %d exact, %d prefix entries", len(exact), len(prefix))


def _abbreviate_via_ltwa(name: str) -> str:
    """Apply LTWA word-by-word abbreviation to *name*; pass through on failure."""
    # Snapshot module-level refs (defends against concurrent reload).
    local_exact = _ltwa_exact
    local_prefix = _ltwa_prefix
    if not local_exact:
        return name

    working = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
    words = working.split()
    result: list[str] = []

    for word in words:
        w_lower = word.lower()

        # 1. Exact match in LTWA
        if w_lower in local_exact:
            abbrev = local_exact[w_lower]
            if abbrev.lower() != "n.a.":
                result.append(abbrev)
            continue

        # 2. Prefix match (longest first)
        matched = False
        for pfx, abbrev in (local_prefix or []):
            if w_lower.startswith(pfx):
                if abbrev.lower() != "n.a.":
                    result.append(abbrev)
                matched = True
                break
        if matched:
            continue

        # 3. Fallback stop-word omission
        if w_lower in _ISO4_OMIT:
            continue

        # 4. Keep unchanged (proper noun, digit, already abbreviated)
        result.append(word)

    abbreviated = " ".join(result).strip()
    return abbreviated if abbreviated and abbreviated != working else name


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def normalize_journal(full_name: str) -> str:
    """Return the JACoW-required ISO 4 abbreviation for *full_name*.

    The cascade tries each tier and returns the first hit:

    1. L1   — :data:`JACOW_ABBREVS` (always available).
    2. L2   — JabRef combined list  (lazy network load, in-memory cache).
    3. L2.5 — ISSN LTWA word-by-word (lazy network load).
    4. L3   — pass-through.

    Leading ``"The "`` is stripped before lookup. Matching is case-insensitive.
    Returns an empty string when *full_name* is a clearly invalid placeholder
    such as ``"Conf."`` / ``"Proc."``.
    """
    if not full_name:
        return full_name

    # Strip embedded URLs before lookup
    full_name = re.sub(r"https?://\S+", "", full_name).strip().rstrip(",").strip()

    # Strip trailing year-month suffix that NLP parsers sometimes absorb
    full_name = re.sub(
        r"\s+(?:19|20)\d{2}[–\-]?\w*[,.]?\s*$", "", full_name,
    ).strip()
    full_name = re.sub(
        r"\s+(?:19|20)\d{2}\s+\d{1,4}:\d{1,4}\s*$", "", full_name,
    ).strip()

    # Reject tokens that are clearly not journal names
    _invalid = {
        "conf.", "proc.", "process.", "assoc.", "technol.",
        "conf", "proc", "proceedings",
    }
    if full_name.strip().lower().rstrip(".") in {x.rstrip(".") for x in _invalid}:
        return ""

    key = re.sub(r"^the\s+", "", full_name.strip().lower())
    key = re.sub(r"\s+", " ", key)

    # ── L1 ────────────────────────────────────────────────────────────────
    if key in JACOW_ABBREVS:
        return JACOW_ABBREVS[key]
    for long_name, abbrev in JACOW_ABBREVS.items():
        # Prefix match requires (a) the L1 key is multi-word and (b) a word
        # boundary follows so "physical review" doesn't match "physical chemistry".
        if (
            " " in long_name
            and key.startswith(long_name)
            and len(key) > len(long_name)
            and key[len(long_name)] == " "
        ):
            return abbrev

    # ── L2 ────────────────────────────────────────────────────────────────
    _load_jabref()
    local_jabref = _jabref_map
    if local_jabref:
        if key in local_jabref:
            logger.debug('JabRef L2: "%s" → "%s"', full_name, local_jabref[key])
            return local_jabref[key]
        for long_name, abbrev in local_jabref.items():
            if (
                key.startswith(long_name)
                and len(long_name) > 10
                and (len(key) == len(long_name) or key[len(long_name)] == " ")
            ):
                logger.debug('JabRef L2 prefix: "%s" → "%s"', full_name, abbrev)
                return abbrev

    # ── L2.5 ──────────────────────────────────────────────────────────────
    _load_ltwa()
    if _ltwa_exact:
        ltwa_result = _abbreviate_via_ltwa(full_name)
        if ltwa_result and ltwa_result != full_name:
            logger.debug('LTWA L2.5: "%s" → "%s"', full_name, ltwa_result)
            return ltwa_result

    # ── L3 ────────────────────────────────────────────────────────────────
    logger.debug('normalize_journal: no match for "%s"', full_name)
    return full_name
