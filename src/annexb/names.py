"""Author lists: read in whatever form the author wrote them, written as Appendix B's Table 2.

Forms read: "A. T. Alpha", "A.T. Alpha", "Alpha, A. T.", "Alpha A.T.", "Alpha AT"
(Vancouver), "Andrew T. Alpha", "J.-P. Gamma", "S. van der Meer", "the CMS
Collaboration"; separated by commas, semicolons, "and" or "&"; ending in
"et al.", "et. al", "et al" or "and others".
"""

from __future__ import annotations

import re

from src.annexb.model import Name

_PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "le", "la",
              "dos", "das", "ter", "ten", "zu", "af", "al", "el", "bin", "ibn", "st.", "mac"}
_GROUP = re.compile(r"\b(?:collaboration|consortium|group|team|committee|project|"
                    r"organi[sz]ation|association|society|institute|laboratory|lab|"
                    r"council|foundation|university|agency|office|department|inc\.?|"
                    r"ltd\.?|corporation|company|gmbh)\b", re.I)
_ET_AL = re.compile(r"[\s,;]*(?:\bet\.?\s*al\b\.?|\band\s+others\b|\bet\s+al\.?)\s*[,.;]*\s*$",
                    re.I)
_INITIAL = r"(?:[A-ZÀ-ÖØ-ÞĀ-Ž][a-z]?\.|[A-ZÀ-ÖØ-ÞĀ-Ž](?=[\s.\-]|$))"
_INITIALS = rf"{_INITIAL}(?:\s*-?\s*{_INITIAL})*"
_UPPER = "A-ZÀ-ÖØ-ÞĀ-Ž"
_WORD = rf"[{_UPPER}][\w'’À-ɏ\-]*"


def split_et_al(segment: str) -> tuple[str, bool]:
    m = _ET_AL.search(segment)
    if m and m.start() > 0:
        return segment[:m.start()], True
    return segment, False


def _initials(given: str) -> str:
    """'Andrew Thomas' -> 'A. T.'; 'A.T.' -> 'A. T.'; 'Jean-Pierre' -> 'J.-P.'; 'AT' -> 'A. T.'."""
    given = given.strip().strip(",")
    if not given:
        return ""
    if re.fullmatch(r"[A-Z]{1,3}", given):                 # Vancouver "AT"
        return " ".join(f"{c}." for c in given)
    out = []
    for word in re.split(r"\s+|(?<=\.)(?=[A-Z])", given):
        if not word:
            continue
        parts = word.split("-")
        pieces = []
        for part in parts:
            part = part.strip(".")
            if not part:
                continue
            if re.fullmatch(r"(?:Ch|Th|Ph|Kh|Sh|Zh|Yu|Ya|Ts)", part):
                pieces.append(part + ".")                  # "Th. Demma", "Ch. Steier"
            else:
                pieces.append(part[0].upper() + ".")
        if pieces:
            out.append("-".join(pieces))
    return " ".join(out)


def _family(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" ,.;")).strip()


def parse_name(token: str) -> Name | None:
    """One author as written -> :class:`Name`, or None when it does not look like a name."""
    t = re.sub(r"\s+", " ", token.strip(" ,;")).strip()
    t = re.sub(r"^(?:and|&)\s+", "", t, flags=re.I)
    if not t:
        return None
    if _GROUP.search(t) and not re.match(rf"{_INITIALS}\s+{_WORD}$", t):
        return Name(literal=re.sub(r"^the\s+", "", t, flags=re.I).rstrip("."))
    # "A. T. Alpha", "A.T. Alpha", "J.-P. Gamma", "Th. Demma", "S. van der Meer"
    m = re.fullmatch(rf"({_INITIALS})\.?\s*((?:(?:{'|'.join(_PARTICLES)})\s+)*{_WORD}"
                     rf"(?:\s+{_WORD})*?)(?:,?\s+(Jr\.|Sr\.|II|III|IV))?", t, re.I)
    if m and re.match(r"[A-Z]", t):
        return Name(given=_initials(m.group(1)), family=_family(m.group(2)),
                    suffix=m.group(3) or "")
    # "MJ Hogan": initials without full stops, before the family name
    m = re.fullmatch(rf"([A-Z]{{1,2}})\s+({_WORD}(?:[\s\-]{_WORD})*)", t)
    if m and not re.fullmatch(r"[A-Z]{2,}", m.group(2)):
        return Name(given=_initials(m.group(1)), family=_family(m.group(2)))
    # "Alpha, A. T." / "Alpha A.T." / "Alpha AT" / "van der Meer, S."
    m = re.fullmatch(rf"((?:(?:{'|'.join(_PARTICLES)})\s+)*{_WORD}(?:[\s\-]{_WORD})*?),?\s+"
                     rf"({_INITIALS}\.?|[A-Z]{{1,3}})", t, re.I)
    if m and re.search(r"[A-Z]", m.group(2)) and not re.fullmatch(r"[A-Z][a-z]+", m.group(2)):
        return Name(given=_initials(m.group(2)), family=_family(m.group(1)))
    # "Andrew T. Alpha", "Jean-Pierre Gamma", "Berk Geveci"
    words = t.split()
    if 2 <= len(words) <= 5 and all(re.match(rf"[{_UPPER}]|(?:{'|'.join(_PARTICLES)})$", w, re.I)
                                    for w in words):
        family_start = len(words) - 1
        while family_start > 1 and words[family_start - 1].lower() in _PARTICLES:
            family_start -= 1
        given, family = words[:family_start], words[family_start:]
        if any(len(g) > 1 and g.isupper() for g in given):
            return None
        if all(re.fullmatch(rf"{_WORD}|{_INITIAL}\.?|[A-Z]\.(?:-[A-Z]\.)?", g) for g in given):
            return Name(given=_initials(" ".join(given)), family=" ".join(family))
    # "Alpha" alone (a surname with no initials): kept as written
    if re.fullmatch(_WORD, t):
        return Name(family=t)
    return None


def _inverted_pairs(tokens: list[str]) -> list[str] | None:
    """["Zampetakis", "M.", "Antoniou", "F."] -> ["Zampetakis, M.", "Antoniou, F."]."""
    if len(tokens) < 2 or len(tokens) % 2:
        return None
    pairs = []
    for family, given in zip(tokens[::2], tokens[1::2]):
        if not re.fullmatch(rf"(?:(?:{'|'.join(_PARTICLES)})\s+)*{_WORD}(?:[\s\-]{_WORD})*",
                            family.strip(), re.I):
            return None
        if not re.fullmatch(rf"\s*{_INITIALS}\.?\s*|\s*[A-Z][a-z]+(?:\s+{_INITIAL}\.?)*\s*",
                            given):
            return None
        pairs.append(f"{family.strip()}, {given.strip()}")
    return pairs


def parse_authors(segment: str) -> tuple[list[Name], bool, bool]:
    """(names, et al., every piece read as a name) for the author part of a reference."""
    seg = segment.strip().strip(",;:").strip()
    seg = re.sub(r"\bet\.\s*al\b\.?", "et al.", seg)
    seg, et_al = split_et_al(seg)
    seg = re.sub(r"\s*&\s*", " and ", seg)
    seg = re.sub(r"\s+and\s+", ", ", seg)
    seg = seg.strip(" ,;.") + ("." if re.search(rf"\b{_INITIAL}$", seg.strip(" ,;")) else "")
    if not seg:
        return [], et_al, False
    tokens = [t for t in re.split(r"\s*[,;]\s*", seg) if t.strip()]
    for i in range(len(tokens) - 1, 0, -1):                # "T. M. Beta, Jr."
        if re.fullmatch(r"(?:Jr|Sr)\.?|II|III|IV", tokens[i].strip()):
            tokens[i - 1] = f"{tokens[i - 1]} {tokens[i].strip()}"
            del tokens[i]
    pairs = _inverted_pairs(tokens)
    if pairs:
        tokens = [p.replace(", ", " ", 1) for p in pairs]
        names = [Name(given=_initials(p.split(", ", 1)[1]), family=p.split(", ", 1)[0])
                 for p in pairs]
        return names, et_al, True
    names: list[Name] = []
    ok = True
    for token in tokens:
        name = parse_name(token)
        if name is None:
            ok = False
            continue
        names.append(name)
    # "Ahrens, James, Berk Geveci, and Charles Law": the first author family name first.
    if len(names) >= 3 and not names[0].given and not names[1].given and \
            names[0].family and re.fullmatch(r"[A-Z][a-z]+(?:-[A-Z]?[a-z]+)?", names[1].family) and \
            all(n.given or n.literal for n in names[2:]):
        names[:2] = [Name(given=_initials(names[1].family), family=names[0].family)]
    return names, et_al, ok and bool(names)


def same_people(a: list[Name], b: list[Name]) -> bool:
    """The same authors, compared by family name (accents and case ignored)."""
    if len(a) != len(b):
        return False
    return all(x.key() == y.key() or x.key() in y.key() or y.key() in x.key()
               for x, y in zip(a, b))


def from_record(family: str, given: str) -> Name:
    """An author from a registry record: family name as given, initials from the given names."""
    return Name(given=_initials(given), family=family.strip())


__all__ = ["parse_authors", "parse_name", "split_et_al", "same_people", "from_record"]
