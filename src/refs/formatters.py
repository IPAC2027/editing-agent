"""JACoW per-type reference formatters.

Migrated from the v1.0.0 standalone formatter (sections 7 and 8). Each
``_fmt_<type>`` takes a ``rec`` dict and returns a fully-formatted JACoW-style
citation string. :func:`format_ref` dispatches by ``ref_type``.

The expected ``rec`` schema (all fields optional unless noted by the type):

- ``authors_raw`` (str | list[dict])
- ``title``
- ``journal``, ``volume``, ``issue``, ``pages``
- ``year``, ``month``
- ``doi``, ``url``
- ``conference``, ``booktitle``, ``paper_id``, ``city``, ``country``
- ``arxiv_id``, ``arxiv_cat``
- ``publisher``, ``edition``, ``editor``, ``is_editor``
- ``institution``, ``rep_id``, ``number``
- ``degree``, ``school``, ``university``, ``department``
- ``patent_number``, ``country``, ``organization``, ``accessed``

Supported ``ref_type`` values are the keys of :data:`FORMATTERS`.
"""

from __future__ import annotations

import re
from typing import Callable

from src.refs.text_utils import (
    fmt_authors,
    pages_fmt,
    sent_case,
)


# ─────────────────────────────────────────────────────────────────────────────
# Small field accessors (mirror _a, _t, _doi_line, _loc, _date, _pp in script)
# ─────────────────────────────────────────────────────────────────────────────

def _a(rec: dict) -> str:
    return fmt_authors(rec.get("authors_raw", ""))


def _t(rec: dict) -> str:
    return sent_case(rec.get("title", ""))


def _doi_line(rec: dict) -> str:
    return f"\n  doi:{rec['doi']}" if rec.get("doi") else ""


def _loc(rec: dict) -> str:
    return ", ".join(filter(None, [rec.get("city"), rec.get("country")]))


def _date(rec: dict) -> str:
    return " ".join(filter(None, [rec.get("month", ""), rec.get("year", "")]))


def _pp(rec: dict) -> str:
    p = rec.get("pages", "")
    if not p:
        return ""
    if re.match(r"^\d{6}$", p.strip()):
        return p.strip()  # article number
    return ("pp. " if "–" in p else "p. ") + p


# ─────────────────────────────────────────────────────────────────────────────
# Type-specific formatters
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_journal(rec: dict) -> str:
    author = _a(rec)
    title = _t(rec)
    _jnl = (rec.get("journal") or "").strip()
    jnl = f", {_jnl}" if _jnl else ""
    vol = f", vol. {rec['volume']}" if rec.get("volume") else ""
    iss = f", no. {rec['issue']}" if rec.get("issue") else ""
    pp = f", {_pp(rec)}" if _pp(rec) else ""
    date = f", {_date(rec)}" if _date(rec) else ""
    if author and title:
        head = f'{author}, "{title}"'
    elif title:
        head = f'"{title}"'
    else:
        head = author
    return f"{head}{jnl}{vol}{iss}{pp}{date}.{_doi_line(rec)}"


def _fmt_journal_accepted(rec: dict) -> str:
    jnl = f", {rec['journal']}" if rec.get("journal") else ""
    return f'{_a(rec)}, "{_t(rec)}"{jnl}, to be published.'


def _fmt_journal_submitted(rec: dict) -> str:
    return f'{_a(rec)}, "{_t(rec)}", submitted for publication.'


def _fmt_arxiv(rec: dict) -> str:
    aid = rec.get("arxiv_id", "")
    cat = rec.get("arxiv_cat", "")
    adoi = rec.get("doi") or (f"10.48550/arXiv.{aid}" if aid else "")
    cat_str = f" [{cat}]" if cat else ""
    year = rec.get("year", "")
    year_str = f", {_date(rec)}" if _date(rec) else (f", {year}" if year else "")
    doi_str = f"\n  doi:{adoi}" if adoi else ""
    return f'{_a(rec)}, "{_t(rec)}"{year_str}, arXiv:{aid}{cat_str}.{doi_str}'


def _fmt_online(rec: dict) -> str:
    # JACoW style: "Name, URL" — e.g. "JACoW, https://www.jacow.org"
    author = _a(rec) or rec.get("organization", "")
    if not author and rec.get("url"):
        m = re.search(r"https?://(?:www\.)?([^/]+)", rec.get("url", ""))
        author = m.group(1) if m else ""
    res = (
        f'{author}, "{_t(rec)}"'
        if (author and rec.get("title"))
        else (f"{author}" if author else "")
    )
    if rec.get("url"):
        res = (res + ", " if res else "") + rec["url"]
    if rec.get("accessed"):
        res += f" (accessed: {rec['accessed']})"
    return (res.rstrip(".") or rec.get("url", "")).rstrip(".") + "."


def _fmt_patent(rec: dict) -> str:
    # JACoW ANNEX B [31]: Authors, "Title of patent", Authority and No., Date.
    author = _a(rec)
    title = _t(rec)
    parts: list[str] = []
    if author:
        parts.append(f'{author}, "{title}"' if title else author)
    if rec.get("country"):
        parts.append(rec["country"])
    pat = rec.get("patent_number") or rec.get("number", "")
    parts.append(f"Patent {pat}" if pat else "Patent")
    if _date(rec):
        parts.append(_date(rec))
    return ", ".join(parts) + "."


def _fmt_conference_published(rec: dict) -> str:
    raw_conf = rec.get("conference") or rec.get("booktitle", "")
    conf = re.sub(
        r"^proc(?:eedings)?\s+(?:of\s+)?", "", raw_conf, flags=re.IGNORECASE,
    ).strip()
    # Strip any pre-existing 'YY suffix before re-appending so we don't get IPAC'24'24.
    conf = re.sub(r"['’]\d{2}$", "", conf).strip()
    yr2 = (rec.get("year") or "")[-2:]
    if re.search(r"(?:19[5-9]\d|20\d\d)(?:\b|$)", conf):
        parts = [f"in Proc. {conf}"]
    else:
        parts = [f"in Proc. {conf}'{yr2}"]
    if _loc(rec):
        parts.append(_loc(rec))
    if _date(rec):
        parts.append(_date(rec))
    if _pp(rec):
        parts.append(_pp(rec))
    return f'{_a(rec)}, "{_t(rec)}", {", ".join(parts)}.{_doi_line(rec)}'


def _fmt_conference_unpublished(rec: dict) -> str:
    raw_conf = rec.get("conference", "")
    conf = re.sub(r"['’]\d{2}$", "", raw_conf).strip()
    yr2 = (rec.get("year") or "")[-2:]
    pid = f", paper {rec['paper_id']}" if rec.get("paper_id") else ""
    if re.search(r"(?:19[5-9]\d|20\d\d)(?:\b|$)", conf):
        parts = [f"presented at {conf}"]
    else:
        parts = [f"presented at {conf}'{yr2}"]
    if _loc(rec):
        parts.append(_loc(rec))
    if _date(rec):
        parts.append(_date(rec))
    return f'{_a(rec)}, "{_t(rec)}", {", ".join(parts)}{pid}, unpublished.'


def _fmt_conference_current(rec: dict) -> str:
    raw_conf = rec.get("conference", "")
    conf = re.sub(r"['’]\d{2}$", "", raw_conf).strip()
    yr2 = (rec.get("year") or "")[-2:]
    pid = f", paper {rec['paper_id']}" if rec.get("paper_id") else ""
    if re.search(r"(?:19[5-9]\d|20\d\d)(?:\b|$)", conf):
        parts = [f"presented at {conf}"]
    else:
        parts = [f"presented at {conf}'{yr2}"]
    if _loc(rec):
        parts.append(_loc(rec))
    if _date(rec):
        parts.append(_date(rec))
    return f'{_a(rec)}, "{_t(rec)}", {", ".join(parts)}{pid}, this conference.'


# JACoW ANNEX B [22]: book titles are NOT quoted and stay in Title Case.
def _fmt_book(rec: dict) -> str:
    raw_title = rec.get("title", "")
    author = _a(rec)
    if author and rec.get("is_editor"):
        n_eds = (
            len(rec["authors_raw"]) if isinstance(rec.get("authors_raw"), list) else 1
        )
        author = author + (", Eds." if n_eds > 1 else ", Ed.")
    loc = rec.get("city") or rec.get("address", "")
    pub = rec.get("publisher", "")
    ed_suffix = f", {rec['edition']} ed" if rec.get("edition") else ""
    if loc and pub:
        loc_pub = f" {loc}: {pub},"
    elif pub:
        loc_pub = f" {pub},"
    elif loc:
        loc_pub = f" {loc},"
    else:
        loc_pub = ""
    head = f"{author}, {raw_title}" if author else raw_title
    return f"{head}{ed_suffix}.{loc_pub} {rec.get('year', '')}.{_doi_line(rec)}"


def _fmt_book_chapter(rec: dict) -> str:
    # JACoW ANNEX B [21]:
    #   Authors, "Chapter title", in Book Title, Ed. Name, Ed. City: Pub, year, pp.
    ch_title = _t(rec)                       # sentence-cased chapter title
    bk_title = rec.get("booktitle", "")      # raw book title (Title Case)
    ed_name = rec.get("editor", "")
    loc = rec.get("city") or rec.get("address", "")
    pub = rec.get("publisher", "")
    year = rec.get("year", "")
    pp = f", {_pp(rec)}" if _pp(rec) else ""

    book_block = f"in {bk_title}"
    if ed_name:
        book_block += f", {ed_name}, Ed."

    if loc and pub:
        loc_pub = f"{loc}: {pub}"
    elif pub:
        loc_pub = pub
    elif loc:
        loc_pub = loc
    else:
        loc_pub = ""

    if loc_pub:
        sep = " " if ed_name else ", "
        tail = f"{sep}{loc_pub}, {year}{pp}" if year else f"{sep}{loc_pub}{pp}"
    else:
        tail = f", {year}{pp}" if year else pp

    return f'{_a(rec)}, "{ch_title}", {book_block}{tail}.'


def _fmt_report(rec: dict) -> str:
    inst = rec.get("institution", "")
    rep = rec.get("rep_id") or rec.get("number", "")
    parts: list[str] = []
    if inst:
        parts.append(inst)
    if _loc(rec):
        parts.append(_loc(rec))
    if rep:
        parts.append(f"Rep. {rep}")
    if _date(rec):
        parts.append(_date(rec))
    suffix = ", ".join(parts)
    return (
        f'{_a(rec)}, "{_t(rec)}"'
        f'{", " + suffix if suffix else ""}.{_doi_line(rec)}'
    )


def _fmt_thesis(rec: dict) -> str:
    degree = rec.get("degree", "Ph.D.")
    parts = [f"{degree} thesis"]
    if rec.get("department"):
        parts.append(rec["department"])
    if rec.get("school") or rec.get("university"):
        parts.append(rec.get("school") or rec.get("university", ""))
    if _loc(rec):
        parts.append(_loc(rec))
    return (
        f'{_a(rec)}, "{_t(rec)}", '
        f'{", ".join(parts)}, {rec.get("year", "")}.{_doi_line(rec)}'
    )


def _fmt_unpublished(rec: dict) -> str:
    return f'{_a(rec)}, "{_t(rec)}", unpublished.'


def _fmt_private_comm(rec: dict) -> str:
    return f"{_a(rec)}, private communication, {_date(rec)}."


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────

FORMATTERS: dict[str, Callable[[dict], str]] = {
    "journal":                _fmt_journal,
    "journal_accepted":       _fmt_journal_accepted,
    "journal_submitted":      _fmt_journal_submitted,
    "conference_published":   _fmt_conference_published,
    "conference_unpublished": _fmt_conference_unpublished,
    "conference_current":     _fmt_conference_current,
    "arxiv":                  _fmt_arxiv,
    "web":                    _fmt_online,
    "book":                   _fmt_book,
    "book_chapter":           _fmt_book_chapter,
    "report":                 _fmt_report,
    "thesis":                 _fmt_thesis,
    "patent":                 _fmt_patent,
    "unpublished":            _fmt_unpublished,
    "private_comm":           _fmt_private_comm,
}

# Legacy aliases — some parsers return names that don't match the
# formatter dispatch keys.  When :func:`format_ref` is called with one of
# these, the dispatch looks it up here first and maps to the canonical
# formatter key.  The bug this prevents: the Word parser classifies
# "in Proc. ..." entries as ``proceedings`` (a legacy name that doesn't
# match any formatter), which previously caused the dispatch to fall
# through to ``_fmt_journal`` and silently drop the ``in Proc. ...`` line.
REF_TYPE_ALIASES: dict[str, str] = {
    "proceedings":            "conference_published",
    "proceedings_published":  "conference_published",
    "proceedings_unpublished": "conference_unpublished",
    "proceedings_current":    "conference_current",
    "conference":             "conference_published",  # bare alias
    "online":                 "web",                   # bibitem parser
    "phdthesis":              "thesis",                # bibtex entry type
    "mastersthesis":          "thesis",                # bibtex entry type
}


def canonicalize_ref_type(rt: str) -> str:
    """Map a legacy / non-canonical ref-type name to a :data:`FORMATTERS` key.

    Unknown names are returned unchanged so :func:`format_ref`'s
    ``FORMATTERS.get(rt, _fmt_journal)`` fallback still works.
    """
    if not rt:
        return "journal"
    return REF_TYPE_ALIASES.get(rt.lower(), rt.lower())


def format_ref(rec: dict, ref_type: str) -> str:
    """Format *rec* per JACoW style for the given *ref_type*.

    Whitespace is normalised per-line so the 2-space indent on continuation
    lines (e.g. ``  doi:10.xxx``) is preserved. Returns the formatted string
    with a single trailing period.

    *ref_type* is first run through :func:`canonicalize_ref_type` so legacy
    parser names like ``"proceedings"`` (returned by the Word and LaTeX
    parsers for "in Proc. ..." entries) map to the correct formatter
    instead of falling through to the journal formatter.  Unknown names
    still fall through to the journal formatter.
    """
    rt = canonicalize_ref_type(ref_type)
    text = FORMATTERS.get(rt, _fmt_journal)(rec).strip()
    # Normalise whitespace line-by-line so a 2-space DOI indent on
    # continuation lines is preserved exactly.
    normalised: list[str] = []
    for ln in text.split("\n"):
        if ln.startswith("  "):
            normalised.append(ln)  # indented continuation — keep as-is
        else:
            normalised.append(re.sub(r"[ \t]+", " ", ln))
    text = "\n".join(normalised)
    text = re.sub(r",\s*\.", ".", text)
    # Ensure a space after every comma not already followed by whitespace.
    text = re.sub(r",(?=[A-Za-z])", ", ", text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Multi-reference splitter
# ─────────────────────────────────────────────────────────────────────────────

def split_refs(text: str) -> list[str]:
    """Split a multi-reference block into individual citation strings.

    Recognises three styles:

    1. Numbered with brackets: ``[1] …`` / ``[2] …``
    2. Numbered with dots:     ``1. …`` / ``2. …``
    3. Blank-line separated:   refs delimited by one or more blank lines.

    Falls back to a single rejoined block when no separator pattern is found.
    Continuation lines (those starting lower-case, with quote-like punctuation,
    or indented ≥ 6 spaces) are glued onto the previous line.
    """
    text = text.strip()
    if not text:
        return []
    _REF_NUM = re.compile(r"^\s*(?:\[\d+\]\.?\s*|\d{1,3}\.\s+)")
    _CONT = re.compile(r"^[a-z'\"(“«,;:\-–]|^\s{6,}")

    def _strip_num(s: str) -> str:
        return _REF_NUM.sub("", s).strip()

    def _rejoin(lines: list[str]) -> str:
        out: list[str] = []
        for line in lines:
            if out and _CONT.match(line):
                out[-1] = out[-1].rstrip() + " " + line.strip()
            else:
                out.append(line)
        return " ".join(line.strip() for line in out).strip()

    lines = text.splitlines()
    splits = [i for i, ln in enumerate(lines) if _REF_NUM.match(ln)]
    if len(splits) >= 2:
        chunks = []
        for k, pos in enumerate(splits):
            end = splits[k + 1] if k + 1 < len(splits) else len(lines)
            block = _strip_num(_rejoin([_strip_num(lines[pos])] + lines[pos + 1:end]))
            if len(block) >= 10:
                chunks.append(block)
        if chunks:
            return chunks

    raw_chunks = [c.strip() for c in re.split(r"\n[ \t]*\n", text) if c.strip()]
    if len(raw_chunks) >= 2:
        out = [_strip_num(_rejoin(c.splitlines())) for c in raw_chunks]
        out = [b for b in out if len(b) >= 10]
        if out:
            return out

    rejoined = _strip_num(_rejoin(lines))
    return [rejoined] if len(rejoined) >= 10 else [text]
