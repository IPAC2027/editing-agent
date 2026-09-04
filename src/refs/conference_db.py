"""JACoW conference metadata connector.

Provides authoritative location / month / publisher metadata for JACoW conference
series (IPAC, LINAC, FEL, SRF, ICALEPCS, …). Migrated from the v1.0.0 standalone
formatter (sections 0d–0e).

Lookup tiers:

1. Hardcoded :data:`_JACOW_CONF_TABLE` (~70 events, no network).
2. Live fetch of ``jacow-events.bib`` from github.com/zhichu/JACoW-bib
   (~300 events, in-memory cached for the process).

The connector exposes both a no-side-effect query API
(:meth:`JacoWConnector.lookup`, :meth:`JacoWConnector.is_jacow_series`) and a
record-completion helper (:meth:`JacoWConnector.complete_record`) that fills
missing fields and appends a :class:`FieldCompletion` log entry for each.

Adaptations from the standalone script:
- HTTP client is :mod:`httpx` (matches the rest of the package).
- No SqliteCache wired in this Tier-1 pass — the bib download is cached in
  process memory; persistent caching can be layered on later.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# FieldCompletion — record of one filled-in metadata field
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FieldCompletion:
    """One auto-completed field (provenance for the editor)."""

    field: str
    value: str
    source: str
    timestamp: str
    cached: bool = False
    confidence: float = 1.0


def _now_ts() -> str:
    """Current UTC time as an ISO-8601 string (``YYYY-MM-DDTHH:MM:SSZ``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# Venue parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

# US/Canadian state and province abbreviations seen in JACoW venue strings.
_VENUE_STATE_PROVS: frozenset = frozenset({
    # US states
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
    # Canadian provinces
    "BC", "ON", "QC", "AB", "MB", "SK", "NS", "NB", "PE", "NL",
})

_JACOW_MONTH_NAMES: list[str] = [
    "Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.",
    "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.",
]


def _parse_jacow_venue(venue: str) -> tuple[str, str]:
    """Parse a JACoW venue string into ``(city, country)``.

    Handles patterns:
      ``"City, Country"``
      ``"City, State, Country"``           (US/CA state abbreviations)
      ``"Facility, City, State, Country"``
      ``"Facility, City, Country"``
    """
    venue = re.sub(r"\s+", " ", venue).strip()
    venue = re.sub(r"\b([A-Z])\.([A-Z])\.\s*", r"\1\2 ", venue).strip()

    parts = [p.strip() for p in venue.split(",") if p.strip()]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""

    country = parts[-1]

    # If the second-to-last part is a recognised state/province abbreviation,
    # the city is the part before it.
    if parts[-2] in _VENUE_STATE_PROVS:
        city = parts[-3] if len(parts) >= 3 else parts[-2]
    else:
        city = parts[-2]
    return city, country


def _parse_jacow_events_bib(text: str) -> dict[str, dict[str, dict]]:
    """Parse a JACoW ``@xdata`` BibTeX file into the table layout.

    Returns ``{series_lower: {year_str: {'city', 'country', 'month', 'proc',
    'isbn', 'issn', 'pubstate' (opt)}}}``.
    """
    result: dict[str, dict[str, dict]] = {}

    for block_m in re.finditer(
        r"@xdata\{(\w+),\s*((?:[^{}@]|\{[^{}]*\})*)\}",
        text,
        re.DOTALL,
    ):
        key = block_m.group(1)
        content = block_m.group(2)

        fields: dict[str, str] = {}
        for fld_m in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", content):
            fields[fld_m.group(1).lower()] = re.sub(
                r"\s+", " ", fld_m.group(2),
            ).strip()

        series = fields.get("shortseries", "").strip().lower()
        if not series:
            m = re.match(r"^([A-Za-z]+)\d{4}$", key)
            series = m.group(1).lower() if m else ""
        if not series:
            continue

        year = ""
        month = ""
        eventdate = fields.get("eventdate", "")
        if eventdate:
            em = re.match(r"(\d{4})-(\d{2})", eventdate)
            if em:
                year = em.group(1)
                mn = int(em.group(2))
                if 1 <= mn <= 12:
                    month = _JACOW_MONTH_NAMES[mn - 1]

        if not year:
            km = re.search(r"(\d{4})$", key)
            year = km.group(1) if km else ""
        if not year:
            continue

        venue = fields.get("venue", "")
        city, country = _parse_jacow_venue(venue) if venue else ("", "")

        proc = fields.get("indextitle") or key

        entry: dict[str, str] = {"proc": proc}
        if city:
            entry["city"] = city
        if country:
            entry["country"] = country
        if month:
            entry["month"] = month
        if fields.get("isbn"):
            entry["isbn"] = fields["isbn"]
        if fields.get("issn"):
            entry["issn"] = fields["issn"]
        pubstate = fields.get("pubstate", "")
        if pubstate:
            entry["pubstate"] = pubstate

        result.setdefault(series, {})[year] = entry

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Hardcoded fallback table (always available, even without network)
# ─────────────────────────────────────────────────────────────────────────────

_JACOW_CONF_TABLE: dict[str, dict[str, dict]] = {
    "ipac": {
        "2019": {"city": "Melbourne",    "country": "Australia",    "month": "May",  "proc": "IPAC2019"},
        "2021": {"city": "Campinas",     "country": "Brazil",       "month": "May",  "proc": "IPAC2021"},
        "2022": {"city": "Bangkok",      "country": "Thailand",     "month": "Jun.", "proc": "IPAC2022"},
        "2023": {"city": "Venice",       "country": "Italy",        "month": "May",  "proc": "IPAC2023"},
        "2024": {"city": "Nashville",    "country": "USA",          "month": "May",  "proc": "IPAC2024"},
        "2025": {"city": "Taipei",       "country": "Taiwan",       "month": "Jun.", "proc": "IPAC2025"},
    },
    "linac": {
        "2018": {"city": "Beijing",      "country": "China",        "month": "Sep.", "proc": "LINAC2018"},
        "2022": {"city": "Liverpool",    "country": "UK",           "month": "Aug.", "proc": "LINAC2022"},
        "2024": {"city": "Chicago",      "country": "USA",          "month": "Aug.", "proc": "LINAC2024"},
    },
    "fel": {
        "2019": {"city": "Hamburg",      "country": "Germany",      "month": "Aug.", "proc": "FEL2019"},
        "2022": {"city": "Trieste",      "country": "Italy",        "month": "Aug.", "proc": "FEL2022"},
        "2023": {"city": "Padova",       "country": "Italy",        "month": "Aug.", "proc": "FEL2023"},
        "2024": {"city": "Nara",         "country": "Japan",        "month": "Aug.", "proc": "FEL2024"},
    },
    "ibic": {
        "2019": {"city": "Malmö",        "country": "Sweden",       "month": "Sep.", "proc": "IBIC2019"},
        "2021": {"city": "Pohang",       "country": "South Korea",  "month": "Sep.", "proc": "IBIC2021"},
        "2022": {"city": "Kraków",       "country": "Poland",       "month": "Sep.", "proc": "IBIC2022"},
        "2023": {"city": "Saskatoon",    "country": "Canada",       "month": "Sep.", "proc": "IBIC2023"},
        "2024": {"city": "Goyang",       "country": "South Korea",  "month": "Sep.", "proc": "IBIC2024"},
    },
    "icalepcs": {
        "2019": {"city": "New York City", "country": "USA",         "month": "Oct.", "proc": "ICALEPCS2019"},
        "2021": {"city": "Shanghai",     "country": "China",        "month": "Oct.", "proc": "ICALEPCS2021"},
        "2023": {"city": "Cape Town",    "country": "South Africa", "month": "Oct.", "proc": "ICALEPCS2023"},
    },
    "medsi": {
        "2020": {"city": "Chicago",      "country": "USA",          "month": "Jul.", "proc": "MEDSI2020"},
        "2022": {"city": "Taipei",       "country": "Taiwan",       "month": "Sep.", "proc": "MEDSI2022"},
        "2024": {"city": "London",       "country": "UK",           "month": "Jun.", "proc": "MEDSI2024"},
    },
    "cool": {
        "2019": {"city": "Novosibirsk",  "country": "Russia",       "month": "Sep.", "proc": "COOL2019"},
        "2023": {"city": "Darmstadt",    "country": "Germany",      "month": "Oct.", "proc": "COOL2023"},
    },
    "cyclotrons": {
        "2019": {"city": "Cape Town",    "country": "South Africa", "month": "Sep.", "proc": "Cyclotrons2019"},
        "2022": {"city": "Beijing",      "country": "China",        "month": "Dec.", "proc": "Cyclotrons2022"},
    },
    "eaac": {
        "2019": {"city": "Elba Island",  "country": "Italy",        "month": "Sep.", "proc": "EAAC2019"},
        "2021": {"city": "Ischia",       "country": "Italy",        "month": "Oct.", "proc": "EAAC2021"},
        "2023": {"city": "Elba Island",  "country": "Italy",        "month": "Sep.", "proc": "EAAC2023"},
    },
    "icap": {
        "2018": {"city": "Key West",     "country": "USA",          "month": "Oct.", "proc": "ICAP2018"},
        "2022": {"city": "Córdoba",      "country": "Argentina",    "month": "Sep.", "proc": "ICAP2022"},
    },
    "hb": {
        "2018": {"city": "Daejeon",      "country": "South Korea",  "month": "Jun.", "proc": "HB2018"},
        "2021": {"city": "Batavia",      "country": "USA",          "month": "Oct.", "proc": "HB2021"},
        "2023": {"city": "Geneva",       "country": "Switzerland",  "month": "Oct.", "proc": "HB2023"},
    },
    "srf": {
        "2019": {"city": "Dresden",      "country": "Germany",      "month": "Jun.", "proc": "SRF2019"},
        "2021": {"city": "East Lansing", "country": "USA",          "month": "Jun.", "proc": "SRF2021"},
        "2023": {"city": "Grand Rapids", "country": "USA",          "month": "Jun.", "proc": "SRF2023"},
    },
    "nac": {
        "2021": {"city": "Cape Town",    "country": "South Africa", "month": "Nov.", "proc": "NAC2021"},
        "2022": {"city": "Gqeberha",     "country": "South Africa", "month": "Oct.", "proc": "NAC2022"},
    },
    "pcapac": {
        "2018": {"city": "Hsinchu",      "country": "Taiwan",       "month": "Dec.", "proc": "PCaPAC2018"},
        "2022": {"city": "Lanzhou",      "country": "China",        "month": "Nov.", "proc": "PCaPAC2022"},
    },
    "fls": {
        "2018": {"city": "Shanghai",     "country": "China",        "month": "Mar.", "proc": "FLS2018"},
        "2022": {"city": "Lucerne",      "country": "Switzerland",  "month": "Sep.", "proc": "FLS2022"},
    },
    "napac": {
        "2019": {"city": "Lansing",      "country": "USA",          "month": "Sep.", "proc": "NAPAC2019"},
        "2022": {"city": "Albuquerque",  "country": "USA",          "month": "Aug.", "proc": "NAPAC2022"},
    },
    "hiat": {
        "2019": {"city": "Yokohama",     "country": "Japan",        "month": "Jun.", "proc": "HIAT2019"},
        "2022": {"city": "Darmstadt",    "country": "Germany",      "month": "Jun.", "proc": "HIAT2022"},
    },
    "pac": {
        "2001": {"city": "Chicago",      "country": "USA",          "month": "Jun.", "proc": "PAC2001"},
    },
    "apac": {
        "2007": {"city": "Indore",       "country": "India",        "month": "Jan.", "proc": "APAC2007"},
    },
}

# All known JACoW conference series (for is_jacow_series check).
_JACOW_SERIES: frozenset = frozenset(_JACOW_CONF_TABLE.keys()) | frozenset({
    # Main accelerator conferences
    "pac", "apac", "rupac", "epac", "ipac", "napac",
    # Linac / RF
    "linac", "srf",
    # FEL / photon sources
    "fel", "fls",
    # Beam instrumentation / diagnostics
    "ibic", "dipac", "biwb", "biw",
    # Controls
    "icalepcs", "pcapac",
    # Beam dynamics / high-intensity
    "hb", "hbeb",
    # Cooling
    "cool",
    # Cyclotrons / ion sources
    "cyclotrons", "ecris",
    # Synchrotron radiation / X-ray optics
    "medsi", "xb", "hf",
    # Electron–ion and advanced accelerators
    "eic", "erl", "eaac", "eefact",
    # Specialised workshops
    "icap", "hiat", "sofe",
    # Broader/historical
    "nac", "nss", "psc", "blt", "iwbs", "tul",
    # Regional
    "nb", "sap", "ecloud",
})


# ─────────────────────────────────────────────────────────────────────────────
# Remote source
# ─────────────────────────────────────────────────────────────────────────────

_JACOW_EVENTS_BIB_URL = (
    "https://raw.githubusercontent.com/zhichu/JACoW-bib/"
    "refs/heads/IPAC2026/jacow-events.bib"
)

_jacow_fetch_lock: threading.Lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Connector
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _ConnectorState:
    """Mutable per-process cache; one instance shared across :class:`JacoWConnector` callers."""

    db: dict[str, dict[str, dict]] = field(
        default_factory=lambda: {k: dict(v) for k, v in _JACOW_CONF_TABLE.items()},
    )
    loaded_remote: bool = False


class JacoWConnector:
    """Authoritative JACoW conference metadata.

    Methods
    -------
    lookup(acronym, year) -> dict | None
        Returns ``{'city', 'country', 'month', 'proc', ...}`` for a known event,
        or ``None`` if not found.
    is_jacow_series(acronym) -> bool
        ``True`` if *acronym* belongs to a known JACoW conference series.
    complete_record(rec, field_log, ts) -> rec
        Fills missing ``city``/``country``/``month``/``isbn``/``issn`` from the
        DB, logging each completion into *field_log* with confidence ``1.0``.
    """

    def __init__(self, *, allow_network: bool = True) -> None:
        self._state = _ConnectorState()
        self._allow_network = allow_network

    # ── internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _norm_acr(acronym: str) -> str:
        """Lowercase, strip trailing year digits, handle ``IPAC2023`` style."""
        a = re.sub(r"\s*\d{2,4}$", "", acronym.strip().lower())
        return re.sub(r"\d+$", "", a)

    def _maybe_fetch_remote(self) -> None:
        """Populate :attr:`_state.db` from ``jacow-events.bib`` (double-checked locking)."""
        if self._state.loaded_remote:
            return
        if not self._allow_network:
            self._state.loaded_remote = True
            return
        with _jacow_fetch_lock:
            if self._state.loaded_remote:
                return
            self._state.loaded_remote = True
            try:
                resp = httpx.get(
                    _JACOW_EVENTS_BIB_URL,
                    headers={"User-Agent": "aiagent-formatter/0.1"},
                    timeout=20.0,
                )
                if resp.status_code != 200:
                    logger.warning(
                        "JacoWConnector: jacow-events.bib HTTP %d — using hardcoded DB only",
                        resp.status_code,
                    )
                    return
                text = resp.content.decode("utf-8", errors="replace")
            except Exception as exc:
                logger.warning(
                    "JacoWConnector: jacow-events.bib unavailable (%s) — using hardcoded DB only",
                    exc,
                )
                return
            try:
                remote = _parse_jacow_events_bib(text)
            except Exception as exc:
                logger.warning("JacoWConnector: jacow-events.bib parse error: %s", exc)
                return
            if remote:
                for series, years in remote.items():
                    self._state.db.setdefault(series, {}).update(years)
                total = sum(len(v) for v in remote.values())
                logger.info(
                    "JacoWConnector: loaded %d events across %d series from jacow-events.bib",
                    total,
                    len(remote),
                )

    # ── public API ──────────────────────────────────────────────────────

    def lookup(self, acronym: str, year: str) -> Optional[dict]:
        """Return metadata dict for ``(acronym, year)``, or ``None``."""
        self._maybe_fetch_remote()
        acr = self._norm_acr(acronym)
        return self._state.db.get(acr, {}).get(str(year).strip())

    def is_jacow_series(self, acronym: str) -> bool:
        """Return ``True`` if *acronym* is a recognised JACoW series."""
        self._maybe_fetch_remote()
        acr = self._norm_acr(acronym)
        return acr in _JACOW_SERIES or acr in self._state.db

    def complete_record(
        self,
        rec: dict,
        field_log: list[FieldCompletion],
        ts: str | None = None,
    ) -> dict:
        """Fill missing city/country/month/isbn/issn from the JACoW DB.

        Logs each completion into *field_log* (confidence = 1.0). Returns the
        possibly modified record. ``rec`` is **not** mutated in place — a shallow
        copy is returned to match the standalone-script semantics.
        """
        timestamp = ts or _now_ts()
        conf = rec.get("conference", "")
        year = rec.get("year", "")
        if not conf or not year:
            return rec
        meta = self.lookup(conf, year)
        if not meta:
            return rec
        out = dict(rec)
        for field_name in ("city", "country", "month", "isbn", "issn"):
            if meta.get(field_name) and not out.get(field_name):
                out[field_name] = meta[field_name]
                field_log.append(FieldCompletion(
                    field=field_name,
                    value=meta[field_name],
                    source="JACoW-DB",
                    timestamp=timestamp,
                    cached=True,
                    confidence=1.0,
                ))
                logger.debug(
                    "JACoW-DB filled %s=%s for %s %s",
                    field_name, meta[field_name], conf, year,
                )
        return out
