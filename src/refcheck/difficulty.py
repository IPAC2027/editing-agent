"""What is still wrong with a reference after the rules, and why they could not fix it.

The description is written twice from the same facts: briefly for the editor
(on the reference's card), and in full for the local model, which is given
only the problems it may fix (layout and judgement, with every fact already
in the reference or verified by a lookup), the JACoW layout and Annex B's own
example for that kind of reference, and the verified facts it may use.
Problems that need a fact nobody has, or a decision only the author can make,
are for the editor and are never sent to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.refcheck.model import EDITOR, ERROR, INFO, MODEL, Issue

# Annex B, by kind of reference: what it is, its layout, Annex B's own example.
LAYOUTS: dict[str, tuple[str, str, str]] = {
    "conference_published": (
        "a paper in published conference proceedings",
        "Authors, “Title”, in Proc. CONF'YY, City, [State,] Country, Mon. Year, pp. X-Y. "
        "doi:10.18429/JACoW-CONFYYYY-PAPERID",
        "A. Alpha and B. T. Beta, “An overview of modern control systems”, in Proc. "
        "ICALEPCS'23, Cape Town, South Africa, Oct. 2023, pp. 57-59. "
        "doi:10.18429/JACoW-ICALEPCS2023-PAPERID"),
    "conference_unpublished": (
        "a talk at a past conference, not published",
        "Authors, “Title”, presented at CONF'YY, City, Country, Mon. Year, paper ID, "
        "unpublished.",
        "A. Alpha, “An interesting talk but paper not submitted”, presented at IPAC'14, "
        "Dresden, Germany, Jun. 2014, paper MOP057, unpublished."),
    "conference_current": (
        "a paper at this conference",
        "Authors, “Title”, presented at CONF'YY, City, Country, Mon. Year, paper ID, "
        "this conference.",
        "A. Alpha and B. T. Beta, “Title of talk presented at this conference”, presented "
        "at IPAC'25, Taipei, Taiwan, Jun. 2025, paper MOAB01, this conference."),
    "journal": (
        "a journal article",
        "Authors, “Title”, Journal (ISO 4 abbreviation), vol. V, no. N, p. P (or pp. X-Y), "
        "Mon. Year. doi:10.xxxx/…",
        "A. Alpha et al., “Title of paper published in journal”, Phys. Rev. Lett., vol. 114, "
        "no. 5, p. 050511, Feb. 2014. doi:10.1103/PhysRevLett.114.050511"),
    "journal_accepted": (
        "a journal article accepted for publication",
        "Authors, “Title”, Journal, to be published.",
        "J. B. Good, “Title of paper accepted for publication”, Phys. Rev. Lett., to be "
        "published."),
    "journal_submitted": (
        "an article submitted for publication",
        "Authors, “Title”, submitted for publication.",
        "G. D. Read, “Title of paper”, submitted for publication."),
    "arxiv": (
        "an arXiv preprint",
        "Authors, “Title”, Mon. Year, arXiv:ID [category]. doi:10.48550/arXiv.ID",
        "A. Alpha, “Title of arXiv preprint”, Jan. 2025, arXiv:2501.10602 [physics.acc-ph]. "
        "doi:10.48550/arXiv.2501.10602"),
    "web": ("a web page", "Name, URL (no full stop after it)",
            "EPICS, https://www.epics-controls.org"),
    "book": ("a book",
             "Authors, Title of Book, edition. City, [State,] Country: Publisher, Year.",
             "A. Alpha, Title of Book. Cambridge, MA, USA: MIT Press, 1986."),
    "book_chapter": (
        "a chapter in a book",
        "Authors, “Chapter title”, in Title of Book, Editor, Ed. City, Country: Publisher, "
        "Year, pp. X-Y.",
        "A. Alpha and B. Beta, “Title of chapter in the book”, in Title of Book, R. Mars, "
        "Ed. New York, NY, USA: Wiley, 1994, pp. 42-48."),
    "report": (
        "a report",
        "Authors, “Title”, Institution, City, Country, Rep. NUMBER, Mon. Year.",
        "A. Alpha et al., “Title of report”, CERN, Geneva, Switzerland, Rep. CERN-2012-333, "
        "Oct. 2012."),
    "thesis": (
        "a thesis",
        "Author, “Title”, Ph.D. thesis, Dept., University, City, Country, Year.",
        "A. Student, “Title of thesis”, Ph.D. thesis, Phys. Dept., Karlsruher Institut fuer "
        "Technologie, Karlsruhe, Germany, 2014."),
    "unpublished": ("an unpublished paper", "Authors, “Title”, unpublished.",
                    "P. Neptune, “Title of paper”, unpublished."),
    "private_comm": ("a private communication", "Author, private communication, Mon. Year.",
                     "P. Uranus, private communication, Jun. 2015."),
    "patent": ("a patent", "Inventor, “Title of patent”, Patent Authority and No., Mon. Day, "
               "Year.", "A. N. Inventor, “Title of patent”, Patent Authority and No., Jan. "
               "20, 2016."),
}


def kind_of(text: str, formatter_type: str = "") -> str:
    """What kind of reference *text* is, as Annex B sorts them.

    The text's own markers decide first; the formatter's guess (which can be
    wrong: it once took a conference paper for a journal article) only when
    the text says nothing.
    """
    t = text
    if re.search(r"\bprivate communication\b", t, re.I):
        return "private_comm"
    if re.search(r"\bthis conference\b", t, re.I):
        return "conference_current"
    if re.search(r"\bpresented at\b", t, re.I):
        return "conference_unpublished"
    if re.search(r"\bProc(?:eedings\b|\.)", t):
        return "conference_published"
    if re.search(r"\b(?:Ph\.\s?D\.|PhD|M\.\s?Sc?\.|Master'?s|Diploma)\s+thesis\b|\bthesis\b", t, re.I):
        return "thesis"
    if re.search(r"\bto be published\b|\baccepted\b", t, re.I):
        return "journal_accepted"
    if re.search(r"\bsubmitted\b", t, re.I) and not re.search(r"\bvol\.", t):
        return "journal_submitted"
    if re.search(r"\bunpublished\b", t, re.I):
        return "unpublished"
    if re.search(r"\b(?:Rep\.|Report|Tech\.\s+Note|Preprint)\b", t) and not re.search(r"\bvol\.", t):
        return "report"
    # "J. Appl. Phys." is a journal; "J. D. Jackson" is a person.
    if re.search(r"\bvol\.|\bPhys\.\s+Rev\b|\bNucl\.\s+Instrum\b|\bJ\.\s+[A-Z][a-z]+\.|"
                 r"\bJournal\b|\b\d+\(\d+\):", t):
        return "journal"
    if re.search(r"\barXiv:", t) or "10.48550/arXiv" in t:
        return "arxiv"
    if formatter_type in LAYOUTS:
        return formatter_type
    if re.match(r"[^“\"]*https?://\S+\s*$", t):
        return "web"
    return formatter_type or ""


@dataclass
class Difficulty:
    label: str
    text: str
    kind: str
    model_issues: list[Issue] = field(default_factory=list)
    editor_issues: list[Issue] = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    refused: list[tuple[Issue, str]] = field(default_factory=list)

    @property
    def level(self) -> str:
        """low: layout only; medium: needs judgement; high: needs a fact or a decision."""
        if self.editor_issues:
            return "high"
        judgement = {"REF-TITLE-CAPS", "REF-TITLE-CASE", "REF-TITLE-MISSING", "REF-AUTH-FORM",
                     "REF-PROC-NAME", "REF-LATEX", "REF-DOI-LAST"}
        return "medium" if any(i.code in judgement for i in self.model_issues) else "low"

    @property
    def layout(self) -> tuple[str, str, str]:
        return LAYOUTS.get(self.kind, ("a reference", "", ""))

    def verified_facts(self) -> list[tuple[str, str, str]]:
        return [(name, value, source) for name, (value, source) in sorted(self.facts.items())
                if source and value]

    # -- for the editor ----------------------------------------------------------
    def for_editor(self) -> str:
        lines = []
        for issue in self.editor_issues:
            line = f"• {issue.message}"
            if issue.needs:
                line += f" Needs: {issue.needs}."
            lines.append(line)
        for issue in self.model_issues:
            line = f"• {issue.message}"
            if issue.why_not:
                line += f" (Not fixed automatically: {issue.why_not}.)"
            lines.append(line)
        return "\n".join(lines)

    # -- for the local model -----------------------------------------------------
    def for_model(self, feedback: str = "") -> str:
        name, layout, example = self.layout
        lines = [f"Reference ({name}):", self.text, "", "Problems to fix:"]
        for n, issue in enumerate(self.model_issues, start=1):
            where = f' — in: "{issue.excerpt}"' if issue.excerpt and \
                issue.excerpt != self.text else ""
            lines.append(f"{n}. {issue.message}{where}")
            if issue.why_not:
                lines.append(f"   (The rules could not do it because {issue.why_not}.)")
        for issue, reason in self.refused:
            lines.append(f"- An automatic fix was refused: {issue.message} It {reason}.")
        facts = self.verified_facts()
        if facts:
            lines += ["", "Verified facts you may use (from lookups):"]
            lines += [f"- {name}: {value} ({source})" for name, value, source in facts]
        if layout:
            lines += ["", f"JACoW layout for {name}: {layout}", f"Annex B example: {example}"]
        lines += ["", "Change only what the problems ask for. Keep every author, word, "
                  "number and DOI of the reference unless a problem says to remove it. "
                  "Put the title in curly quotes “…” with the comma after the closing quote. "
                  "Write a DOI last, as doi:10.…, after a full stop."]
        if feedback:
            lines += ["", "Your previous answer was not accepted:", feedback,
                      "Correct those points."]
        return "\n".join(lines)

    def view(self) -> dict:
        return {"label": self.label, "text": self.text, "kind": self.kind,
                "kind_name": self.layout[0], "level": self.level,
                "for_model": [i.view() for i in self.model_issues],
                "for_editor": [i.view() for i in self.editor_issues],
                "facts": {k: {"value": v, "source": s} for k, (v, s) in self.facts.items()}}


def describe(text: str, issues: list[Issue], *, kind: str = "", facts: dict | None = None,
             label: str = "", refused: list[tuple[Issue, str]] | None = None
             ) -> Difficulty | None:
    """The difficulty description for what the rules left, or None if nothing is."""
    left = [i for i in issues if i.severity != INFO]
    if not left:
        return None
    model = [i for i in left if (i.fix is not None) or i.who == MODEL]
    editor = [i for i in left if i.fix is None and i.who == EDITOR]
    return Difficulty(label=label, text=text, kind=kind, model_issues=model,
                      editor_issues=editor, facts=dict(facts or {}),
                      refused=[(i, r) for i, r in (refused or []) if i.severity != INFO])


__all__ = ["Difficulty", "describe", "kind_of", "LAYOUTS", "ERROR"]
