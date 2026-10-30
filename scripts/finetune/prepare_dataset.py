#!/usr/bin/env python3
"""Prepare training data for the JACoW reference model — standalone.

Reads downloaded conferences (author revision and editors' final revision of
each paper), pairs every reference with its edited version, keeps only pairs
that teach information-preserving formatting, removes duplicates, and writes
chat-format JSONL for fine-tuning.

    # The formatter is not on PyPI: install the copy from the local test
    # package (jacow-tools/jacow-reference-formatter), or the v1.0.0 tag once
    # it exists.  An older formatter lacks check_rewrite and will not do.
    pip install ./jacow-tools/jacow-reference-formatter python-docx "bibtexparser<2" pylatexenc
    python prepare_dataset.py CONF-A CONF-B --out data/refs --test-conference CONF-B

    # or, with nothing to install, inside the editing agent's environment:
    cd jacow-tools/editing-agent
    uv run python scripts/finetune/prepare_dataset.py CONF-A CONF-B --out data/refs ...

Input layout — one folder per conference, one folder per paper, as written by
``indico-pull`` (``index.json`` is not required):

    CONF-A/MOPA001/original/Source_Files/…     the author's submission
    CONF-A/MOPA001/current/Source_Files/…      the editors' final version
    CONF-A/MOPA001/*/BibTeX_file_only_for_LaTeX_papers/*.bib   (LaTeX + .bib)

Output (``--out``):
    train.jsonl   examples to train on
    eval.jsonl    held-out papers from the training conferences (checks during training)
    test.jsonl    every example from --test-conference (final test; never trained on)
    rejected.jsonl  pairs left out, with the reason — read it
    summary.json  counts

Reference sources: Word papers (numbered entries after "REFERENCES", with DOI
or URL lines below an entry joined to it); LaTeX ``\\bibitem`` lists; LaTeX
papers citing from ``.bib`` files (paired by key; both sides written in the
same layout, so the pair carries only the editor's field changes).

Style: clear Annex B rules are applied to the editor's version before it is
used ("et al." with a full stop, "and" between two authors, the comma before
"and", spaced initials, "doi:" form, month full stops, “…” quotation marks);
each row records the fixes, and the editor's own text.  With
``--title-case sentence`` titles are sentence-cased too, and a title whose
words cannot all be decided rejects the pair.

Kept: the editor's version passes the damage check (``check_rewrite``) against
the author's — nothing lost or invented, except values a lookup confirms,
which are then included in the prompt — or the reference was already right
(at most ``--unchanged-share`` of the final data).  The prompt is the one the editing agent
uses at inference (``src/finetune/prompt.py``); keep the two identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

# --- The prompt: identical to src/finetune/prompt.py ---------------------------

SYSTEM = """You format one bibliographic reference in the JACoW style (IEEE style as
applied in JACoW Annex B). Rules:
- Authors: initials and surname ("A. T. Alpha"), initials separated by spaces;
  two authors joined by "and"; three to six separated by commas with a comma
  before "and"; more than six as "A. T. Alpha et al.". Keep names the author
  listed before "et al.".
- Title in sentence case inside “ ”, followed by a comma; keep acronyms, units
  (GeV, MHz) and proper names as written.
- Conference papers: "in Proc. IPAC’23, Venice, Italy, May 2023, pp. 57-59."
  Unpublished: "presented at IPAC’14, …, unpublished." Submitted papers:
  "submitted for publication." — never name the journal.
- Journals: ISO 4 abbreviation, then "vol. N, no. N, p./pp. N, Mon. YYYY."
- DOIs at the end as "doi:10.…", never as a URL.
- Never add, remove or change a number, DOI, name or word unless it comes
  from the verified record given with the reference. If the record is absent,
  only reformat what is written.
Answer with the formatted reference only.
/no_think"""


def user_message(raw: str, record: dict | None = None) -> str:
    text = f"Reference:\n{raw.strip()}"
    if record:
        kept = {k: v for k, v in record.items() if v and not str(k).startswith("_")}
        text += "\n\nVerified record (Crossref, DataCite or JACoW):\n" + json.dumps(
            kept, ensure_ascii=False, sort_keys=True)
    return text


def messages(raw: str, record: dict | None, answer: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message(raw, record)},
            {"role": "assistant", "content": answer.strip()}]


# --- Finding the papers ---------------------------------------------------------

SOURCE_DIRS = ("Source_Files", "Supporting_files_for_papers", "BibTeX_file_only_for_LaTeX_papers")


def paper_folders(conference: Path):
    for folder in sorted(p for p in conference.iterdir() if p.is_dir()):
        if (folder / "original").is_dir() and (folder / "current").is_dir():
            yield folder


def main_file(side: Path) -> Path | None:
    files = [f for f in (side / "Source_Files").glob("*")
             if f.suffix.lower() in (".tex", ".docx") and f.is_file()]
    return max(files, key=lambda f: f.stat().st_size) if files else None


# --- Reading references ---------------------------------------------------------

_REF_NUM = re.compile(r"^\s*\[(\d+)\]\s*")
_LINK_LINE = re.compile(r"^(?:https?://|doi:|www\.)", re.IGNORECASE)


def word_references(path: Path) -> dict[str, str]:
    import docx
    refs: dict[str, str] = {}
    current: str | None = None
    in_refs = False
    for paragraph in docx.Document(str(path)).paragraphs:
        text = paragraph.text.replace("\t", " ").strip()
        if re.fullmatch(r"REFERENCES?", text, re.IGNORECASE):
            in_refs = True
            continue
        if not in_refs or not text:
            continue
        m = _REF_NUM.match(text)
        if m:
            current = m.group(1)
            refs[current] = text[m.end():].strip()
        elif current and _LINK_LINE.match(text):
            refs[current] += " " + text          # the entry's DOI or URL on its own line
    return refs


_BIBITEM = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}")
_LATEX_RESIDUE = re.compile(r"\\[A-Za-z]+|\\[^A-Za-z\s]|[{}]")


def latex_to_text(text: str) -> str:
    """LaTeX in a reference to plain Unicode text.

    JACoW's own commands are handled first (\\enquote, \\doi, \\url, quote
    macros, thin spaces); everything else — accents, math, font switches,
    \\textsuperscript — goes through pylatexenc.  What is left is checked by
    the caller: an example with LaTeX still in it is rejected, not learned.
    """
    t = text
    t = re.sub(r"\\enquote\*?\{((?:[^{}]|\{[^{}]*\})*)\}", "\u201c\\1\u201d", t)
    t = re.sub(r"\\doi\{([^}]*)\}", r"doi:\1", t)
    t = re.sub(r"\\url\{([^}]*)\}", r"\1", t)
    # \href{https://doi.org/X}{X} is the DOI; any other link keeps its text.
    t = re.sub(r"\\href\{(?:https?://)?(?:dx\.)?doi\.org/([^}]*)\}\{[^}]*\}", r"doi:\1", t)
    t = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", t)
    for macro, char in (("textquotedblleft", "\u201c"), ("textquotedblright", "\u201d"),
                        ("textquoteleft", "\u2018"), ("textquoteright", "\u2019")):
        t = re.sub(r"\\" + macro + r"(?:\{\}|\s?)", char, t)
    t = t.replace("``", "\u201c").replace("''", "\u201d")
    t = re.sub(r"\\[,;:!]|\\ |(?<!\\)~", " ", t)
    # URLs and DOIs are passed through untouched ('%' and '_' in them are not LaTeX).
    kept: list[str] = []

    def _keep(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"QQKEPT{len(kept) - 1}QQ"

    t = re.sub(r"(?:https?://|doi:)[^\s,;{}]+", _keep, t)
    try:
        from pylatexenc.latex2text import LatexNodes2Text
        t = LatexNodes2Text(math_mode="text", keep_braced_groups=False).latex_to_text(t)
    except ImportError:
        for pattern, replacement in _LATEX_FALLBACK:
            t = pattern.sub(replacement, t)
    except Exception:  # noqa: BLE001 — malformed LaTeX: keep what we have; the residue check decides
        pass
    t = t.replace("---", "\u2014").replace("--", "\u2013")
    t = re.sub(r"QQKEPT(\d+)QQ", lambda m: kept[int(m.group(1))], t)
    return re.sub(r"\s+", " ", t).strip()


_LATEX_FALLBACK = (
    (re.compile(r"\\(?:emph|textit|textbf|textrm|NoCaseChange|textsuperscript)\{([^{}]*)\}"), r"\1"),
    (re.compile(r"\{\\(?:it|em|bf|rm)\s+([^{}]*)\}"), r"\1"),
    (re.compile(r"\\([&%#_$])"), r"\1"),
    (re.compile(r"(?<!\\)[{}]"), ""),
)


def has_latex(text: str) -> bool:
    return bool(_LATEX_RESIDUE.search(text))


def bibitem_references(path: Path) -> dict[str, str]:
    source = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8", errors="replace"))
    end = source.find("\\end{thebibliography}")
    marks = list(_BIBITEM.finditer(source))
    refs = {}
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else (end if end > 0 else len(source))
        refs[m.group(1).strip()] = latex_to_text(source[m.end():stop])
    return refs


_MONTH_ABBR = {"jan": "Jan.", "feb": "Feb.", "mar": "Mar.", "apr": "Apr.", "may": "May",
               "jun": "Jun.", "jul": "Jul.", "aug": "Aug.", "sep": "Sep.", "oct": "Oct.",
               "nov": "Nov.", "dec": "Dec."}


def _month(value: str) -> str:
    v = value.strip().lower().rstrip(".")
    if v.isdigit() and 1 <= int(v) <= 12:
        v = list(_MONTH_ABBR)[int(v) - 1]
    return _MONTH_ABBR.get(v[:3], value.strip())


def _bib_layout(entry: dict) -> str:
    """A .bib entry in the Annex B order for its type, fields exactly as given.

    Both sides of a pair are written with this function, so what differs is
    only what the editor changed in the fields.
    """
    from jacow_formatter import fmt_authors

    def field(name: str) -> str:
        return latex_to_text(str(entry.get(name, "") or ""))

    kind = entry.get("ENTRYTYPE", "").lower()
    parts = []
    # BibTeX names: "Last, First and Last, First and others".
    names = [n.strip() for n in re.split(r"\s+and\s+", field("author")) if n.strip()]
    others = bool(names) and names[-1].lower() == "others"
    names = [n for n in names if n.lower() != "others"]
    names = [" ".join(reversed([p.strip() for p in n.split(",", 1)])) if "," in n else n for n in names]
    if names:
        parts.append(fmt_authors(", ".join(names) + " et al." if others else " and ".join(names)))
    if field("title"):
        parts.append(f"\u201c{field('title')}\u201d")
    date = " ".join(x for x in (_month(field("month")) if field("month") else "", field("year")) if x)
    pages = field("pages").replace("--", "-").replace("\u2013", "-")
    pp = (("pp. " if "-" in pages else "p. ") + pages) if pages else ""
    if kind == "article":
        parts += [field("journal")]
        parts += [f"vol. {field('volume')}" if field("volume") else "",
                  f"no. {field('number')}" if field("number") else "", pp, date]
    elif kind in ("inproceedings", "proceedings", "conference"):
        container = field("booktitle")
        parts.append(f"in {container}" if container and not container.startswith("in ") else container)
        parts += [field("venue") or field("address"), date, pp]
    else:
        parts += [field("booktitle") or field("journal") or field("publisher") or field("institution"),
                  field("venue") or field("address"), date, pp]
    text = ", ".join(p for p in parts if p) + "."
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", field("doi"), flags=re.IGNORECASE)
    if doi:
        text += f" doi:{doi}"
    elif field("url"):
        text += f" {field('url')}"
    return text


def bib_references(side: Path) -> dict[str, str]:
    import bibtexparser
    refs: dict[str, str] = {}
    for directory in SOURCE_DIRS:
        for bib in sorted((side / directory).glob("*.bib")) if (side / directory).is_dir() else []:
            try:
                database = bibtexparser.loads(bib.read_text(encoding="utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                continue
            for entry in database.entries:
                refs.setdefault(entry.get("ID", ""), _bib_layout(entry))
    return refs


def references(side: Path) -> tuple[dict[str, str], str]:
    path = main_file(side)
    if path is None:
        return {}, "no source"
    if path.suffix.lower() == ".docx":
        return word_references(path), "word"
    refs = bibitem_references(path)
    return (refs, "bibitem") if refs else (bib_references(side), "bib")


# --- Filtering ------------------------------------------------------------------

def normal(text: str) -> str:
    text = text.translate(str.maketrans({"\u201c": '"', "\u201d": '"', "\u2019": "'",
                                         "\u2013": "-", "\u00a0": " "}))
    return re.sub(r"\s+", " ", text).strip().lower()


def journal_substitutions(raw: str, final: str, journal: str = "") -> list[tuple[str, str]]:
    """Declare journal-name abbreviations the editor made as allowed.

    Full titles are found anywhere in the reference — "Nuclear Instruments and
    Methods in Physics Research Section A: Accelerators, Spectrometers,
    Detectors and Associated Equipment" contains commas, so splitting on
    commas never saw it — and accepted when their abbreviation is in the
    editor's version.
    """
    from jacow_formatter.journals import normalize_journal
    from jacow_formatter.tables import _JACOW_ABBREVS, _JOURNAL_ALIASES
    pairs: list[tuple[str, str]] = []
    lowered = raw.lower()
    titles = list(_JACOW_ABBREVS.items()) + [
        (alias, _JACOW_ABBREVS.get(full, "")) for alias, full in _JOURNAL_ALIASES.items()]
    for full, abbr in sorted(titles, key=lambda kv: -len(kv[0])):
        if not abbr or abbr not in final:
            continue
        for variant in {full, re.sub(r"\s+section\s+([a-e])\b.*$", r" section \1", full)}:
            at = lowered.find(variant)
            if at >= 0 and variant != abbr.lower():
                end = at + len(variant)
                # the descriptive tail after "Section A:" belongs to the title
                tail = re.match(r":[^,]*(?:,[^,]*){0,4}?(?=,\s*(?:vol\.|\d|[A-Z][a-z]{2}\.?\s+\d{4}))",
                                raw[end:])
                pairs.append((raw[at:end + (tail.end() if tail else 0)], abbr))
                break
        if pairs:
            break
    # "Nucl. Instrum. Methods Phys. Res., Sect. B" -> "… Res. B" (Annex C).
    nim = re.search(r"Nucl\. Instrum\. Methods Phys\. Res\.,?\s+Sect\.\s+([AB])\b", raw)
    if nim and f"Nucl. Instrum. Methods Phys. Res. {nim.group(1)}" in final:
        pairs.append((nim.group(0), f"Nucl. Instrum. Methods Phys. Res. {nim.group(1)}"))
    if journal and journal in final:
        for segment in re.split(r"[,\u201d\"]", raw):
            segment = segment.strip()
            for name in {segment.rstrip("."), re.sub(r"\s+[A-Z]?\d[\w\s()]*$", "", segment).strip()}:
                if name and name.rstrip(".") != journal.rstrip("."):
                    try:
                        if normalize_journal(name) == journal:
                            pairs.append((name, journal))
                            break
                    except Exception:  # noqa: BLE001
                        continue
    return pairs


def lookup_record(result: dict) -> dict:
    record = {k: result["rec"].get(k) for k in result.get("derived_fields") or []}
    record.update({c["field"]: c["value"] for c in result.get("field_log") or []})
    return {k: v for k, v in record.items() if v}


# --- Style check on the editor's version ---------------------------------------
# The damage check guards information, not style: an editor's "et al" without
# the full stop, or two authors without "and", loses nothing and would be
# learned as correct.  Clear Annex B rules are therefore applied to the
# editor's version before it becomes a training target; anything left that a
# rule cannot settle is rejected rather than learned.

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_NAME = r"(?:[A-Z][a-z]?\.\s?-?)+\s?[A-Z][\w'\u2019\-]+(?:\s(?:van|von|de|der|den|la|du|da|di)\s[\w'\u2019\-]+)*"


def _author_part(text: str) -> tuple[str, str]:
    m = re.search(r"[\u201c\u201e\"]", text)
    return (text[:m.start()], text[m.start():]) if m else ("", text)


def style_fix(target: str, title_case: str = "any") -> tuple[str | None, list[str]]:
    """Apply the unambiguous Annex B rules to an editor's reference.

    Returns ``(fixed, notes)``; ``fixed`` is None when a rule is broken in a way
    no rule can repair (the pair is then rejected, with the note as reason).
    """
    notes: list[str] = []
    text = target

    # Quotation marks: German „…“, straight "…", mixed “…" and stray spaces.
    new = re.sub(r"\u201e\s*", "\u201c", text)
    new = re.sub(r'(^|,\s*)"([^"\u201c\u201d]+?)\s*["\u201d](?=\s*,)', "\\1\u201c\\2\u201d", new)
    new = re.sub(r'\u201c([^"\u201c\u201d]+?)\s*"(?=\s*,)', "\u201c\\1\u201d", new)
    new = re.sub(r"\u201c\s*([^\u201c\u201d\u201e]+?)\s*[\u201c\u201d](?=\s*,)",
                 lambda m: "\u201c" + m.group(1).strip() + "\u201d", new)
    if new != text:
        notes.append("quotation marks")
        text = new

    # DOI form.
    new = re.sub(r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\S+)", r"doi:\1", text, flags=re.IGNORECASE)
    new = re.sub(r"\bDOI\s*:\s*(?=10\.)", "doi:", new, flags=re.IGNORECASE)
    if new != text:
        notes.append("doi: form")
        text = new

    authors, rest = _author_part(text)
    if authors:
        fixed = authors
        # "et al" -> "et al."
        fixed = re.sub(r"\bet\.?\s*al\b\.?", "et al.", fixed)
        # Initials separated by spaces: "H.P. Alpha" -> "H. P. Alpha"
        fixed = re.sub(r"(?<![A-Za-z])([A-Z][a-z]?\.)(?=[A-Z][a-z]?\.)", r"\1 ", fixed)
        fixed = re.sub(r"(?<![A-Za-z])([A-Z][a-z]?\.)(?=[A-Z][a-z'\u2019])", r"\1 ", fixed)
        body = fixed.rstrip().rstrip(",").rstrip()
        if "et al." not in body:
            names = [n.strip() for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", body) if n.strip()]
            if len(names) == 2 and " and " not in body and all(re.fullmatch(_NAME, n) for n in names):
                fixed = fixed.replace(body, f"{names[0]} and {names[1]}", 1)
                notes.append("'and' between two authors")
            elif len(names) >= 3 and re.search(r"[^,]\s+and\s+", body) and all(re.fullmatch(_NAME, n) for n in names):
                fixed = fixed.replace(body, re.sub(r"(?<!,)\s+and\s+(?=[^,]*$)", ", and ", body), 1)
                notes.append("comma before 'and'")
        if fixed != authors:
            if "et al." in fixed and "et al." not in authors:
                notes.append("'et al.' punctuation")
            if re.search(r"[A-Z]\.[A-Z]", authors) and not re.search(r"[A-Z]\.[A-Z]", fixed):
                notes.append("initials spacing")
            text = fixed + rest

    # Annex C: "Nucl. Instrum. Methods Phys. Res. A", not "…, Sect. A".
    new = re.sub(r"(Nucl\. Instrum\. Methods Phys\. Res\.),?\s+Sect\.\s+([AB])\b", r"\1 \2", text)
    if new != text:
        notes.append("journal abbreviation")
        text = new

    # Month abbreviations take a full stop (May has none).
    new = re.sub(r"\b(" + "|".join(_MONTHS) + r")(?=\s+(?:19|20)\d{2}\b)", r"\1.", text)
    new = re.sub(r"\bSept\.", "Sep.", new)
    if new != text:
        notes.append("month abbreviation")
        text = new

    # Title case: a team decision (--title-case).  "sentence": sentence-case
    # the title when every word can be decided; otherwise reject the pair.
    if title_case == "sentence":
        from jacow_formatter import sent_case_report
        m = re.search(r"\u201c([^\u201d]+)\u201d", text)
        if m:
            report = sent_case_report(m.group(1))
            if report.unsure:
                return None, notes + [f"title case undecided ({', '.join(report.unsure[:3])})"]
            if report.text != m.group(1):
                text = text[:m.start(1)] + report.text + text[m.end(1):]
                notes.append("sentence case")
    return text, notes


# --- Main -----------------------------------------------------------------------

def _require_formatter() -> None:
    try:
        from jacow_formatter import check_rewrite, fmt_authors, sent_case_report  # noqa: F401
    except ImportError as exc:
        sys.exit(
            f"The JACoW reference formatter is not available ({exc}).\n"
            "It is not on PyPI. Install the copy from the local test package:\n"
            "    pip install ./jacow-tools/jacow-reference-formatter\n"
            "or run this script inside the editing agent's environment:\n"
            "    cd jacow-tools/editing-agent && uv run python scripts/finetune/prepare_dataset.py ...\n"
            "(An older formatter without check_rewrite is not enough.)")
    try:
        import docx  # noqa: F401
        import bibtexparser  # noqa: F401
        import pylatexenc  # noqa: F401
    except ImportError as exc:
        sys.exit(f"Missing package ({exc}): pip install python-docx \"bibtexparser<2\" pylatexenc")


# --- Pairing ----------------------------------------------------------------------

_SURNAME = re.compile(r"^\s*(?:(?:[A-Z][a-z]?\.\s?-?)+\s?)?([A-Z][\w'\u2019\-]+)")


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _surname(text: str) -> str:
    m = _SURNAME.match(text)
    return m.group(1).lower() if m else ""


def pair_references(old: dict[str, str], new: dict[str, str]) -> tuple[list[tuple[str, str, str]], int]:
    """Pair author and editor references by content, not only by number.

    Editors renumber, insert and remove references; pairing [n] with [n]
    matched unrelated papers (the template's "A. Alpha and B. T. Beta…" with
    an unrelated article).  Same label is used when it is the same
    reference; otherwise the most similar unused editor reference with the
    same first author, if similar enough.  Returns (label, raw, final) and how
    many were re-paired.
    """
    def same(a: str, b: str, *, same_label: bool = False) -> bool:
        sa, sb = _surname(a), _surname(b)
        if sa and sb and sa != sb:
            return False
        # Under the same number, a shared first author and some shared words
        # suffice — an editor may change a lot; across numbers be stricter.
        threshold = 0.25 if (same_label and sa and sb) else 0.45
        return similarity(a, b) >= threshold

    pairs, used, repaired = [], set(), 0
    pending = []
    for label, raw in old.items():
        if label in new and same(raw, new[label], same_label=True):
            pairs.append((label, raw, new[label]))
            used.add(label)
        else:
            pending.append((label, raw))
    for label, raw in pending:
        best = max(((similarity(raw, text), key) for key, text in new.items()
                    if key not in used and same(raw, text)), default=(0, None))
        if best[1] is not None:
            pairs.append((label, raw, new[best[1]]))
            used.add(best[1])
            repaired += 1
    return pairs, repaired


# --- Run --------------------------------------------------------------------------

_URL = re.compile(r"https?://\S+")


def run(conferences: list[Path], out_dir: Path, *, test_conference: Path | None = None,
        eval_share: float = 0.10, unchanged_share: float = 0.15, lookups: bool = True,
        mailto: str = "", title_case: str = "any", seed: int = 7) -> dict:
    """Build the dataset; returns the summary (also written to summary.json)."""
    from jacow_formatter import AgentConfig, JacowAgent, check_rewrite

    agent = JacowAgent(AgentConfig(
        mailto=mailto, use_crossref=lookups, use_datacite=lookups, use_inspirehep=lookups,
        use_jacow_remote=lookups, use_refdb=lookups, use_ltwa=False, use_llm=False,
        cache_path=out_dir / "lookup-cache.sqlite"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    files = {name: (out_dir / f"{name}.jsonl").open("w", encoding="utf-8")
             for name in ("train", "eval", "test", "rejected")}
    counts = {k: 0 for k in ("papers", "papers_without_pairs", "pairs", "re_paired", "duplicates",
                             "latex_left", "style_fixed", "rejected", "corrections",
                             "unchanged_available", "unchanged_kept", "train", "eval", "test")}
    sources: dict[str, int] = {}
    style_notes: dict[str, int] = {}
    seen: set[str] = set()
    unchanged: list[tuple[str, dict]] = []
    test_root = test_conference.resolve() if test_conference else None
    roots = list(conferences) + ([test_conference] if test_conference and test_conference not in conferences else [])

    def split_for(conference: Path, paper: str) -> str:
        if test_root is not None and conference.resolve() == test_root:
            return "test"
        bucket = int(hashlib.sha256(paper.encode()).hexdigest(), 16) % 1000
        return "eval" if bucket < eval_share * 1000 else "train"

    def reject(row: dict, reason: str) -> None:
        row["reason"] = reason
        files["rejected"].write(json.dumps(row, ensure_ascii=False) + "\n")
        counts["rejected"] += 1

    try:
        for conference in roots:
            for paper in paper_folders(conference):
                counts["papers"] += 1
                try:
                    old, kind = references(paper / "original")
                    new, _ = references(paper / "current")
                except Exception as exc:  # noqa: BLE001
                    print(f"skipped {paper.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
                pairs, repaired = pair_references(old, new)
                counts["re_paired"] += repaired
                if not pairs:
                    counts["papers_without_pairs"] += 1
                    continue
                sources[kind] = sources.get(kind, 0) + 1
                for label, raw, editor in pairs:
                    counts["pairs"] += 1
                    base = {"conference": conference.name, "paper": paper.name,
                            "label": label, "source": kind}
                    if has_latex(raw) or has_latex(editor):
                        counts["latex_left"] += 1
                        reject({**base, "messages": messages(raw, None, editor)},
                               "LaTeX left after conversion")
                        continue
                    final, notes = style_fix(editor, title_case)
                    for note in notes:
                        style_notes[note] = style_notes.get(note, 0) + 1
                    if final is None:
                        reject({**base, "messages": messages(raw, None, editor)}, "style: " + notes[-1])
                        continue
                    counts["style_fixed"] += bool(notes)
                    fingerprint = hashlib.sha256((normal(raw) + "\0" + normal(final)).encode()).hexdigest()
                    if fingerprint in seen:
                        counts["duplicates"] += 1
                        continue
                    seen.add(fingerprint)
                    row = {**base, "style_fixes": notes,
                           "editor_original": editor if notes else None}
                    if raw == final:
                        counts["unchanged_available"] += 1
                        unchanged.append((split_for(conference, paper.name),
                                          {**row, "reason": "unchanged",
                                           "messages": messages(raw, None, final)}))
                        continue
                    result = agent.process_record(raw)
                    record = lookup_record(result) if lookups else {}
                    removable = []
                    if record.get("doi") and record["doi"].lower() in final.lower():
                        # A publisher URL replaced by the DOI the lookup confirms.
                        removable = [u for u in _URL.findall(raw) if u not in final]
                    verdict = check_rewrite(
                        raw, final, allowed_additions=[str(v) for v in record.values()],
                        allowed_removals=removable,
                        allowed_substitutions=journal_substitutions(
                            raw, final, str((result.get("rec") or {}).get("journal") or "")))
                    row["messages"] = messages(raw, record or None, final)
                    if not verdict.ok:
                        reject(row, "editor changed information: " + "; ".join(verdict.problems)[:200])
                        continue
                    row["reason"] = "formatting"
                    split = split_for(conference, paper.name)
                    files[split].write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts[split] += 1
                    counts["corrections"] += 1
        # Unchanged references: at most `unchanged_share` of the final data.
        limit = int(counts["corrections"] * unchanged_share / max(1e-9, 1 - unchanged_share))
        rng.shuffle(unchanged)
        for split, row in unchanged[:limit]:
            files[split].write(json.dumps(row, ensure_ascii=False) + "\n")
            counts[split] += 1
            counts["unchanged_kept"] += 1
    finally:
        for handle in files.values():
            handle.close()
    summary = {**counts, "papers_by_reference_source": sources, "style_fixes": style_notes}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main() -> int:
    _require_formatter()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("conferences", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/refs"))
    ap.add_argument("--test-conference", type=Path, default=None,
                    help="kept entirely for the final test (never trained on)")
    ap.add_argument("--eval-share", type=float, default=0.10,
                    help="share of training-conference papers held out for evaluation")
    ap.add_argument("--unchanged-share", type=float, default=0.15,
                    help="largest share of the final data made of already-correct references")
    ap.add_argument("--offline", action="store_true",
                    help="no Crossref/DataCite/JACoW lookups (pairs that add values are rejected)")
    ap.add_argument("--mailto", default="", help="your e-mail, for polite Crossref use")
    ap.add_argument("--title-case", choices=("any", "sentence"), default="any",
                    help="'sentence': editors' titles must be in sentence case (Annex B); "
                         "'any': leave titles as the editors wrote them (until the team decides)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    summary = run(args.conferences, args.out, test_conference=args.test_conference,
                  eval_share=args.eval_share, unchanged_share=args.unchanged_share,
                  lookups=not args.offline, mailto=args.mailto, title_case=args.title_case,
                  seed=args.seed)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
