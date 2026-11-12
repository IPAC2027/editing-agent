"""A journal's name as Appendix B prints it: its ISO 4 abbreviation, Annex C's first.

In order:

1. Annex C of the JACoW style guide (the journals JACoW lists), by full name or
   abbreviation, ignoring case, full stops and "&"/"and";
2. the usual other ways of writing those journals ("Phys. Rev. ST Accel. Beams",
   "PRAB", "NIM A", "Nucl. Instr. Meth. A", "JINST");
3. Annex C again, allowing a typo (a letter wrong, missing or swapped);
4. abbrevIso (https://abbreviso.toolforge.org), the ISO 4 tool Appendix B cites [13];
5. JabRef's journal lists (18 000 journals), for when abbrevIso does not answer;
6. the journal's short title in the DOI's Crossref record.

A name none of these knows is kept as written and reported.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import re
import threading
import time
import urllib.parse
from pathlib import Path

_ANNEX_C_FILE = (Path(__file__).resolve().parents[1] / "knowledge" /
                 "jacow-paper-formatting-skill" / "references" / "journal-abbreviations.md")

#: Other ways of writing journals that Annex C lists (key -> Annex C abbreviation).
_VARIANTS = {
    "phys rev st accel beams": "Phys. Rev. Spec. Top. Accel. Beams",
    "phys rev stab": "Phys. Rev. Spec. Top. Accel. Beams",
    "prstab": "Phys. Rev. Spec. Top. Accel. Beams",
    "pr stab": "Phys. Rev. Spec. Top. Accel. Beams",
    "phys rev spec top accel beams": "Phys. Rev. Spec. Top. Accel. Beams",
    "physical review special topics accelerators and beams": "Phys. Rev. Spec. Top. Accel. Beams",
    "physical review special topics": "Phys. Rev. Spec. Top. Accel. Beams",
    "phys rev special topics accelerators and beams": "Phys. Rev. Spec. Top. Accel. Beams",
    "prab": "Phys. Rev. Accel. Beams", "pr ab": "Phys. Rev. Accel. Beams",
    "phys rev ab": "Phys. Rev. Accel. Beams", "phys rev accel beam": "Phys. Rev. Accel. Beams",
    "phys rev accelerators and beams": "Phys. Rev. Accel. Beams",
    "prl": "Phys. Rev. Lett.", "phys rev letters": "Phys. Rev. Lett.",
    "physical review letter": "Phys. Rev. Lett.",
    "nim a": "Nucl. Instrum. Methods Phys. Res. A", "nima": "Nucl. Instrum. Methods Phys. Res. A",
    "nim b": "Nucl. Instrum. Methods Phys. Res. B", "nimb": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instr meth a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instr meth phys res a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instr and meth a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instr and meth in phys res a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instrum meth a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instrum methods a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instrum meth phys res a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instrum methods phys res sect a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instrum methods phys res section a": "Nucl. Instrum. Methods Phys. Res. A",
    "nucl instr meth b": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instrum meth b": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instrum methods b": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instrum methods phys res sect b": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instrum meth phys res b": "Nucl. Instrum. Methods Phys. Res. B",
    "nucl instr meth": "Nucl. Instrum. Methods", "nucl instrum meth": "Nucl. Instrum. Methods",
    "nuclear instruments and methods in physics research a":
        "Nucl. Instrum. Methods Phys. Res. A",
    "nuclear instruments and methods in physics research b":
        "Nucl. Instrum. Methods Phys. Res. B",
    "nuclear instruments and methods in physics research section a":
        "Nucl. Instrum. Methods Phys. Res. A",
    "nuclear instruments and methods in physics research section b":
        "Nucl. Instrum. Methods Phys. Res. B",
    "jinst": "J. Instrum.", "j inst": "J. Instrum.", "journal of instrumentation": "J. Instrum.",
    "rev sci instr": "Rev. Sci. Instrum.", "rsi": "Rev. Sci. Instrum.",
    "review of scientific instruments": "Rev. Sci. Instrum.",
    "ieee trans nucl sci": "IEEE Trans. Nucl. Sci.",
    "ieee trans appl supercond": "IEEE Trans. Appl. Supercond.",
    "j synchrotron rad": "J. Synchrotron Radiat.", "j synchrotron radiation": "J. Synchrotron Radiat.",
    "nature comm": "Nat. Commun.", "nat comm": "Nat. Commun.",
    "nature communications": "Nat. Commun.", "nature physics": "Nat. Phys.",
    "nature photonics": "Nat. Photonics", "nat photon": "Nat. Photonics",
    "supercond sci tech": "Supercond. Sci. Technol.",
    "phys plasmas": "Phys. Plasmas", "physics of plasmas": "Phys. Plasmas",
    "opt express": "Opt. Express", "optics express": "Opt. Express",
    "science advances": "Sci. Adv.", "sci adv": "Sci. Adv.",
}

#: Where Annex C as printed is not ISO 4, which the guide says is mandatory ("the official
#: abbreviation of the journal, as mandated by the ISO 4 standard"): LTWA abbreviates
#: "Applied" as "Appl.", "Magnetics" as "Magn.", "Superconductivity" as "Supercond.",
#: "Communications" as "Commun."; "Plasmas" keeps its "s". Delete a line to follow Annex C.
ANNEX_C_ERRATA = {
    "App. Phys. A": "Appl. Phys. A", "App. Phys. B": "Appl. Phys. B",
    "App. Phys. B: Lasers Opt.": "Appl. Phys. B: Lasers Opt.",
    "App. Phys. Express": "Appl. Phys. Express", "App. Phys. Lett.": "Appl. Phys. Lett.",
    "App. Phys. Res.": "Appl. Phys. Res.", "App. Phys. Rev.": "Appl. Phys. Rev.",
    "App. Supercond.": "Appl. Supercond.", "IEEE Trans. Magnetics": "IEEE Trans. Magn.",
    "J. Superconductivity": "J. Supercond.", "Opt. Communic.": "Opt. Commun.",
    "Phys. Plasma": "Phys. Plasmas",
}

_lock = threading.Lock()
_annex: dict[str, str] | None = None
_annex_abbrevs: set[str] = set()


def _key(name: str) -> str:
    name = re.sub(r"<[^>]+>", "", name)
    name = name.replace("&", " and ").replace("–", "-").lower()
    name = re.sub(r"^\s*the\s+", "", name)
    name = re.sub(r"[.,:;()\"“”']", " ", name)
    name = re.sub(r"\s*-\s*", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def annex_c() -> dict[str, str]:
    """Annex C: key of the full name or of the abbreviation -> the abbreviation."""
    global _annex, _annex_abbrevs
    with _lock:
        if _annex is not None:
            return _annex
        table: dict[str, str] = {}
        try:
            lines = _ANNEX_C_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
            if not m or m.group(1) in ("Abbreviation",) or set(m.group(1)) <= {"-"}:
                continue
            printed, full = m.group(1).strip(), m.group(2).strip()
            abbreviation = ANNEX_C_ERRATA.get(printed, printed)
            _annex_abbrevs.add(abbreviation)
            for name in (full, full.split(":")[0], abbreviation, printed):
                table.setdefault(_key(name), abbreviation)
        for k, v in _VARIANTS.items():
            table.setdefault(k, v)
        _annex = table
        return table


def in_annex_c(abbreviation: str) -> bool:
    annex_c()
    return abbreviation in _annex_abbrevs


# ---------------------------------------------------------------------------
# Online and offline ISO 4 sources
# ---------------------------------------------------------------------------

def _fetch_text(url: str, service: str) -> str | None:
    """A cached GET returning text, or None when the service does not answer."""
    import httpx

    from src.lookup_status import STATUS
    from src.refcheck import doi as registry

    hit = registry.CACHE.get(url)
    if hit:
        return hit["body"] if hit["status"] == 200 else ""
    with STATUS.attempt(service) as outcome:
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "jacow-prescreen"})
        except Exception as exc:  # noqa: BLE001
            outcome.failed(f"{type(exc).__name__}: {exc}")
            return None
        if resp.status_code not in (200, 404):
            outcome.failed(f"HTTP {resp.status_code}")
            return None
        outcome.succeeded()
    body = resp.text if resp.status_code == 200 else ""
    registry.CACHE.put(url, resp.status_code, body)
    return body


def abbreviso(name: str) -> str | None:
    """abbrevIso's ISO 4 abbreviation of *name*; "" if it has none; None with no answer."""
    url = "https://abbreviso.toolforge.org/a/" + urllib.parse.quote(name.strip(), safe="")
    text = _fetch_text(url, "abbrevIso")
    if text is None:
        return None
    text = text.strip()
    if not text or len(text) > 2 * len(name) + 10 or "<" in text:
        return ""
    return text


_JABREF = ("general", "ieee", "acs", "mechanical")
_jabref: dict[str, str] | None = None
_jabref_abbrevs: set[str] = set()


def _jabref_table() -> dict[str, str]:
    """JabRef's lists, full name key -> abbreviation (downloaded once, kept 90 days)."""
    global _jabref, _jabref_abbrevs
    with _lock:
        if _jabref is not None:
            return _jabref
        from src.references import cache_dir
        path = cache_dir() / "jabref_journals.json"
        table: dict[str, str] = {}
        try:
            if time.time() - path.stat().st_mtime < 90 * 86400:
                table = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            table = {}
        if not table:
            for name in _JABREF:
                url = ("https://raw.githubusercontent.com/JabRef/abbrv.jabref.org/main/journals/"
                       f"journal_abbreviations_{name}.csv")
                text = _fetch_text(url, "JabRef")
                if not text:
                    continue
                for row in csv.reader(io.StringIO(text)):
                    if len(row) >= 2 and row[0] and row[1]:
                        table.setdefault(_key(row[0]), row[1].strip())
            if table:
                try:
                    path.write_text(json.dumps(table), encoding="utf-8")
                except OSError:
                    pass
        _jabref = table
        _jabref_abbrevs = set(table.values())
        return table


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------

_MINOR = {"of", "and", "on", "in", "the", "for", "to", "a", "an", "&", "at", "with", "de", "la"}


def _title_cased(name: str) -> str:
    """"IEEE transactions on neural networks" -> "IEEE Transactions on Neural Networks"."""
    words = name.split()
    return " ".join(w if (w.lower() in _MINOR and i) or not w[:1].islower() else
                    w[:1].upper() + w[1:] for i, w in enumerate(words))


def looks_abbreviated(name: str) -> bool:
    return bool(re.search(r"\b[A-Z][a-z]{0,8}\.(?:\s|$)", name)) or name.isupper()


def abbreviate(name: str, *, record_short: str = "", online: bool = True
               ) -> tuple[str, str, str]:
    """(the journal as Appendix B prints it, where that came from, a note for the editor)."""
    written = re.sub(r"\s+", " ", name).strip(" ,;")
    written = re.sub(r"^(?:in|In)\s+", "", written)
    if not looks_abbreviated(written):
        written = written.rstrip(".")
    if not written:
        return "", "", ""
    table = annex_c()
    key = _key(written)
    if key in table:
        return table[key], "Annex C", ""
    # "Nuclear Instruments and Methods in Physics Research Section A: Accelerators, …"
    short_key = _key(re.split(r":\s", written)[0])
    if short_key in table:
        return table[short_key], "Annex C", ""
    close = [c for c in difflib.get_close_matches(key, list(table), n=3, cutoff=0.9)
             if abs(len(c) - len(key)) <= 3]
    if close and (len(close) == 1 or table[close[0]] == table[close[1]]) and len(key) > 8:
        return table[close[0]], "Annex C", f"“{written}” read as {table[close[0]]} (a typo)"
    abbreviated = looks_abbreviated(written)
    jabref = _jabref_table() if online else {}
    if abbreviated:
        # Already abbreviated: abbrevIso would garble it ("Prog, Theor, Exp, Phys").
        if written in _jabref_abbrevs:
            return written, "JabRef", ""
        if key in jabref:
            return jabref[key], "JabRef", ""
        if record_short:
            return record_short, "Crossref", ""
    elif online:
        answer = abbreviso(_title_cased(written))
        if answer and "," not in answer.replace(written, ""):
            return answer, "abbrevIso", ""
    if key in jabref:
        return jabref[key], "JabRef", ""
    if record_short:
        return record_short, "Crossref", ""
    if looks_abbreviated(written):
        return written, "", (f"journal “{written}” is not in Annex C; check its ISO 4 "
                             "abbreviation")
    return written, "", f"journal “{written}” has no ISO 4 abbreviation in Annex C or online"


__all__ = ["abbreviate", "annex_c", "in_annex_c", "abbreviso", "looks_abbreviated"]
