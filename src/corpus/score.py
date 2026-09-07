"""Score the agent's proposals against what the editors actually did.

Step three. For every pair in the corpus the agent screens the author's
revision, and each edit it proposes is looked for in the editors' real diff.

The arithmetic is easy; the honesty is not, so three things are named
explicitly rather than buried in a ratio.

**"Unconfirmed" is not "wrong."** A proposal the editors did not make may be a
false positive — or a correction they missed, or one they made in a later
revision this corpus does not contain, or a judgement call they declined. The
column is called *unconfirmed* throughout and never *false positive*, because
the difference cannot be settled by this program and pretending otherwise would
be the most damaging thing measurement could do here.

**Confirmed is strong evidence, unconfirmed is weak evidence.** So a check with
a high confirmation rate over a decent sample has earned something; a check with
a low one has earned a look from a human, not an automatic demotion.

**The sample is per check, not per conference.** A LaTeX-only check sees only
the LaTeX papers. Every rate is reported with its denominator attached.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.corpus.diff import Hunk, PaperDiff, diff_paper
from src.corpus.index import PaperEntry
from src.corpus.zones import (
    reading,
    zone_of_check,
    zone_of_hunk,
)

#: A proposal whose ``before`` is shorter than this matches too much to trust.
_MIN_ANCHOR = 2


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _loose(text: str) -> str:
    r"""Normalised further, so a difference of spacing convention is not a
    difference of opinion.

    ``X. Du`` and ``X.~Du`` are the same decision about a name; ``10~MeV`` and
    ``10\,MeV`` are the same decision about a unit. Counting those as
    disagreements would have hidden the actual finding, which is that the agent
    and the editors agree on the correction and differ on which non-breaking
    space to use.
    """
    return re.sub(r"\s+", " ", _norm(text).replace("~", " ")
                  .replace("\\,", " ").replace("\\ ", " ")).strip()


@dataclass
class Proposal:
    """One edit the agent would make."""

    paper: str
    check_id: str
    tier: str
    before: str
    after: str


@dataclass
class Judged:
    """A proposal, and whether the editors did the same thing."""

    proposal: Proposal
    how: str = ""          # exact | inside-hunk | covers-hunk | contradicted | ""
    hunk: int | None = None
    editors_did: str = ""  # what the editors put there instead, when they disagreed

    @property
    def confirmed(self) -> bool:
        return bool(self.how) and self.how != "contradicted"

    @property
    def contradicted(self) -> bool:
        """The editors touched exactly this text and did something else with it.

        Far stronger evidence against a rule than mere absence: absence usually
        means the editors did not get to it, but a contradiction means they
        looked at that span and disagreed.
        """
        return self.how == "contradicted"


@dataclass
class PaperScore:
    paper: str
    source: str
    judged: list[Judged] = field(default_factory=list)
    hunks: list[Hunk] = field(default_factory=list)
    explained: set[int] = field(default_factory=set)
    error: str = ""

    @property
    def confirmed(self) -> int:
        return sum(1 for j in self.judged if j.confirmed)

    @property
    def contradicted(self) -> int:
        return sum(1 for j in self.judged if j.contradicted)

    @property
    def unconfirmed(self) -> int:
        return len(self.judged) - self.confirmed - self.contradicted

    @property
    def missed(self) -> list[Hunk]:
        return [h for i, h in enumerate(self.hunks) if i not in self.explained
                and not h.large]


@dataclass
class CheckScore:
    """One check's record against real editorial behaviour."""

    check_id: str
    tier: str = ""
    proposals: int = 0
    confirmed: int = 0
    contradicted: int = 0
    papers: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.confirmed / self.proposals if self.proposals else 0.0

    @property
    def zone(self) -> str:
        return zone_of_check(self.check_id)

    @property
    def verdict(self) -> str:
        """What the evidence supports, read against the zone it comes from.

        A check is never promoted or demoted by this program; it can only earn
        or lose the argument a human then makes. Absence of confirmation is weak
        evidence, contradiction is strong — and in running text even the weak
        evidence is worth almost nothing, because the editors disagree with each
        other there. See :mod:`~src.corpus.zones`.
        """
        if self.contradicted:
            return f"{self.contradicted} contradicted — read them"
        return reading(self.zone, self.rate, self.proposals)


# ---------------------------------------------------------------------------
# Getting the agent's proposals for one paper
# ---------------------------------------------------------------------------

def propose(entry: PaperEntry) -> tuple[list[Proposal], str]:
    """Run the agent on the author's revision. Returns ``(proposals, error)``."""
    folder = entry.original.folder.parent      # the folder holding Source_Files
    try:
        if entry.kind == "latex":
            from src.workflow.prescreen import prescreen

            paper = prescreen(folder, compile=False, git=False)
            editset = paper.__dict__.get("editset")
            edits = list(editset.edits) if editset else []
            return [Proposal(paper=entry.code, check_id=e.check_id,
                             tier=e.tier.value, before=e.before, after=e.after)
                    for e in edits], ""
        if entry.kind == "word":
            from src.workflow.word_prescreen import prescreen_word

            result = prescreen_word(folder)
            return [Proposal(paper=entry.code,
                             check_id=c.get("check_id", "?"),
                             tier=c.get("tier", "suggest"),
                             before=c.get("shown_before") or c.get("before", ""),
                             after=c.get("shown_after") or c.get("after", ""))
                    for c in (result.corrections or [])], ""
        return [], f"no screener for {entry.kind}"
    except Exception as exc:  # noqa: BLE001 — one bad paper must not stop the run
        return [], f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def match(proposal: Proposal, hunks: list[Hunk]) -> Judged:
    """Did the editors make this change?

    Three ways of agreeing, in decreasing strength. Exact is the same edit.
    *inside-hunk* is the agent's small edit sitting within a larger editorial
    rewrite — common when an editor retyped a whole reference that happened to
    contain the DOI the agent would have fixed. *covers-hunk* is the reverse,
    which is how the Word side matches at all: its corrections are whole
    paragraphs while the diff is word-level.
    """
    if (len(_norm(proposal.before)) < _MIN_ANCHOR
            and len(_norm(proposal.after)) < _MIN_ANCHOR):
        return Judged(proposal=proposal)

    # Strict first, then again ignoring which flavour of non-breaking space
    # each side chose. A hit on the second pass is agreement, not disagreement.
    for normalise, label in ((_norm, ""), (_loose, "near ")):
        before, after = normalise(proposal.before), normalise(proposal.after)
        for index, hunk in enumerate(hunks):
            if before == normalise(hunk.before) and after == normalise(hunk.after):
                return Judged(proposal=proposal, how=f"{label}exact", hunk=index)
        for index, hunk in enumerate(hunks):
            h_before, h_after = normalise(hunk.before), normalise(hunk.after)
            if before and after and before in h_before and after in h_after:
                return Judged(proposal=proposal, how=f"{label}inside-hunk", hunk=index)
            if h_before and h_after and h_before in before and h_after in after:
                return Judged(proposal=proposal, how=f"{label}covers-hunk", hunk=index)

    # Nothing agreed. Did the editors change this very text into something else?
    #
    # The guard matters more than it looks. Without it a three-word proposal
    # matches inside any large rewritten block and the report fills with
    # "contradictions" that are nothing of the kind — an edit the editors never
    # considered, sitting inside a paragraph they happened to retype.
    before = _norm(proposal.before)
    for index, hunk in enumerate(hunks):
        if hunk.large:
            continue
        h_before = _norm(hunk.before)
        if not h_before:
            continue
        if h_before == before or (before in h_before
                                  and len(h_before) <= 2 * len(before) + 8):
            return Judged(proposal=proposal, how="contradicted", hunk=index,
                          editors_did=_norm(hunk.after)[:120])
    return Judged(proposal=proposal)


def score_paper(entry: PaperEntry, diff: PaperDiff | None = None) -> PaperScore:
    """Screen one paper and compare the result with what the editors did."""
    diff = diff or diff_paper(entry)
    result = PaperScore(paper=entry.code, source=entry.kind, hunks=diff.hunks)
    proposals, error = propose(entry)
    if error:
        result.error = error
        return result
    for proposal in proposals:
        judged = match(proposal, diff.hunks)
        result.judged.append(judged)
        if judged.hunk is not None:
            result.explained.add(judged.hunk)
    return result


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def by_check(scores: list[PaperScore]) -> list[CheckScore]:
    table: dict[str, CheckScore] = {}
    for score in scores:
        for judged in score.judged:
            entry = table.setdefault(judged.proposal.check_id,
                                     CheckScore(check_id=judged.proposal.check_id))
            entry.tier = judged.proposal.tier or entry.tier
            entry.proposals += 1
            entry.confirmed += int(judged.confirmed)
            entry.contradicted += int(judged.contradicted)
            entry.papers.add(score.paper)
            if judged.contradicted and len(entry.examples) < 3:
                entry.examples.append(
                    f"{score.paper}: {_norm(judged.proposal.before)[:34]} -> "
                    f"we say {_norm(judged.proposal.after)[:28]}, "
                    f"editors put {judged.editors_did[:34]}")
    return sorted(table.values(), key=lambda c: (-c.proposals, c.check_id))


def missed_signatures(scores: list[PaperScore], *, top: int = 30) -> list[tuple[str, int]]:
    """The corrections editors make that nothing proposed — the mining list."""
    counter = Counter(h.signature for s in scores for h in s.missed)
    return counter.most_common(top)


def totals(scores: list[PaperScore]) -> dict[str, int]:
    small = [h for s in scores for h in s.hunks if not h.large]
    explained = sum(len([i for i in s.explained
                         if i < len(s.hunks) and not s.hunks[i].large])
                    for s in scores)
    return {
        "papers scored": len([s for s in scores if not s.error]),
        "papers that failed to screen": len([s for s in scores if s.error]),
        "proposals": sum(len(s.judged) for s in scores),
        "confirmed by the editors": sum(s.confirmed for s in scores),
        "contradicted by the editors": sum(s.contradicted for s in scores),
        "unconfirmed (not evidence of error)": sum(s.unconfirmed for s in scores),
        "editorial corrections": len(small),
        "of those, explained": explained,
    }

# ---------------------------------------------------------------------------
# The two cuts that make a rate mean something
# ---------------------------------------------------------------------------

@dataclass
class ZoneScore:
    """Confirmation within one part of the paper."""

    zone: str
    proposals: int = 0
    confirmed: int = 0
    contradicted: int = 0
    corrections: int = 0        # what the editors did here, whether we saw it
    explained: int = 0

    @property
    def rate(self) -> float:
        return self.confirmed / self.proposals if self.proposals else 0.0

    @property
    def recall(self) -> float:
        return self.explained / self.corrections if self.corrections else 0.0


def by_zone(scores: list[PaperScore]) -> list[ZoneScore]:
    """Split every number by where in the paper it happened.

    Without this cut the headline rate is an average over zones with completely
    different meanings, and it flatters the strict zones while condemning the
    loose ones.
    """
    from src.corpus.zones import ZONES

    table = {zone: ZoneScore(zone=zone) for zone in ZONES}
    for score in scores:
        for judged in score.judged:
            entry = table[zone_of_check(judged.proposal.check_id)]
            entry.proposals += 1
            entry.confirmed += int(judged.confirmed)
            entry.contradicted += int(judged.contradicted)
        for index, hunk in enumerate(score.hunks):
            if hunk.large:
                continue
            entry = table[zone_of_hunk(hunk)]
            entry.corrections += 1
            entry.explained += int(index in score.explained)
    return [z for z in table.values() if z.proposals or z.corrections]


@dataclass
class EditorScore:
    """One editor's habits, so 'editors vary' can be a number."""

    editor: str
    papers: int = 0
    corrections: int = 0
    by_zone: Counter = field(default_factory=Counter)

    @property
    def per_paper(self) -> float:
        return self.corrections / self.papers if self.papers else 0.0

    def share(self, zone: str) -> float:
        return self.by_zone[zone] / self.corrections if self.corrections else 0.0


def by_editor(entries, diffs) -> list[EditorScore]:
    """How much each editor changed, and where they spent it.

    The claim this measures is that strictness varies by person, most of all in
    running text. If two editors correct the same zone at very different rates,
    no single confirmation threshold can be right for that zone.
    """
    table: dict[str, EditorScore] = {}
    for entry, diff in zip(entries, diffs):
        name = entry.editor or "(unassigned)"
        record = table.setdefault(name, EditorScore(editor=name))
        record.papers += 1
        for hunk in diff.hunks:
            if hunk.large:
                continue
            record.corrections += 1
            record.by_zone[zone_of_hunk(hunk)] += 1
    return sorted(table.values(), key=lambda e: -e.papers)
