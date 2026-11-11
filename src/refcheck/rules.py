"""The JACoW reference rules, one function each: find the error, fix it if it can.

Sources: JACoW Annex B (the reference examples in the template), the JACoW
"Formatting references" and "DOIs for arXiv" pages, and the Editor Quality
Matrix (author lists, DOIs, italics). Each rule returns :class:`Issue`\\ s; a
rule fixes only what it can fix with no judgement and no fact from outside
the reference (or a fact a lookup verified, named on the fix). Everything
else is left as an issue saying why, so it can be described to the local
model or the editor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from src.refcheck.model import (EDITOR, ERROR, INFO, MODEL, WARNING, Context, Fix, Issue,
                                names, people)

ANNEX_B = "JACoW Annex B"
RULE_DOI = "JACoW Annex B: DOIs are written doi:10.xxxx/… as the last item"
RULE_ARXIV = "JACoW 'DOIs for arXiv': an arXiv paper is cited with doi:10.48550/arXiv.<id>"
RULE_AUTHORS = "JACoW Annex B: authors as 'A. B. Surname'; 'and' / ', and' / 'et al.' rules"
RULE_TITLE = "JACoW Annex B: the title in double quotes, sentence case, comma after the quote"
RULE_PROC = "JACoW Annex B: in Proc. CONF'YY, City, Country, Mon. Year, pp. X-Y. doi:…"
RULE_JOURNAL = "JACoW Annex B: Journal (ISO 4 abbreviation), vol. V, no. N, p. P, Year. doi:…"
RULE_MONTH = "JACoW Annex B: months as Jan. Feb. Mar. Apr. May Jun. Jul. Aug. Sep. Oct. Nov. Dec."
RULE_URL = "JACoW Annex B: a URL only when there is no DOI, written plainly"
RULE_END = "JACoW Annex B: a reference ends with a full stop, except after a DOI or URL"

RULES: list[Callable[[Context], Iterable[Issue]]] = []


def rule(fn):
    RULES.append(fn)
    return fn


def _issue(ctx: Context, code: str, severity: str, message: str, rule_text: str,
           start: int, end: int, replacement: str | None = None, *,
           presentation: bool = True, substitutions=(), additions=(), removals=(),
           who: str = MODEL, why_not: str = "", needs: str = "", source: str = "") -> Issue:
    excerpt = ctx.text[max(0, start):max(0, end)] if start >= 0 else ""
    fix = None
    if replacement is not None:
        fix = Fix(start, end, replacement, tuple(substitutions), tuple(additions),
                  tuple(removals), presentation, source)
    return Issue(code, severity, message, rule_text, start, end, fix, who, why_not, needs,
                 excerpt[:120])


# ---------------------------------------------------------------------------
# DOIs, arXiv and URLs
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
JACOW_DOI_RE = re.compile(r"10\.18429/JACoW-([A-Za-z]+)[-_]?(\d{4})(?:-([A-Za-z0-9]+))?", re.I)


def doi_end(raw: str) -> str:
    """A DOI as found in text, without the punctuation that follows it."""
    doi = raw.rstrip(".,;:")
    while doi.endswith(")") and doi.count("(") < doi.count(")"):
        doi = doi[:-1].rstrip(".,;:")
    return doi


def dois(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.start() + len(doi_end(m.group(0))), doi_end(m.group(0)))
            for m in DOI_RE.finditer(text)]


@rule
def doi_as_url(ctx: Context):
    for m in re.finditer(r"(?:\bdoi:\s*)?(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+)",
                         ctx.text, re.I):
        doi = doi_end(m.group(1))
        yield _issue(ctx, "REF-DOI-URL", ERROR, "The DOI is written as a web address; "
                     "JACoW writes it doi:10.xxxx/….", RULE_DOI, m.start(),
                     m.start(1) + len(doi), f"doi:{doi}",
                     removals=("https", "http", "dx", "doi", "org"))


@rule
def doi_prefix(ctx: Context):
    for m in re.finditer(r"\b[Dd][Oo][Ii]\b(?:\s*:\s*/{0,2}\s*|\s+)(?=10\.\d)", ctx.text):
        if m.group(0) == "doi:":
            continue
        yield _issue(ctx, "REF-DOI-FORM", ERROR, f"'{m.group(0).strip()}' before the DOI; "
                     "JACoW writes doi: in lower case with no space.", RULE_DOI,
                     m.start(), m.end(), "doi:")


@rule
def doi_bare(ctx: Context):
    for m in re.finditer(r"(?<![\w/:.])(10\.\d{4,9}/[^\s\"<>]+)", ctx.text):
        if re.search(r"(?:doi:\s*|doi\.org/|https?://\S*)$", ctx.text[:m.start()], re.I):
            continue
        yield _issue(ctx, "REF-DOI-FORM", ERROR, "A DOI is written with 'doi:' before it.",
                     RULE_DOI, m.start(), m.start(), "doi:")


@rule
def doi_twice(ctx: Context):
    seen: dict[str, int] = {}
    for start, end, doi in dois(ctx.text):
        key = doi.lower()
        if key not in seen:
            seen[key] = start
            continue
        # The later copy goes, with the "doi:" and separator before it.
        head = re.search(r"[\s,.;]*(?:doi:\s*)?$", ctx.text[:start], re.I)
        cut = head.start() if head else start
        yield _issue(ctx, "REF-DOI-TWICE", WARNING, "The same DOI is given twice.", RULE_DOI,
                     cut, end, "", removals=(doi,))


def _last_doi(text: str) -> tuple[int, int, str] | None:
    found = list(re.finditer(r"\bdoi:(10\.\d{4,9}/\S+)", text))
    if not found:
        return None
    m = found[-1]
    doi = doi_end(m.group(1))
    return m.start(), m.start(1) + len(doi), doi


@rule
def doi_place(ctx: Context):
    last = _last_doi(ctx.text)
    if not last:
        return
    start, end, doi = last
    after = ctx.text[end:]
    if after.strip(" .,;"):
        if re.fullmatch(r"[\s.,;]*https?://\S+[\s.]*", after):
            return                     # a URL after it: url_with_doi decides
        yield _issue(ctx, "REF-DOI-LAST", WARNING, "Something follows the DOI; JACoW puts "
                     "the DOI last.", RULE_DOI, start, len(ctx.text),
                     why_not="what follows the DOI has to be moved before it, and where "
                     "it goes depends on what it is")
        return
    if after.strip():
        yield _issue(ctx, "REF-DOI-END", ERROR, "A full stop after the DOI; JACoW ends "
                     "the reference with the DOI itself.", RULE_DOI, end, len(ctx.text), "")
    before = ctx.text[:start]
    sep = re.search(r"([\s,;]*)$", before)
    if before.strip() and not before.rstrip().endswith("."):
        yield _issue(ctx, "REF-DOI-SEP", ERROR, "The DOI should follow a full stop "
                     "(“…, pp. 57-59. doi:…”).", RULE_DOI, sep.start(), start, ". ")
    elif before.rstrip().endswith(".") and not before.endswith(". ") \
            and "\n" not in before[len(before.rstrip()):]:
        yield _issue(ctx, "REF-DOI-SEP", ERROR, "One space between the full stop and "
                     "the DOI.", RULE_DOI, len(before.rstrip()), start, " ")


@rule
def jacow_doi(ctx: Context):
    for m in JACOW_DOI_RE.finditer(ctx.text):
        series, year, paper = m.group(1), m.group(2), m.group(3)
        if not paper:
            known = ctx.facts.get("doi")
            if known and JACOW_DOI_RE.fullmatch(known[0] or "") and \
                    known[0].lower().startswith(m.group(0).lower()):
                yield _issue(ctx, "REF-DOI-INCOMPLETE", ERROR, "The JACoW DOI has no paper "
                             "ID.", RULE_DOI, m.start(), m.end(), known[0],
                             presentation=False, additions=(known[0],), source=known[1])
            else:
                yield _issue(ctx, "REF-DOI-INCOMPLETE", ERROR, "The JACoW DOI has no paper "
                             f"ID: 10.18429/JACoW-{series}{year}-<paper ID>.", RULE_DOI,
                             m.start(), m.end(), who=EDITOR,
                             why_not="the paper ID cannot be made up",
                             needs="the paper ID in the proceedings (refs.jacow.org)")
            continue
        # The conference the DOI names against the one the text names.
        named = _named_conference(ctx)
        if named and (named[0].lower() != series.lower() or named[1] != year[-2:]):
            yield _issue(ctx, "REF-DOI-OTHER-CONF", ERROR,
                         f"The DOI is for {series.upper()}'{year[-2:]}, but the reference "
                         f"names {named[0]}'{named[1]}: one of them is wrong.", RULE_DOI,
                         m.start(), m.end(), who=EDITOR,
                         why_not="only the author or the proceedings can say which is right",
                         needs="the paper on refs.jacow.org")


def _series() -> frozenset[str]:
    try:
        from jacow_formatter import _JACOW_SERIES
        return frozenset(_JACOW_SERIES)
    except Exception:  # noqa: BLE001
        return frozenset({"ipac", "napac", "pac", "epac", "linac", "fel", "ibic", "icalepcs",
                          "srf", "hiat", "cyclotrons", "cool", "icap", "hb", "ecris", "fls"})


_MIXED_SERIES = {"cyclotrons": "Cyclotrons", "rupac": "RuPAC", "pcapac": "PCaPAC",
                 "eefact": "eeFACT", "napac": "NAPAC"}


def series_label(series: str, year: str, apostrophe: str = "'") -> str:
    """JACoW's label for a conference: IPAC'23 (or IPAC’23), Cyclotrons'22."""
    name = _MIXED_SERIES.get(series.lower(), series.upper())
    return f"{name}{apostrophe}{year[-2:]}"


def _apostrophe(ctx: Context) -> str:
    return getattr(ctx.style, "label_apostrophe", "'") or "'"


def _conference_re() -> re.Pattern:
    names_ = "|".join(sorted(_series(), key=len, reverse=True))
    return re.compile(rf"\b({names_})(?:\s*[-\u2019']?\s*|\s+)(\d{{4}}|\d{{2}})\b(?!\.\d)", re.I)


def _venue_start(ctx: Context) -> int:
    return ctx.parts.rest[0] if (ctx.parts.title or ctx.parts.authors) else 0


def _named_conference(ctx: Context) -> tuple[str, str] | None:
    m = _conference_re().search(ctx.text, _venue_start(ctx))
    if not m or m.start() > (JACOW_DOI_RE.search(ctx.text) or m).start():
        return None
    return m.group(1).upper(), m.group(2)[-2:]


ARXIV_NEW = r"\d{4}\.\d{4,5}"
ARXIV_OLD = r"[a-z\-]+(?:\.[A-Z]{2})?/\d{7}"


@rule
def arxiv_url(ctx: Context):
    for m in re.finditer(rf"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/({ARXIV_NEW}|{ARXIV_OLD})"
                         r"(v\d+)?(?:\.pdf)?", ctx.text):
        yield _issue(ctx, "REF-ARXIV-URL", ERROR, "arXiv is cited by its identifier and "
                     "DOI, not its web address.", RULE_ARXIV, m.start(), m.end(),
                     f"arXiv:{m.group(1)}", presentation=False,
                     removals=("https", "http", "www", "arxiv", "org", "abs", "pdf",
                               m.group(2) or ""))


@rule
def arxiv_preprint(ctx: Context):
    for m in re.finditer(r"\barXiv\s+(?:e-)?preprint\s*,?\s*(?=arXiv:)", ctx.text, re.I):
        yield _issue(ctx, "REF-ARXIV-PREPRINT", WARNING, "'arXiv preprint' is not written; "
                     "arXiv:<id> says it.", RULE_ARXIV, m.start(), m.end(), "",
                     presentation=False, removals=("preprint", "arXiv", "e"))


@rule
def arxiv_doi(ctx: Context):
    m = re.search(rf"\barXiv:\s*({ARXIV_NEW}|{ARXIV_OLD})(v\d+)?", ctx.text, re.I)
    if not m or re.search(r"10\.48550/arXiv\.", ctx.text, re.I):
        return
    if _last_doi(ctx.text) or dois(ctx.text):
        return                         # a published version's DOI comes first
    arxiv_id = m.group(1)
    body = ctx.text.rstrip()
    end = len(body.rstrip("."))
    doi = f"10.48550/arXiv.{arxiv_id}"
    yield _issue(ctx, "REF-ARXIV-DOI", ERROR, f"An arXiv paper is cited with its DOI: "
                 f"doi:{doi}.", RULE_ARXIV, end, len(ctx.text), f". doi:{doi}",
                 presentation=False, additions=(doi,))


@rule
def url_boilerplate(ctx: Context):
    for m in re.finditer(r"\[\s*[Oo]nline\s*\]\.?\s*(?:[Aa]vailable\s*(?:at|from)?:?\s*)?"
                         r"|\b[Aa]vailable\s+(?:online\s+)?(?:at|from)?:?\s*(?=https?://)",
                         ctx.text):
        yield _issue(ctx, "REF-URL-ONLINE", WARNING, "'[Online]. Available:' is not "
                     "written before a URL in JACoW.", RULE_URL, m.start(), m.end(), "",
                     removals=("Online", "Available", "at", "from"))


@rule
def url_with_doi(ctx: Context):
    urls = [m.span() for m in re.finditer(r"https?://\S+", ctx.text)]
    # DOIs given outside any web address: one inside the URL is not "given".
    known = {d.lower() for start, _, d in dois(ctx.text)
             if not any(a <= start < b for a, b in urls)}
    for m in re.finditer(r"[\s,.;]*\bhttps?://\S+", ctx.text):
        url = m.group(0).strip(" ,.;")
        trimmed_end = m.start() + len(m.group(0).rstrip(".,;"))
        jacow_pdf = re.search(r"(?:accelconf\.web\.cern\.ch|jacow\.org)/\S*?/papers?/"
                              r"([A-Za-z0-9]+)\.pdf", url, re.I)
        inside = DOI_RE.search(url)
        if (inside and doi_end(inside.group(0)).lower() in known
                and not url.lower().startswith(("http://doi.org", "https://doi.org",
                                                "https://dx.doi.org", "http://dx.doi.org"))):
            yield _issue(ctx, "REF-URL-DOI", WARNING, "A web address that repeats the DOI.",
                         RULE_URL, m.start(), trimmed_end, "", removals=(url,))
        elif jacow_pdf and known:
            yield _issue(ctx, "REF-URL-JACOW", WARNING, "A JACoW paper is cited by its DOI, "
                         "not the PDF's address.", RULE_URL, m.start(), trimmed_end, "",
                         removals=(url,))
        elif jacow_pdf:
            # Older proceedings have no DOI: Annex B gives the paper ID instead.
            paper = jacow_pdf.group(1).upper()
            yield _issue(ctx, "REF-URL-JACOW", WARNING, "A JACoW paper is cited by its DOI "
                         f"or, with none, its paper ID (paper {paper}), not the PDF's "
                         "address.", RULE_URL, m.start(), trimmed_end, f", paper {paper}",
                         presentation=False, substitutions=((url, f"paper {paper}"),),
                         removals=(url,))


@rule
def jacow_paper_id(ctx: Context):
    if not any(JACOW_DOI_RE.fullmatch(d) for _, _, d in dois(ctx.text)):
        return
    for m in re.finditer(r",?\s*\bpaper\s+(?:ID\s+)?[A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*\b", ctx.text):
        yield _issue(ctx, "REF-PAPER-ID", WARNING, "With a JACoW DOI the paper ID is not "
                     "given.", "JACoW 'Formatting references': with a JACoW DOI, remove "
                     "'paper …'", m.start(), m.end(), "", presentation=False,
                     removals=(m.group(0),))


# ---------------------------------------------------------------------------
# Authors
# ---------------------------------------------------------------------------

_PARTICLES = {"von", "van", "de", "der", "den", "du", "la", "le", "di", "da", "del", "dos",
              "ten", "ter", "zu", "dei", "des", "y", "bin", "al"}


@rule
def et_al_form(ctx: Context):
    for m in re.finditer(r"\bet\.?\s*al\b\.?", ctx.text):
        if m.group(0) != "et al.":
            yield _issue(ctx, "REF-ETAL", ERROR, f"'{m.group(0)}' is written 'et al.'.",
                         RULE_AUTHORS, m.start(), m.end(), "et al.")


@rule
def et_al_comma(ctx: Context):
    found, et_al = names(ctx.text, ctx.parts.authors)
    if not et_al or not people(found) or not ctx.parts.authors:
        return
    start = found[-1].end
    tail = re.match(r"(\s*,?\s*)et\.?\s*al\b", ctx.text[start:ctx.parts.authors[1]])
    if not tail:
        return
    sep = tail.group(1)
    if len(found) == 1 and "," in sep:
        yield _issue(ctx, "REF-ETAL-COMMA", ERROR, "No comma before 'et al.' after a "
                     "single name.", RULE_AUTHORS, start, start + len(sep), " ")
    elif len(found) > 1 and "," not in sep:
        yield _issue(ctx, "REF-ETAL-COMMA", ERROR, "A comma before 'et al.' after several "
                     "names.", RULE_AUTHORS, start, start + len(sep), ", ")


_SURNAME_FIRST = re.compile(
    r"([A-Z][\w'\u2019\-]+(?:\s[A-Z][\w'\u2019\-]+)?),?\s+((?:[A-Z]\.\s?-?)+)(?=,|\s+and\b|\s*$)")


@rule
def surname_first(ctx: Context):
    if not ctx.parts.authors:
        return
    start, end = ctx.parts.authors
    body = ctx.text[start:end]
    if re.search(r"\d", body):
        return
    et_al = re.search(r",?\s*et\.?\s*al\.?\s*$", body)
    core = body[:et_al.start()] if et_al else body
    pieces = [p for p in re.split(r",\s*(?:and\s+)?(?=[A-Z][\w'\u2019\-]+,?\s+[A-Z]\.)"
                                  r"|\s+and\s+|\s*&\s*", core) if p.strip()]
    converted = []
    for piece in pieces:
        m = re.fullmatch(r"\s*([A-Z][\w'\u2019\-]+(?:\s[A-Z][\w'\u2019\-]+)?),?\s+"
                         r"((?:[A-Z]\.\s?-?)+)\s*", piece)
        if not m:
            return
        initials = re.sub(r"\.(?=[A-Z])", ". ", m.group(2).replace(" ", "")).strip()
        initials = initials.replace(". -", ".-")
        converted.append(f"{initials} {m.group(1)}")
    if not converted:
        return
    joined = _join_names(converted, bool(et_al))
    if joined == body:
        return
    yield _issue(ctx, "REF-AUTH-ORDER", ERROR, "Names are written initials first "
                 "('T. Boltz', not 'Boltz, T.').", RULE_AUTHORS, start, end, joined,
                 presentation=False)


def _join_names(people: list[str], et_al: bool) -> str:
    if et_al:
        return f"{people[0]} et al." if len(people) == 1 else ", ".join(people) + ", et al."
    if len(people) == 1:
        return people[0]
    if len(people) == 2:
        return f"{people[0]} and {people[1]}"
    return ", ".join(people[:-1]) + ", and " + people[-1]


@rule
def initials_spacing(ctx: Context):
    if not ctx.parts.authors or not people(names(ctx.text, ctx.parts.authors)[0]):
        return
    start, end = ctx.parts.authors
    for m in re.finditer(r"(?<![A-Za-z])([A-Z]\.)(?=[A-Z][a-z]?\.)", ctx.text[start:end]):
        at = start + m.end()
        yield _issue(ctx, "REF-AUTH-INITIALS", ERROR, "Initials are separated by a space "
                     "('P. N. Ostroumov').", RULE_AUTHORS, at, at, " ")


_NOT_PEOPLE = r"(?:Collaboration|Group|Team|Consortium|Project|Lab|Laboratory|Collab)"


@rule
def initials_without_stops(ctx: Context):
    """'SG Biedron, BE Chase, D Edstrom' -> 'S. G. Biedron, B. E. Chase, D. Edstrom'."""
    if not ctx.parts.authors:
        return
    start, end = ctx.parts.authors
    body = ctx.text[start:end]
    if re.search(r"\d", body):
        return
    pattern = re.compile(r"(?:^|(?<=,\s)|(?<=\band\s))([A-Z]{1,3})\s+(?=[A-Z][a-z\u00c0-\u024f'\u2019\-]+"
                         rf"\b)(?!{_NOT_PEOPLE}\b)")
    for m in pattern.finditer(body):
        letters = m.group(1)
        dotted = " ".join(f"{c}." for c in letters)
        at = start + m.start(1)
        yield _issue(ctx, "REF-AUTH-INITIAL", ERROR, f"'{letters}' is initials: '{dotted}'.",
                     RULE_AUTHORS, at, at + len(letters), dotted, presentation=False,
                     substitutions=((f"{letters} ", f"{dotted} "),) if len(letters) > 1 else ())


@rule
def initial_typo(ctx: Context):
    if not ctx.parts.authors:
        return
    start, end = ctx.parts.authors
    body = ctx.text[start:end]
    if re.search(r"\d", body) or len(body) > 400:
        return
    for m in re.finditer(r"(?:^|(?<=,\s)|(?<=\band\s))([A-Z])(,)\s+(?=[A-Z][a-z]{2,})", body):
        if _SURNAME_FIRST.match(body):
            return
        at = start + m.start(1) + 1
        yield _issue(ctx, "REF-AUTH-INITIAL", ERROR, f"'{m.group(1)}{m.group(2)}' before a "
                     "surname looks like an initial without its full stop.", RULE_AUTHORS,
                     at, at + len(m.group(2)), ".", presentation=False)


@rule
def given_names(ctx: Context):
    found, _ = names(ctx.text, ctx.parts.authors)
    body = ctx.parts.get(ctx.parts.authors)
    if not people(found) or _SURNAME_FIRST.match(body or "") or re.search(r"\b[A-Z][\w-]+,\s*[A-Z]\.", body):
        return
    for name in found:
        tokens = name.text.split()
        if len(tokens) < 2 or not re.fullmatch(r"[A-Z][a-z\u00c0-\u024f'\-]+", tokens[0]):
            continue
        if any(t.isupper() and len(t) > 1 for t in tokens) or len(tokens) > 4:
            continue                    # a collaboration or an acronym, not a person
        surname_at = len(tokens) - 1
        while surname_at > 1 and tokens[surname_at - 1].lower() in _PARTICLES:
            surname_at -= 1
        given, surname = tokens[:surname_at], tokens[surname_at:]
        initials = []
        for word in given:
            if re.fullmatch(r"[A-Z]\.(?:-[A-Z]\.)?", word):
                initials.append(word)
            elif re.fullmatch(r"[A-Z][\w'\u2019]*(?:-[A-Z][\w'\u2019]*)+", word):
                initials.append("-".join(part[0] + "." for part in word.split("-")))
            elif re.fullmatch(r"[A-Z][a-z\u00c0-\u024f'\u2019]+", word):
                initials.append(word[0] + ".")
            else:
                initials = []
                break
        if not initials:
            continue
        replacement = " ".join(initials + surname)
        dropped = [w for w in given if not re.fullmatch(r"[A-Z]\.(?:-[A-Z]\.)?", w)]
        yield _issue(ctx, "REF-AUTH-GIVEN", ERROR, f"'{name.text}': JACoW gives initials, "
                     f"not first names ('{replacement}').", RULE_AUTHORS, name.start,
                     name.end, replacement, presentation=False, removals=tuple(dropped))


@rule
def author_separators(ctx: Context):
    found, et_al = names(ctx.text, ctx.parts.authors)
    if len(found) < 2 or not ctx.parts.authors or not people(found):
        return
    for m in re.finditer(r"\s*&\s*", ctx.parts.get(ctx.parts.authors)):
        at = ctx.parts.authors[0] + m.start()
        yield _issue(ctx, "REF-AUTH-AND", ERROR, "'and', not '&', between names.",
                     RULE_AUTHORS, at, at + len(m.group(0)), " and ")
        return
    if et_al:
        return
    if len(found) > 6:
        first = found[0]
        removed = tuple(n.text for n in found[1:])
        yield _issue(ctx, "REF-AUTH-MANY", WARNING, f"{len(found)} names: JACoW lists more "
                     "than six authors as the first one 'et al.'.", RULE_AUTHORS,
                     first.end, found[-1].end, " et al.", presentation=False,
                     removals=removed)
        return
    gaps = [(found[i].end, found[i + 1].start) for i in range(len(found) - 1)]
    for index, (a, b) in enumerate(gaps):
        gap = ctx.text[a:b]
        last = index == len(gaps) - 1
        if len(found) == 2:
            want = " and "
        elif last:
            want = ", and "
        else:
            want = ", "
        if gap != want and gap.strip(" ,") in ("", "and"):
            if not last and gap.strip(" ,") == "and":
                continue                 # "A and B, C": not a list this rule can read
            yield _issue(ctx, "REF-AUTH-AND", ERROR,
                         "Two names are joined by 'and'; three to six by commas with "
                         "', and' before the last.", RULE_AUTHORS, a, b, want)


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

@rule
def title_quotes(ctx: Context):
    p = ctx.parts
    if not p.title:
        return
    if ctx.text[p.open_quote] == '"':
        yield _issue(ctx, "REF-TITLE-QUOTES", ERROR, "Curly double quotes around the "
                     "title.", RULE_TITLE, p.open_quote, p.open_quote + 1, "\u201c")
    if ctx.text[p.close_quote] == '"':
        yield _issue(ctx, "REF-TITLE-QUOTES", ERROR, "Curly double quotes around the "
                     "title.", RULE_TITLE, p.close_quote, p.close_quote + 1, "\u201d")


@rule
def title_punctuation(ctx: Context):
    p = ctx.parts
    if not p.title:
        return
    text = ctx.text
    inside = re.search(r"\s*([,.;:])\s*$", text[p.title[0]:p.close_quote])
    after = text[p.close_quote + 1:]
    follow = after[:1]
    if inside:
        start = p.title[0] + inside.start()
        # "rings.”," / "optimizer,”" -> "rings”," / "optimizer”,"
        replacement = "\u201d" if follow == "," else "\u201d,"
        end = p.close_quote + 1
        if follow and follow not in ", ":
            replacement = "\u201d, "
        yield _issue(ctx, "REF-TITLE-COMMA", ERROR, "The comma goes after the closing "
                     "quote, and no full stop ends the title (“Title”, …).", RULE_TITLE,
                     start, end, replacement)
    elif after.strip() and follow not in (",",) and not after.lstrip().startswith(("?", "!")) \
            and not text[p.title[0]:p.close_quote].rstrip().endswith(","):
        yield _issue(ctx, "REF-TITLE-COMMA", ERROR, "A comma after the closing quote.",
                     RULE_TITLE, p.close_quote + 1, p.close_quote + 1 + (len(after) -
                     len(after.lstrip(" .;:"))), ", ")
    if p.authors and people(names(text, p.authors)[0]):
        gap = text[p.authors[1]:p.open_quote]
        if gap != ", " and gap.strip() in ("", ",") and \
                not re.search(r"\b(?:Ed|Eds)\.$", text[:p.authors[1]]):
            yield _issue(ctx, "REF-TITLE-COMMA", ERROR, "A comma between the authors and "
                         "the title.", RULE_TITLE, p.authors[1], p.open_quote, ", ")


_TITLE_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*")
_SMALL = {"a", "an", "the", "and", "or", "of", "for", "in", "on", "at", "to", "by", "with",
          "from", "via", "as", "into", "over", "under", "versus", "vs"}


@rule
def title_capitals(ctx: Context):
    p = ctx.parts
    if not p.title:
        return
    title = ctx.text[p.title[0]:p.title[1]]
    words = _TITLE_WORD.findall(title)
    letters = [w for w in words if len(w) > 1]
    capitals = len(letters) >= 3 and sum(w.isupper() for w in letters) >= 0.8 * len(letters)
    later = [w for w in words[1:] if w.lower() not in _SMALL and len(w) > 2
             and not (sum(c.isupper() for c in w) > 1)]
    title_case = (not capitals and len(later) >= 3
                  and sum(w[0].isupper() for w in later) >= 0.75 * len(later))
    if not (capitals or title_case):
        return
    code, severity, what = (("REF-TITLE-CAPS", ERROR, "in capitals") if capitals
                            else ("REF-TITLE-CASE", WARNING, "in Title Case"))
    message = (f"The title is {what}; JACoW titles are in sentence case (first word, "
               "names and acronyms capitalised).")
    try:
        from src.references import sent_case_report
        casing = sent_case_report(title)
    except Exception:  # noqa: BLE001
        casing = None
    protected = [w for w in re.findall(r"[\w'\u2019\-]+", title)
                 if re.search(r"\d", w) or re.search(r"[a-z][A-Z]", w)]
    if casing and any(w not in casing.text for w in protected):
        casing = None                    # it would lowercase "Mu2e": not this way
    if casing and casing.changed and not casing.unsure and casing.text != title:
        yield _issue(ctx, code, severity, message + f" ('{casing.text}')", RULE_TITLE,
                     p.title[0], p.title[1], casing.text, presentation=False,
                     substitutions=((title, casing.text),))
        return
    unsure = ", ".join(casing.unsure) if casing and casing.unsure else ""
    yield _issue(ctx, code, severity, message, RULE_TITLE, p.title[0], p.title[1],
                 why_not=("whether these words are names or acronyms needs judgement: "
                          + unsure) if unsure else
                 "which words are names or acronyms needs judgement")


@rule
def title_missing(ctx: Context):
    if ctx.parts.title or re.search(r"https?://", ctx.text[:80]):
        return
    quoted_kinds = ("journal", "conference_published", "conference_unpublished",
                    "conference_current", "report", "thesis", "arxiv", "unpublished")
    markers = re.search(r"\bvol\.|\bProc\.|\bpp?\.\s*\d|\b\d+\(\d+\):|\barXiv:|"
                        r"\bJournal\b|\bRev\.|\bLett\.", ctx.text)
    if ctx.kind in ("web", "book", "book_chapter", "private_comm", "patent") or \
            (ctx.kind not in quoted_kinds and not markers):
        return
    if re.match(r"(?:(?:[A-Z]\.\s?(?:-?[A-Z]\.\s?)*|[A-Z][a-z\u00c0-\u024f]+\s+)"
                r"[A-Z][\w'\u2019\-]+(?:,\s+|\s+and\s+|\s+et al)"
                r"|[A-Z][\w'\u2019\-]+,\s+(?:[A-Z]\.\s?-?)+,)", ctx.text):
        yield _issue(ctx, "REF-TITLE-MISSING", ERROR, "No title in double quotes: JACoW "
                     "puts the title in “…” after the authors.", RULE_TITLE, 0,
                     len(ctx.text), why_not="where the title begins and ends has to be "
                     "read from the reference")


_PROPER = {"gaussian": "Gaussian", "fourier": "Fourier", "hamiltonian": "Hamiltonian",
           "lagrangian": "Lagrangian", "bayesian": "Bayesian", "markov": "Markov",
           "markovian": "Markovian", "poisson": "Poisson", "lorentz": "Lorentz",
           "coulomb": "Coulomb", "liouville": "Liouville", "vlasov": "Vlasov",
           "touschek": "Touschek", "schottky": "Schottky", "landau": "Landau",
           "maxwell": "Maxwell", "maxwellian": "Maxwellian", "boltzmann": "Boltzmann",
           "hermite": "Hermite", "bessel": "Bessel", "runge": "Runge", "kutta": "Kutta",
           "riemann": "Riemann", "jacobian": "Jacobian", "hessian": "Hessian",
           "cartesian": "Cartesian", "eulerian": "Eulerian", "newtonian": "Newtonian"}


@rule
def title_names(ctx: Context):
    p = ctx.parts
    if not p.title:
        return
    for m in _TITLE_WORD.finditer(ctx.text, p.title[0], p.title[1]):
        word = m.group(0)
        base, ending = re.match(r"(.*?)((?:'s|\u2019s|s)?)$", word).groups()
        proper = _PROPER.get(word) or (_PROPER[base] + ending if base in _PROPER else None)
        if proper:
            yield _issue(ctx, "REF-TITLE-NAME", WARNING, f"'{word}' is a name and keeps its "
                         f"capital ('{proper}').", RULE_TITLE, m.start(), m.end(), proper,
                         presentation=False, substitutions=((word, proper),))


# ---------------------------------------------------------------------------
# Proceedings
# ---------------------------------------------------------------------------

@rule
def proceedings_of(ctx: Context):
    text = ctx.text
    for m in re.finditer(r"\b(?:[Ii]n\s+)?(?:[Tt]he\s+)?[Pp]roceedings\s+of\s+(?:the\s+)?",
                         text, ):
        if m.start() < _venue_start(ctx):
            continue
        yield _issue(ctx, "REF-PROC-FORM", ERROR, "Proceedings are written 'in Proc. …'.",
                     RULE_PROC, m.start(), m.end(), "in Proc. ", presentation=False,
                     removals=("Proceedings", "of", "the"))
    for m in re.finditer(r"\b[Pp]roc\.\s+of\s+(?:the\s+)?", text):
        if m.start() >= _venue_start(ctx):
            yield _issue(ctx, "REF-PROC-FORM", ERROR, "'Proc. of' is written 'Proc.'.",
                         RULE_PROC, m.start(), m.end(), "Proc. ", removals=("of", "the"))
    for m in re.finditer(r"(?<=,\s)Proc\.\s", text):
        if not re.search(r"\b(?:in|at)\s+$", text[:m.start()]):
            yield _issue(ctx, "REF-PROC-FORM", ERROR, "'in' before 'Proc.'.", RULE_PROC,
                         m.start(), m.start(), "in ")
    for m in re.finditer(r"\bpresented\s+at\s+(Proc\.\s+)", text):
        yield _issue(ctx, "REF-PROC-FORM", WARNING, "A talk is 'presented at' a conference, "
                     "not at its proceedings.", RULE_PROC, m.start(1), m.end(1), "",
                     presentation=False, removals=("Proc",))


@rule
def conference_label(ctx: Context):
    start = _venue_start(ctx)
    for m in _conference_re().finditer(ctx.text, start):
        label = series_label(m.group(1), m.group(2), _apostrophe(ctx))
        written = m.group(0)
        if written.replace("\u2019", "'") == label.replace("\u2019", "'"):
            continue                     # either apostrophe is the conference's label
        if DOI_RE.search(ctx.text[max(0, m.start() - 30):m.end()]) and "JACoW" in \
                ctx.text[max(0, m.start() - 12):m.start()]:
            continue                     # inside a JACoW DOI
        before = ctx.text[max(0, m.start() - 8):m.start()]
        if "/" in before or "-" in before[-1:]:
            continue
        yield _issue(ctx, "REF-PROC-LABEL", ERROR, f"JACoW names the conference "
                     f"'{label}'.", RULE_PROC, m.start(), m.end(), label)


@rule
def conference_long_name(ctx: Context):
    """A JACoW paper whose DOI names its conference, but the text does not."""
    m = next((JACOW_DOI_RE.fullmatch(d) for _, _, d in dois(ctx.text)
              if JACOW_DOI_RE.fullmatch(d)), None)
    if not m or not m.group(3) or not ctx.parts.title:
        return
    label = series_label(m.group(1), m.group(2), _apostrophe(ctx))
    if label.replace("\u2019", "'").lower() in ctx.text.replace("\u2019", "'").lower():
        return
    if _named_conference(ctx):
        return                           # named by acronym: conference_label's job
    rest_start = ctx.parts.rest[0]
    lead = re.match(r"[\s,]*(?:in\s+)?", ctx.text[rest_start:])
    venue_start = rest_start + lead.end()
    city = ""
    try:
        from jacow_formatter import _JACOW_CONF_TABLE
        city = (_JACOW_CONF_TABLE.get(m.group(1).lower(), {}).get(m.group(2)) or {}
                ).get("city", "")
    except Exception:  # noqa: BLE001
        pass
    city = city or (ctx.facts.get("city") or ("", ""))[0]
    at = ctx.text.find(f", {city}", venue_start) if city else -1
    venue = ctx.text[venue_start:at] if at >= 0 else ""
    if not venue.strip() or len(venue) > 160:
        yield _issue(ctx, "REF-PROC-NAME", ERROR, f"This is a JACoW paper from {label} (its "
                     f"DOI says so): 'in Proc. … ({label})'.", RULE_PROC, venue_start,
                     len(ctx.text), why_not="where the conference's name ends in the text "
                     "is not clear")
        return
    # Annex B: "in Proc. 13th Int. Comput. Accel. Phys. Conf. (ICAP'18)". The
    # author's name of the conference stays; "in Proc." and the label are added.
    name = venue.strip().rstrip(",")
    proc = "" if re.match(r"(?:in\s+)?Proc\b", name) else "in Proc. "
    if re.match(r"Proc\b", name):
        proc = "in "
    lead = ctx.text[rest_start:venue_start]
    comma_inside = ctx.text[:rest_start].rstrip().endswith(",\u201d")
    lead_new = " " if comma_inside else ", "
    yield _issue(ctx, "REF-PROC-NAME", ERROR, f"This is a JACoW paper from {label} (its DOI "
                 f"says so): 'in Proc. {name} ({label})'.", RULE_PROC, rest_start,
                 venue_start + len(venue.rstrip().rstrip(",")),
                 f"{lead_new}{proc}{name} ({label})", presentation=False,
                 removals=tuple(w for w in re.findall(r"[A-Za-z]+", lead) if w != "in"))


_MONTHS = {"january": "Jan.", "february": "Feb.", "march": "Mar.", "april": "Apr.",
           "may": "May", "june": "Jun.", "july": "Jul.", "august": "Aug.",
           "september": "Sep.", "sept": "Sep.", "october": "Oct.", "november": "Nov.",
           "december": "Dec.", "jan": "Jan.", "feb": "Feb.", "mar": "Mar.", "apr": "Apr.",
           "jun": "Jun.", "jul": "Jul.", "aug": "Aug.", "sep": "Sep.", "oct": "Oct.",
           "nov": "Nov.", "dec": "Dec."}


@rule
def months(ctx: Context):
    start = _venue_start(ctx)
    pattern = re.compile(r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) +
                         r")\b(\.?)(\s*,)?(?=\s+(?:\d{1,2},\s+)?\d{4}\b)", re.I)
    for m in pattern.finditer(ctx.text, start):
        want = _MONTHS[m.group(1).lower()]
        written = m.group(1) + m.group(2)
        if written != want:
            yield _issue(ctx, "REF-MONTH", ERROR, f"'{written}' is written '{want}'.",
                         RULE_MONTH, m.start(), m.start() + len(written), want)
        if m.group(3):
            at = m.start() + len(written)
            yield _issue(ctx, "REF-MONTH", ERROR, "No comma between month and year.",
                         RULE_MONTH, at, at + len(m.group(3)), "")


# ---------------------------------------------------------------------------
# Pages, volume, journal
# ---------------------------------------------------------------------------

@rule
def pages(ctx: Context):
    text = ctx.text
    for m in re.finditer(r"\b(pp?),\s*(?=\d)", text):
        yield _issue(ctx, "REF-PAGES", ERROR, f"'{m.group(0).strip()}' is written "
                     f"'{m.group(1)}.'.", RULE_PROC, m.start(), m.end(), f"{m.group(1)}. ")
    for m in re.finditer(r"\b(pp?\.)\s*(\d{1,3})\s(\d{3})\b(?!\s*[-\u2013])", text):
        joined = f"{m.group(1)} {m.group(2)}{m.group(3)}"
        yield _issue(ctx, "REF-PAGES", ERROR, "An article number is written without a "
                     "space.", RULE_JOURNAL, m.start(), m.end(), joined,
                     substitutions=((m.group(0), joined),))
    for m in re.finditer(r"\bpp\.\s*([A-Z]?\d+)\b(?!\s*[-\u2013\u2014]\s*[A-Z]?\d|\.\d|\s\d{3}\b)",
                         text):
        number = m.group(1)
        if len(number.strip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) >= 5 or number.startswith("0") \
                or number[0].isalpha():
            yield _issue(ctx, "REF-PAGES", ERROR, f"A single article number is 'p. {number}', "
                         "not 'pp.'.", RULE_JOURNAL, m.start(), m.start(1), "p. ",
                         removals=("pp",))
        else:
            known = ctx.facts.get("pages")
            if known and re.fullmatch(rf"{number}\s*[-\u2013]\s*\d+", known[0]):
                rng = known[0].replace("\u2013", "-")
                yield _issue(ctx, "REF-PAGES-RANGE", WARNING, f"Only the first page; "
                             f"{known[1]} gives pp. {rng}.", RULE_PROC, m.start(1),
                             m.end(1), rng, presentation=False, additions=(rng,),
                             source=known[1])
            else:
                yield _issue(ctx, "REF-PAGES-RANGE", WARNING, f"'pp. {number}' gives one "
                             "page: the range is incomplete.", RULE_PROC, m.start(), m.end(),
                             who=EDITOR, why_not="the last page is not in the reference",
                             needs="the paper's page range")
    for m in re.finditer(r"\bp\.\s*(\d+)\s*[-\u2013]\s*(\d+)", text):
        yield _issue(ctx, "REF-PAGES", ERROR, "A page range is 'pp.', not 'p.'.",
                     RULE_PROC, m.start(), m.start() + 2, "pp.", removals=("p",))


@rule
def volume_issue(ctx: Context):
    text = ctx.text
    for m in re.finditer(r"(?<=[A-Za-z.])(\s+)(?=vol\.\s*\d)", text):
        if m.start() >= _venue_start(ctx):
            yield _issue(ctx, "REF-VOLUME", ERROR, "A comma before 'vol.'.", RULE_JOURNAL,
                         m.start(), m.end(), ", ")
    for m in re.finditer(r"\b(?:Vol\.?|vol(?!\.)|Volume|volume)\s*(?=\d)", text):
        yield _issue(ctx, "REF-VOLUME", ERROR, f"'{m.group(0).strip()}' is written "
                     "'vol.'.", RULE_JOURNAL, m.start(), m.end(), "vol. ")
    for m in re.finditer(r"(\bvol\.\s*\d+\s*,\s*)(Issue|issue|No\.|Nr\.|Number|number|N\.)"
                         r"\s*(?=\d)", text):
        yield _issue(ctx, "REF-VOLUME", ERROR, f"'{m.group(2)}' is written 'no.'.",
                     RULE_JOURNAL, m.start(2), m.end(), "no. ", removals=("Issue", "Nr", "N"))


# Words that appear abbreviated in journal names (ISO 4), without their full stop.
_ABBREV_WORDS = {
    "Phys", "Rev", "Lett", "Sci", "Rep", "Nucl", "Instrum", "Meth", "Res", "Sect",
    "Accel", "Appl", "Commun", "Comput", "Chem", "Radioanal", "Mod", "Int", "Opt", "Technol",
    "Eng", "Mater", "Trans", "Magn", "Supercond", "Spec", "Top", "Eur", "Astrophys",
    "Math", "Mech", "Natl", "Acad", "Nat", "Photon", "Med", "Biol", "Ser", "Conf",
    "Part", "Jpn", "Chin", "Soc", "Am", "Inst", "Proc", "Theor", "Exp", "Perspect", "Rad", "Radiat", "Detect", "Vac", "Surf", "Struct", "Dyn", "Syst", "Stat",
    "Ann", "Annu", "Adv", "Prog", "Sov", "Fiz", "Zh", "Usp", "Ultrason", "Ferroelectr",
    "Freq", "Contr", "Microw", "Propag",
}


def _journal_key(name: str) -> str:
    name = name.lower().replace("&", "and")
    name = re.sub(r"\bsect(?:ion)?\b\.?", " ", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


_ANNEX_C: dict[str, str] | None = None


def annex_c() -> dict[str, str]:
    """JACoW's own journal abbreviations (Annex C): full name or variant -> abbreviation."""
    global _ANNEX_C
    if _ANNEX_C is None:
        table: dict[str, str] = {}
        path = (__import__("pathlib").Path(__file__).resolve().parents[1] / "knowledge" /
                "jacow-paper-formatting-skill" / "references" / "journal-abbreviations.md")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$", line)
            if not m or m.group(1) in ("Abbreviation", "---") or set(m.group(1)) <= {"-"}:
                continue
            abbreviation, full = m.group(1), m.group(2)
            for name in (full, full.split(":")[0], abbreviation):
                table.setdefault(_journal_key(name), abbreviation)
        _ANNEX_C = table
    return _ANNEX_C


def journal_span(ctx: Context) -> tuple[int, int] | None:
    """Where the journal's name is: after the title (or the authors), before the volume."""
    if not (ctx.parts.title or ctx.parts.authors):
        return None
    rest_start = ctx.parts.rest[0]
    lead = re.match(r"[\s,]*", ctx.text[rest_start:])
    start = rest_start + lead.end()
    head = ctx.text[start:]
    if re.match(r"(?:in\s+Proc|presented|in\s+[A-Z]|[A-Z][a-z]{2}\.?\s+\d{4}|\d{4}|arXiv|"
                r"https?:|doi:|Ph\.\s?D|M\.\s?S|[Ss]ubmitted|[Uu]npublished|[Pp]rivate)", head):
        return None
    end = re.search(r"\s*,?\s*(?:vol\.|Vol\.|vol\s|no\.|pp?\.|\d|\(|to be published|"
                    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|"
                    r"[Aa]ccepted|[Ss]ubmitted|$)", head)
    if not end or end.start() == 0:
        return None
    name = head[:end.start()].rstrip(" ,")
    if len(name) > 90 or not re.search(r"[A-Za-z]", name):
        return None
    return start, start + len(name)


@rule
def journal_name(ctx: Context):
    span = journal_span(ctx)
    if not span:
        return
    name = ctx.text[span[0]:span[1]]
    tokens = name.split()
    bare = [t for t in tokens if t.rstrip(",") in _ABBREV_WORDS]
    if bare and all(t.endswith(".") or t.rstrip(",") in _ABBREV_WORDS or len(t) == 1 or
                    t in ("of", "and", "&") or t.isupper() for t in tokens):
        fixed = " ".join(t + "." if t in _ABBREV_WORDS or (t == "J" and i < len(tokens) - 1)
                         else t for i, t in enumerate(tokens))
        if fixed != name:
            yield _issue(ctx, "REF-JOURNAL", ERROR, f"Abbreviated words end with a full "
                         f"stop ('{fixed}').", RULE_JOURNAL, span[0], span[1], fixed)
            return
    if not re.match(r"\s*,?\s*(?:vol\.|Vol\.|\d+\s*[,(:])", ctx.text[span[1]:]):
        return                           # not followed by a volume: maybe not a journal
    # JACoW's own list (Annex C) first: "Nucl. Instrum. Methods Phys. Res. A".
    listed = annex_c().get(_journal_key(name))
    if listed:
        if getattr(ctx.style, "applied_physics", "App.") == "Appl.":
            listed = re.sub(r"^App\. ", "Appl. ", listed)
        if listed != name:
            yield _issue(ctx, "REF-JOURNAL", ERROR, f"JACoW abbreviates the journal "
                         f"'{listed}' (Annex C).", RULE_JOURNAL, span[0], span[1], listed,
                         presentation=False, substitutions=((name, listed),))
        return
    try:
        from jacow_formatter.journals import normalize_journal
        short = normalize_journal(name)
    except Exception:  # noqa: BLE001
        return
    if short and short != name and "." in short and len(short) <= len(name) + 12 \
            and short.lower().replace(".", "") != name.lower().replace(".", ""):
        # Only the full name to its ISO 4 form, never the other way.
        if sum(t.endswith(".") for t in short.split()) >= sum(t.endswith(".") for t in tokens):
            yield _issue(ctx, "REF-JOURNAL", ERROR, f"The journal's ISO 4 abbreviation is "
                         f"'{short}'.", RULE_JOURNAL, span[0], span[1], short,
                         presentation=False, substitutions=((name, short),))


@rule
def journal_in(ctx: Context):
    if not ctx.parts.title:
        return
    m = re.match(r"(\s*,?\s*)([Ii]n:?)\s+(?=[A-Z][a-z]*\.\s|[A-Z][a-z]+\s+(?:Rev|Lett|J)\b)",
                 ctx.text[ctx.parts.rest[0]:])
    if m and not ctx.text[ctx.parts.rest[0] + m.end():].startswith("Proc"):
        start = ctx.parts.rest[0] + m.start(2)
        yield _issue(ctx, "REF-JOURNAL", ERROR, "No 'in' before a journal's name.",
                     RULE_JOURNAL, start, ctx.parts.rest[0] + m.end(), "",
                     removals=("in",))


_PHYS_STYLE = re.compile(
    r"(?P<j>[A-Z][A-Za-z.&'\- ]*?[A-Za-z.])\s*,?\s+(?P<v>\d+)\s*(?:\((?P<n>\d+)\))?\s*[,:]\s*"
    r"(?:(?P<pp>pp?\.)\s*)?(?P<p>[A-Z]?\d+(?:\s*[-\u2013]\s*\d+)?)(?!\d)"
    r"(?:\s*,?\s*(?:\((?P<y>\d{4})\)|(?P<m>[A-Z][a-z]{2,8}\.?\s+)?(?P<y2>\d{4}))(?!\d))?")


@rule
def journal_layout(ctx: Context):
    """'Part. Accel. 17, pp. 143-155 (1985)' -> 'Part. Accel., vol. 17, pp. 143-155, 1985'."""
    if not (ctx.parts.title or ctx.parts.authors) or re.search(r"\bvol\.", ctx.text):
        return
    rest_start = ctx.parts.rest[0]
    lead = re.match(r"[\s,]*", ctx.text[rest_start:])
    start = rest_start + lead.end()
    m = _PHYS_STYLE.match(ctx.text, start)
    if not m or re.match(r"(?:in\s+Proc|presented|Proc\.)", m.group("j")):
        return
    if re.search(r"\b(?:Report|Preprint|Note|Memo|Technical|[Tt]hesis)\b|\bRep\.\s*(?:No|[A-Z]+-)"
                 r"|\bNo\.$|\bed\.", m.group("j")) or re.fullmatch(r"(?:19|20)\d{2}", m.group("v")):
        return                           # a report number, or a year, not a volume
    journal, page = m.group("j").rstrip(" ,"), re.sub(r"\s+", "", m.group("p"))
    marker = "pp." if re.search(r"[-\u2013]", page) else "p."
    year = m.group("y") or m.group("y2")
    parts = [journal, f"vol. {m.group('v')}"]
    if m.group("n"):
        parts.append(f"no. {m.group('n')}")
    parts.append(f"{marker} {page}")
    if year:
        parts.append(f"{m.group('m').strip()} {year}" if m.group("m") else year)
    replacement = ", ".join(parts)
    yield _issue(ctx, "REF-JOURNAL-LAYOUT", ERROR, "A journal reference is laid out "
                 "'Journal, vol. V, p. P, Year'.", RULE_JOURNAL, start, m.end(), replacement,
                 presentation=False, removals=("pp", "p"))
    if not year:
        known = ctx.facts.get("year")
        yield _issue(ctx, "REF-YEAR-MISSING", WARNING, "A journal reference gives the "
                     "year" + (f"; {known[1]} gives {known[0]}." if known else "."),
                     RULE_JOURNAL, start, m.end(), who=MODEL if known else EDITOR,
                     why_not="the year is not in the reference",
                     needs="" if known else "the year of publication")


@rule
def year_in_brackets(ctx: Context):
    for m in re.finditer(r",?\s*\((\d{4})\)(?=\s*\.?\s*(?:doi:|https?://|$))", ctx.text):
        yield _issue(ctx, "REF-YEAR", ERROR, "The year is not in brackets: '…, 1985.'.",
                     ANNEX_B, m.start(), m.end(), f", {m.group(1)}")


@rule
def accepted(ctx: Context):
    m = re.search(r",?\s*\b[Aa]ccepted(?:\s+for\s+publication)?(?:\s+(?:on\s+)?(?:\d{1,2}\s+)?"
                  r"[A-Z][a-z]+\.?,?\s+\d{4}|\s+in\s+\d{4})?", ctx.text)
    if m and "to be published" not in ctx.text:
        yield _issue(ctx, "REF-STATUS", WARNING, "A paper accepted for publication is cited "
                     "'…, Journal, to be published.'.", ANNEX_B, m.start(), m.end(),
                     ", to be published", presentation=False, removals=(m.group(0),))
    m = re.search(r"\bin\s+preparation\b", ctx.text, re.I)
    if m:
        yield _issue(ctx, "REF-STATUS", WARNING, "Annex B has no 'in preparation': a paper "
                     "not yet submitted is cited as 'unpublished', a submitted one as "
                     "'submitted for publication'.", ANNEX_B, m.start(), m.end(), who=EDITOR,
                     why_not="whether it has been submitted is for the author to say",
                     needs="the paper's status from the author")


# ---------------------------------------------------------------------------
# Punctuation and leftovers
# ---------------------------------------------------------------------------

@rule
def punctuation(ctx: Context):
    text = ctx.text
    cases = ((r"\s+(?=[,;])", ""), (r"(?<=[A-Za-z0-9)\u201d])\s+(?=\.(?:\s|$))", ""),
             (r",(?=\s*,)", ""), (r"(?<=\w)\.\.(?!\.)", "."), (r"(?<=\S)\s{2,}(?=\S)", " "))
    for pattern, replacement in cases:
        for m in re.finditer(pattern, text):
            yield _issue(ctx, "REF-PUNCT", INFO, "Stray space or punctuation.", ANNEX_B,
                         m.start(), m.end(), replacement)


@rule
def latex_left(ctx: Context):
    for m in re.finditer(r"\\[A-Za-z]+\*?", ctx.text):
        yield _issue(ctx, "REF-LATEX", WARNING, f"A LaTeX command '{m.group(0)}' is left in "
                     "the reference.", ANNEX_B, m.start(), m.end(),
                     why_not="what it was meant to produce depends on the command")


@rule
def end_full_stop(ctx: Context):
    text = ctx.text.rstrip()
    if not text:
        return
    if re.search(r"(?:\bdoi:\S+|https?://\S+)$", text):
        if text.endswith(".") and re.search(r"https?://\S+\.$", text):
            yield _issue(ctx, "REF-END", INFO, "No full stop after a URL at the end.",
                         RULE_END, len(text) - 1, len(ctx.text), "")
        return
    if not text.endswith((".", "?", "!", "\u201d")):
        yield _issue(ctx, "REF-END", INFO, "The reference ends with a full stop.", RULE_END,
                     len(text), len(ctx.text), ".")


@rule
def doi_from_lookup(ctx: Context):
    known = ctx.facts.get("doi")
    if not known or dois(ctx.text) or not known[1]:
        return
    doi = known[0]
    if re.search(r"\bpresented at\b|\bthis conference\b|\bunpublished\b|\bsubmitted\b|"
                 r"\bprivate communication\b|\bin preparation\b", ctx.text, re.I):
        return                           # a talk, a manuscript: no DOI to add
    if doi.lower().startswith("10.48550/arxiv.") and not re.search(r"arxiv", ctx.text, re.I):
        return                           # the preprint's DOI is not the cited paper's
    jacow = JACOW_DOI_RE.fullmatch(doi)
    if jacow:
        named = _named_conference(ctx)
        if named and (named[0].lower() != jacow.group(1).lower()
                      or named[1] != jacow.group(2)[-2:]):
            return                       # the lookup found another conference's paper
    body = ctx.text.rstrip()
    url = re.search(r"[\s,.;]*\bhttps?://\S+?[.]?$", body)
    if url:
        # Annex B: a URL only when there is no DOI. The DOI takes its place.
        yield _issue(ctx, "REF-DOI-MISSING", WARNING, f"No DOI; {known[1]} gives doi:{doi}, "
                     "which takes the place of the web address.", RULE_DOI, url.start(),
                     len(ctx.text), f". doi:{doi}", presentation=False, additions=(doi,),
                     removals=(url.group(0).strip(" ,.;"),), source=known[1])
        return
    end = len(body.rstrip("."))
    yield _issue(ctx, "REF-DOI-MISSING", WARNING, f"No DOI; {known[1]} gives doi:{doi}.",
                 RULE_DOI, end, len(ctx.text), f". doi:{doi}", presentation=False,
                 additions=(doi,), source=known[1])


@rule
def pages_from_lookup(ctx: Context):
    known = ctx.facts.get("pages")
    jacow = any(JACOW_DOI_RE.fullmatch(d) for _, _, d in dois(ctx.text))
    if not jacow or re.search(r"\bpp?[.,]\s*\d", ctx.text) or "presented at" in ctx.text:
        return
    last = _last_doi(ctx.text)
    if not last:
        return
    cut = len(ctx.text[:last[0]].rstrip(" ."))
    if known and known[1]:
        rng = known[0].replace("\u2013", "-")
        marker = "pp." if "-" in rng else "p."
        yield _issue(ctx, "REF-PAGES-MISSING", WARNING, f"No pages; {known[1]} gives "
                     f"{marker} {rng}.", RULE_PROC, cut, cut, f", {marker} {rng}",
                     presentation=False, additions=(rng,), source=known[1])
    else:
        yield _issue(ctx, "REF-PAGES-MISSING", WARNING, "A published JACoW paper is cited "
                     "with its pages.", RULE_PROC, cut, cut, who=EDITOR,
                     why_not="the pages are not in the reference",
                     needs="the paper's pages (refs.jacow.org)")


@rule
def proceedings_missing(ctx: Context):
    if not ctx.parts.title:
        return
    m = _conference_re().search(ctx.text, ctx.parts.rest[0])
    if not m:
        return
    before = ctx.text[ctx.parts.rest[0]:m.start()]
    published = any(JACOW_DOI_RE.fullmatch(d) for _, _, d in dois(ctx.text)) or \
        re.search(r"\bpp?\.\s*\d", ctx.text)
    if re.search(r"\bProc\b|\bpresented\b|\bat\b|\bin\b", before) or not published:
        return
    if before.strip(" ,"):
        return                           # something else stands before it
    yield _issue(ctx, "REF-PROC-FORM", ERROR, "A paper in published proceedings is cited "
                 "'in Proc. CONF'YY'.", RULE_PROC, m.start(), m.start(), "in Proc. ",
                 presentation=False)


@rule
def conference_year(ctx: Context):
    m = _conference_re().search(ctx.text, _venue_start(ctx))
    if not m:
        return
    label_year = m.group(2)[-2:]
    dates = [d for d in re.findall(r"(?:^|[\s,(])((?:19|20)\d{2})(?=[\s,.)]|$)",
                                   ctx.text[m.end():]) if not d.endswith(label_year)]
    written = [d for d in re.findall(r"(?:^|[\s,(])((?:19|20)\d{2})(?=[\s,.)]|$)",
                                     ctx.text[m.end():])]
    if written and all(not d.endswith(label_year) for d in written[:1]) and dates:
        yield _issue(ctx, "REF-PROC-YEAR", ERROR, f"{m.group(1).upper()}'{label_year} was "
                     f"held in {'19' if int(label_year) > 50 else '20'}{label_year}, but the "
                     f"reference gives {written[0]}: one of them is wrong.", RULE_PROC,
                     m.start(), m.end(), who=EDITOR,
                     why_not="only the proceedings can say which is right",
                     needs="the conference's year (refs.jacow.org)")


@rule
def journal_order(ctx: Context):
    span = journal_span(ctx)
    if not span:
        return
    m = re.match(r"(\s*,\s*)((?:[A-Z][a-z]{2}\.?\s+)?(?:19|20)\d{2})(\s*,\s*)(pp?\.\s*[A-Z]?\d+"
                 r"(?:\s*[-\u2013]\s*\d+)?)", ctx.text[span[1]:])
    if not m:
        return
    start = span[1]
    end = start + m.end()
    yield _issue(ctx, "REF-JOURNAL-ORDER", ERROR, "In a journal reference the pages come "
                 "before the year ('…, pp. 308-313, 1965').", RULE_JOURNAL, start, end,
                 f", {m.group(4)}, {m.group(2)}", presentation=False)


@rule
def journal_pages(ctx: Context):
    """A journal article with a volume but no page or article number."""
    m = re.search(r"\bvol\.\s*\d+(?:\s*,\s*no\.\s*[\d\u2013-]+)?", ctx.text)
    if not m or re.search(r"\bpp?\.\s*[A-Z]?\d", ctx.text) or not journal_span(ctx):
        return
    if ctx.kind and ctx.kind not in ("journal",):
        return
    known = ctx.facts.get("pages")
    if known and known[1]:
        value = known[0].replace("\u2013", "-")
        marker = "pp." if "-" in value else "p."
        yield _issue(ctx, "REF-PAGES-MISSING", WARNING, f"No page or article number; "
                     f"{known[1]} gives {marker} {value}.", RULE_JOURNAL, m.end(), m.end(),
                     f", {marker} {value}", presentation=False, additions=(value,),
                     source=known[1])
    else:
        yield _issue(ctx, "REF-PAGES-MISSING", WARNING, "A journal article is cited with its "
                     "page or article number.", RULE_JOURNAL, m.start(), m.end(), who=EDITOR,
                     why_not="it is not in the reference",
                     needs="the article number or pages (from the DOI's record)")


@rule
def journal_volume(ctx: Context):
    span = journal_span(ctx)
    if not span or re.search(r"\bvol\.", ctx.text) or not re.search(r"\bpp?\.\s*[A-Z]?\d",
                                                                     ctx.text):
        return
    if ctx.kind and ctx.kind not in ("journal", "journal_accepted"):
        return
    if re.match(r"\s*,?\s*\d+\s*[,(:]", ctx.text[span[1]:]):
        return                           # "Journal, 17, p. …": the volume is there, bare
    known = ctx.facts.get("volume")
    issue_no = ctx.facts.get("issue")
    if known and known[1]:
        insert = f", vol. {known[0]}" + (f", no. {issue_no[0]}" if issue_no and issue_no[1]
                                         else "")
        added = (known[0],) + ((issue_no[0],) if issue_no and issue_no[1] else ())
        yield _issue(ctx, "REF-VOLUME-MISSING", WARNING, f"No volume; {known[1]} gives "
                     f"vol. {known[0]}.", RULE_JOURNAL, span[1], span[1], insert,
                     presentation=False, additions=added, source=known[1])
    else:
        yield _issue(ctx, "REF-VOLUME-MISSING", WARNING, "A journal reference gives the "
                     "volume.", RULE_JOURNAL, span[0], span[1], who=EDITOR,
                     why_not="the volume is not in the reference",
                     needs="the journal volume (from the DOI's record)")


@rule
def authors_form(ctx: Context):
    found, _ = names(ctx.text, ctx.parts.authors)
    if not ctx.parts.authors or not found or people(found):
        return
    body = ctx.parts.get(ctx.parts.authors)
    if len(body) > 120 or not re.search(r"\d{4}|\b[A-Z][a-z]+,\s+[A-Z]\.,", body):
        return                           # perhaps not authors at all (a book's title)
    yield _issue(ctx, "REF-AUTH-FORM", ERROR, "The author list is not in the JACoW form "
                 "('A. B. Surname, C. Surname, and D. Surname,').", RULE_AUTHORS,
                 ctx.parts.authors[0], ctx.parts.authors[1],
                 why_not="the names have to be read apart from what else is there (a year)")


@rule
def facts_disagree(ctx: Context):
    """A value a lookup verified, by the reference's own DOI, that the text contradicts."""
    if not dois(ctx.text):
        return
    known = ctx.facts.get("pages")
    m = re.search(r"\bpp?\.\s*([A-Z]?\d+)(?:\s*[-\u2013]\s*(\d+))?", ctx.text)
    if known and known[1] and m:
        fact = known[0].replace("\u2013", "-").replace(" ", "")
        written = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
        first = fact.split("-")[0]
        if written != fact and m.group(1) != first:
            yield _issue(ctx, "REF-FACT-PAGES", ERROR, f"The pages differ from {known[1]} "
                         f"for this DOI: the reference gives {written}, {known[1]} {fact}.",
                         RULE_PROC, m.start(), m.end(), who=EDITOR,
                         why_not="either the pages or the DOI is wrong, and only the paper "
                         "can say which", needs="the cited paper itself")
    known = ctx.facts.get("volume")
    m = re.search(r"\bvol\.\s*(\d+)", ctx.text)
    if known and known[1] and m and m.group(1) != str(known[0]).strip():
        yield _issue(ctx, "REF-FACT-VOLUME", ERROR, f"The volume differs from {known[1]} for "
                     f"this DOI: the reference gives {m.group(1)}, {known[1]} {known[0]}.",
                     RULE_JOURNAL, m.start(), m.end(), who=EDITOR,
                     why_not="either the volume or the DOI is wrong",
                     needs="the cited paper itself")


#: What each kind of fix does, in a few words, for the message on the card.
FIXED = {
    "REF-DOI-URL": "DOI written doi:… instead of as a web address",
    "REF-DOI-FORM": "DOI written doi:…", "REF-DOI-TWICE": "repeated DOI removed",
    "REF-DOI-END": "no full stop after the DOI", "REF-DOI-SEP": "full stop before the DOI",
    "REF-DOI-INCOMPLETE": "JACoW DOI completed", "REF-DOI-MISSING": "DOI added",
    "REF-ARXIV-URL": "arXiv cited by its identifier", "REF-ARXIV-PREPRINT": "'arXiv preprint' removed",
    "REF-ARXIV-DOI": "arXiv DOI added", "REF-URL-ONLINE": "'[Online]. Available:' removed",
    "REF-URL-DOI": "web address repeating the DOI removed",
    "REF-URL-JACOW": "JACoW paper cited by DOI or paper ID, not its PDF",
    "REF-PAPER-ID": "paper ID removed (the JACoW DOI is given)",
    "REF-ETAL": "'et al.' written correctly", "REF-ETAL-COMMA": "comma before 'et al.'",
    "REF-AUTH-ORDER": "names as initials first", "REF-AUTH-INITIALS": "spaced initials",
    "REF-AUTH-INITIAL": "initial's full stop", "REF-AUTH-GIVEN": "initials instead of first names",
    "REF-AUTH-AND": "'and' / ', and' between names", "REF-AUTH-MANY": "more than six authors as 'et al.'",
    "REF-TITLE-QUOTES": "curly quotes around the title", "REF-TITLE-COMMA": "comma after the title's quotes",
    "REF-TITLE-CAPS": "title in sentence case", "REF-TITLE-CASE": "title in sentence case",
    "REF-TITLE-NAME": "a name's capital in the title",
    "REF-PROC-FORM": "'in Proc. …'", "REF-PROC-LABEL": "conference as CONF'YY",
    "REF-PROC-NAME": "JACoW conference as 'in Proc. CONF'YY'", "REF-MONTH": "month abbreviation",
    "REF-PAGES": "'p.'/'pp.' and page numbers", "REF-PAGES-RANGE": "page range completed",
    "REF-PAGES-MISSING": "pages added", "REF-VOLUME": "'vol.' and 'no.'",
    "REF-VOLUME-MISSING": "volume added", "REF-JOURNAL": "journal's ISO 4 abbreviation",
    "REF-JOURNAL-LAYOUT": "journal laid out 'Journal, vol. V, p. P, Year'",
    "REF-JOURNAL-ORDER": "pages before the year", "REF-YEAR": "year without brackets",
    "REF-STATUS": "'to be published'", "REF-PUNCT": "stray spaces", "REF-END": "final full stop",
    "REF-TITLE-HYPHEN": "hyphen in the title", "REF-REPEATED": "repeated word removed",
    "REF-PLACE": "US state as its postal code",
    "REF-LOOKALIKE": "Cyrillic look-alike letters made Latin",
    "REF-DOI-WRONG": "wrong DOI corrected",
    "REF-DOI-POSSIBLE": "possible DOI (check it)",
}


@rule
def title_holds_names(ctx: Context):
    """A quoted "title" that is really the author list (a garbled rewrite)."""
    title = ctx.parts.get(ctx.parts.title)
    if title and (re.match(r"\s*[A-Z]\.,?\s", title)
                  or len(re.findall(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)?,\s+[A-Z]\.", title)) >= 2):
        yield _issue(ctx, "REF-TITLE-NAMES", ERROR, "The quoted title seems to hold author "
                     "names.", RULE_TITLE, ctx.parts.title[0], ctx.parts.title[1],
                     why_not="where the names end and the title begins has to be read")


@rule
def title_broken_hyphen(ctx: Context):
    """'multi- charge': a hyphen left from a line break, with a space after it."""
    title = ctx.parts.title
    if not title:
        return
    for m in re.finditer(r"\b([A-Za-z]{2,})-\s+([a-z]{2,})\b", ctx.text[title[0]:title[1]]):
        if m.group(2) in ("and", "or", "to", "nor", "versus", "vs", "as"):
            continue                     # "first- and second-order": a suspended hyphen
        start = title[0] + m.start()
        yield _issue(ctx, "REF-TITLE-HYPHEN", WARNING, f"'{m.group(0)}' has a space after the "
                     f"hyphen ('{m.group(1)}-{m.group(2)}').", RULE_TITLE, start,
                     title[0] + m.end(), f"{m.group(1)}-{m.group(2)}")


@rule
def repeated_word(ctx: Context):
    """'May, May 1996': the same word twice in a row."""
    for m in re.finditer(r"\b([A-Z][A-Za-z]*\.?),\s+\1(?=[\s,.])", ctx.text):
        if m.group(1) in ("A", "B", "C", "D", "E"):
            continue                     # "Phys. Rev. A, A" is not a slip worth guessing
        yield _issue(ctx, "REF-REPEATED", ERROR, f"'{m.group(1)}' is written twice.", ANNEX_B,
                     m.start(), m.start() + len(m.group(1)) + 2, "", removals=(m.group(1),))


@rule
def stop_before_url(ctx: Context):
    """'code., https://…': a full stop and a comma before a URL."""
    for m in re.finditer(r"(?<=[a-z])\.(?=,\s*https?://)", ctx.text):
        yield _issue(ctx, "REF-PUNCT", INFO, "A full stop before the comma.", ANNEX_B,
                     m.start(), m.end(), "")


_US_STATES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI",
    "Wyoming": "WY"}


@rule
def us_state(ctx: Context):
    """'Newport News, Virginia, USA' -> 'Newport News, VA, USA' (Annex B: 'Chicago, IL, USA')."""
    names_ = "|".join(sorted(_US_STATES, key=len, reverse=True))
    for m in re.finditer(rf"(?<=,\s)({names_})(?=,\s*(?:USA|U\.S\.A\.|US|United States)\b)",
                         ctx.text):
        if m.start() < _venue_start(ctx):
            continue
        code = _US_STATES[m.group(1)]
        yield _issue(ctx, "REF-PLACE", WARNING, f"US states are written as their postal code "
                     f"('{code}').", RULE_PROC, m.start(), m.end(), code, presentation=False,
                     substitutions=((m.group(1), code),))


# Cyrillic letters that look like Latin ones, from copying text out of a PDF.
_HOMOGLYPHS = str.maketrans({"\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
                             "\u0441": "c", "\u0445": "x", "\u0443": "y", "\u0410": "A",
                             "\u0412": "B", "\u0415": "E", "\u041d": "H", "\u041a": "K",
                             "\u041c": "M", "\u041e": "O", "\u0420": "P", "\u0421": "C",
                             "\u0422": "T", "\u0425": "X", "\u0423": "Y"})


@rule
def lookalike_letters(ctx: Context):
    """'Proc. РАС'О3, рр. 470' (Cyrillic Р, А, С, О, р) in a Latin reference."""
    latin = len(re.findall(r"[A-Za-z]", ctx.text))
    cyrillic = len(re.findall(r"[\u0400-\u04ff]", ctx.text))
    if not cyrillic or latin < 3 * cyrillic:
        return                           # a reference written in Cyrillic: leave it
    for m in re.finditer(r"[\w'\u2019]*[\u0400-\u04ff][\w'\u2019]*", ctx.text):
        word = m.group(0)
        # "РАС'О3": an O among digits was a zero.
        fixed = re.sub(r"[\u041e\u043e](?=\d)|(?<=\d)[\u041e\u043e]", "0", word)
        fixed = fixed.translate(_HOMOGLYPHS)
        if fixed != word and not re.search(r"[\u0400-\u04ff]", fixed):
            # Declared with a word either side: a one-letter substitution would
            # also mask every Latin "a" in the reference.
            left = re.search(r"\S*\s*$", ctx.text[:m.start()])
            right = re.match(r"\s*\S*", ctx.text[m.end():])
            before = ctx.text[left.start():m.end() + right.end()]
            after = ctx.text[left.start():m.start()] + fixed + ctx.text[m.end():m.end() + right.end()]
            yield _issue(ctx, "REF-LOOKALIKE", ERROR, f"'{word}' has Cyrillic letters that "
                         f"look Latin ('{fixed}').", ANNEX_B, m.start(), m.end(), fixed,
                         substitutions=((before, after),))


@rule
def doi_in_url(ctx: Context):
    """'https://link.aps.org/doi/10.1103/…' with no DOI given: the DOI, written doi:…."""
    if any(True for _ in re.finditer(r"\bdoi:\s*10\.", ctx.text, re.I)):
        return
    for m in re.finditer(r"https?://(?!(?:dx\.)?doi\.org/)\S*?/(10\.\d{4,9}/[^\s?#]+)", ctx.text):
        doi = doi_end(m.group(1))
        url_end = m.start() + len(m.group(0).rstrip(".,;"))
        tail = ctx.text[m.end():url_end]
        if tail.strip():
            continue                     # the URL goes on past the DOI (a query)
        yield _issue(ctx, "REF-URL-DOI", WARNING, f"The web address holds the DOI: "
                     f"doi:{doi}.", RULE_DOI, m.start(), m.start(1) + len(doi), f"doi:{doi}",
                     presentation=False, removals=(m.group(0)[:m.start(1) - m.start()],))



@rule
def doi_spelling(ctx: Context):
    """'doi:10.1103/PhysRevSTAB.17.021007\\vskip3mm', '10,1103/…': the DOI's spelling repaired."""
    from src.refcheck.doi import clean, written_dois

    for start, end, written in written_dois(ctx.text):
        right = clean(written.replace("10,", "10.", 1))
        if right != written and right and DOI_RE.fullmatch(right):
            yield _issue(ctx, "REF-DOI-FORM", ERROR, f"The DOI is written '{written}'; it is "
                         f"'{right}'.", RULE_DOI, start, end, right,
                         substitutions=((written, right),))


@rule
def doi_correction(ctx: Context):
    """A DOI a registry shows to be wrong, replaced by the one it gives for this reference."""
    from src.refcheck.doi import written_dois

    fix_ = ctx.facts.get("doi_fix")
    if fix_:
        written, right, source, reason = fix_
        # The whole DOI as written, never a prefix of the corrected one.
        for start, end, doi in written_dois(ctx.text):
            if doi == written and right and right.lower() != written.lower():
                yield _issue(ctx, "REF-DOI-WRONG", ERROR, f"Wrong DOI: {reason}.", RULE_DOI,
                             start, end, right, presentation=False, additions=(right,),
                             removals=(written,), source=source)
    problem = ctx.facts.get("doi_problem")
    if problem:
        written, reason = problem
        at = ctx.text.find(written)
        yield _issue(ctx, "REF-DOI-UNRESOLVED", ERROR, f"Wrong DOI: {reason}.", RULE_DOI,
                     at, at + len(written) if at >= 0 else -1, who=EDITOR,
                     why_not="no registry gives a DOI that fits this reference",
                     needs="the right DOI, from the paper itself")



@rule
def doi_possible(ctx: Context):
    """A DOI a looser search found: offered for the editor to check, never more."""
    from src.refcheck.doi import written_dois

    known = ctx.facts.get("doi_possible")
    if not known:
        return
    written, doi, source, reason = known
    message = f"Possible DOI, check it before accepting: {reason}."
    if written:
        for start, end, given in written_dois(ctx.text):
            if given == written:
                yield _issue(ctx, "REF-DOI-POSSIBLE", WARNING, message, RULE_DOI, start, end,
                             doi, presentation=False, additions=(doi,), removals=(written,),
                             source=source)
        return
    if dois(ctx.text) or re.search(r"\bpresented at\b|\bthis conference\b|\bunpublished\b|"
                                   r"\bprivate communication\b", ctx.text, re.I):
        return
    jacow = JACOW_DOI_RE.fullmatch(doi)
    named = _named_conference(ctx)
    if jacow and named and (named[0].lower() != jacow.group(1).lower()
                            or named[1] != jacow.group(2)[-2:]):
        return                           # another conference's paper: not even possibly
    body = ctx.text.rstrip()
    end = len(body.rstrip("."))
    yield _issue(ctx, "REF-DOI-POSSIBLE", WARNING, message, RULE_DOI, end, len(ctx.text),
                 f". doi:{doi}", presentation=False, additions=(doi,), source=source)
