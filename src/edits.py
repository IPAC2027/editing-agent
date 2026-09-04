"""Span-anchored edit records — the unit of everything the agent proposes.

Design rules (see ``docs/editor_workflow.md``):

* **One edit is one addressable object.**  An edit is a byte-exact replacement of
  ``original[start:end]`` with :attr:`Edit.after`.  It is never "a line that
  changed" and never a prose description of a change.
* **An edit that changes nothing cannot exist.**  :class:`Edit` rejects
  ``before == after`` at construction time.  This is what makes the phantom
  "auto-fixed" reports of earlier versions structurally impossible.
* **Every edit is verified before it is applied.**  :meth:`EditSet.apply`
  re-checks that ``before`` still sits at ``[start:end]`` in the text it is given
  and refuses the whole application if not.
* **Every edit carries its tier.**  The tier decides whether an editor ever sees
  it, and it is assigned per check by policy, not per fix by the fix itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Tier(str, Enum):
    """How much editor attention an edit is allowed to consume."""

    AUTO = "auto"
    """Mechanically reversible, zero judgement, no external fact required.

    Applied without asking.  Recorded in the diff and the footer of the report,
    but never presented as a decision.
    """

    SUGGEST = "suggest"
    """Needs an editor's eye, but comes with a concrete before/after.

    Presented as exactly one accept/reject decision.
    """

    FLAG = "flag"
    """Something is wrong but the agent will not propose a replacement.

    Used whenever a fix would require a fact the agent could not verify.  A
    flag has no ``after`` text and is carried as a :class:`~src.models.Finding`,
    not an :class:`Edit`.
    """


class Confidence(str, Enum):
    """How sure the generator is, independent of tier."""

    CERTAIN = "certain"      # deterministic rule, no ambiguity
    LIKELY = "likely"        # deterministic rule with known edge cases
    UNCERTAIN = "uncertain"  # model-assisted or heuristic; never AUTO


class Evidence(BaseModel):
    """Why the agent believes an edit is correct."""

    source: str
    """``local-rule``, ``crossref``, ``doi.org``, ``jacow-refdb``, ``ltwa``, ``llm``."""

    checked: bool = True
    """False when the source could not be reached.  An unchecked external source
    disqualifies an edit from :attr:`Tier.AUTO` and :attr:`Tier.SUGGEST`."""

    detail: str = ""

    @property
    def is_external(self) -> bool:
        return self.source not in ("local-rule", "template")


class Edit(BaseModel):
    """One byte-exact, individually reversible replacement."""

    id: str = ""
    check_id: str
    tier: Tier
    confidence: Confidence = Confidence.CERTAIN
    file: str
    start: int
    end: int
    before: str
    after: str
    message: str
    rule: str | None = None
    evidence: Evidence = Field(default_factory=lambda: Evidence(source="local-rule"))
    line: int | None = None
    context_before: str = ""
    context_after: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Edit":
        if self.end < self.start:
            raise ValueError(f"{self.check_id}: end {self.end} precedes start {self.start}")
        if len(self.before) != self.end - self.start:
            raise ValueError(
                f"{self.check_id}: before is {len(self.before)} chars but span is "
                f"{self.end - self.start}"
            )
        if self.before == self.after:
            raise ValueError(
                f"{self.check_id}: no-op edit at {self.start} — an edit that changes "
                "nothing must not be created (report it as a Finding or not at all)"
            )
        if self.tier is Tier.AUTO and self.evidence.is_external and not self.evidence.checked:
            raise ValueError(
                f"{self.check_id}: tier AUTO requires verified evidence, but "
                f"{self.evidence.source} was not reached"
            )
        if self.tier is Tier.AUTO and self.confidence is Confidence.UNCERTAIN:
            raise ValueError(f"{self.check_id}: uncertain edits may not be tier AUTO")
        return self

    # ------------------------------------------------------------------
    @property
    def reversible(self) -> bool:
        """True when applying and then un-applying restores the input exactly.

        Always true for a span replacement; kept explicit because the report
        promises it and a future non-span edit type must not silently inherit
        the claim.
        """
        return True

    @property
    def anchor(self) -> str:
        """Fingerprint used to re-locate this edit if the file moved underneath it."""
        payload = f"{self.context_before}\x00{self.before}\x00{self.context_after}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def short(self, width: int = 60) -> str:
        def t(s: str) -> str:
            s = s.replace("\n", "\\n")
            return s if len(s) <= width else s[: width - 1] + "…"
        return f"{t(self.before)} → {t(self.after)}"


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------

# Lower number wins when two edits target overlapping spans.  Ordering is by
# how much the fix is trusted, not by how interesting it is.
_PRIORITY: dict[str, int] = {
    "DOI-FMT-02": 10,   # \url{doi:…} → \doi{…}: most specific DOI rewrite
    "DOI-FMT-01": 20,   # doi: prefix normalisation
    "URL-AS-DOI-01": 30,
    "FMT-UNIT-01": 40,
    "FMT-UNIT-02": 40,
    "CITE-BRACKET-01": 50,
    "CITE-SPACE-01": 60,
    "AUTH-02": 70,
    "FMT-REF-01": 90,   # whole-reference rewrite: always yields to anything narrower
}
_DEFAULT_PRIORITY = 80


def _priority(edit: Edit) -> int:
    return _PRIORITY.get(edit.check_id, _DEFAULT_PRIORITY)


class EditSet(BaseModel):
    """An ordered, non-overlapping, verified set of edits against one source."""

    file: str
    source_sha256: str
    edits: list[Edit] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def build(cls, source: str, file: str, candidates: list[Edit]) -> tuple["EditSet", list[Edit]]:
        """Verify, de-duplicate and de-overlap *candidates* against *source*.

        Returns ``(editset, dropped)``.  An edit is dropped when its ``before``
        does not actually sit at its span (a generator bug) or when a
        higher-priority edit already claims overlapping text.
        """
        dropped: list[Edit] = []
        verified: list[Edit] = []
        for edit in candidates:
            if source[edit.start:edit.end] != edit.before:
                dropped.append(edit)
                continue
            verified.append(edit)

        # Exact duplicates (same span, same result) collapse to one.
        seen: dict[tuple[int, int, str], Edit] = {}
        for edit in verified:
            key = (edit.start, edit.end, edit.after)
            if key in seen:
                continue
            seen[key] = edit
        verified = list(seen.values())

        # Resolve overlaps: sort by (priority, start) and keep the first claim
        # on any character range.
        verified.sort(key=lambda e: (_priority(e), e.start, e.end))
        claimed: list[tuple[int, int]] = []
        kept: list[Edit] = []
        for edit in verified:
            if any(edit.start < c_end and c_start < edit.end for c_start, c_end in claimed):
                dropped.append(edit)
                continue
            # A zero-width insertion is allowed to sit at a boundary but not
            # inside another edit's span.
            claimed.append((edit.start, max(edit.end, edit.start + 1)))
            kept.append(edit)

        kept.sort(key=lambda e: (e.start, e.end))
        for index, edit in enumerate(kept, start=1):
            edit.id = f"E{index:03d}"
            edit.line = source.count("\n", 0, edit.start) + 1
            edit.context_before = source[max(0, edit.start - 40):edit.start]
            edit.context_after = source[edit.end:edit.end + 40]

        return cls(
            file=file,
            source_sha256=sha256(source),
            edits=kept,
        ), dropped

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def by_tier(self, *tiers: Tier) -> list[Edit]:
        return [e for e in self.edits if e.tier in tiers]

    def get(self, edit_id: str) -> Edit | None:
        for edit in self.edits:
            if edit.id == edit_id:
                return edit
        return None

    @property
    def auto(self) -> list[Edit]:
        return self.by_tier(Tier.AUTO)

    @property
    def suggested(self) -> list[Edit]:
        return self.by_tier(Tier.SUGGEST)

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    def apply(self, source: str, edit_ids: list[str] | None = None) -> str:
        """Return *source* with the named edits applied (all AUTO+SUGGEST if None).

        Applies in reverse offset order so earlier offsets stay valid, and
        verifies every ``before`` before touching anything.  Raises
        :class:`EditConflict` if the source has drifted.
        """
        if edit_ids is None:
            selected = self.auto + self.suggested
        else:
            wanted = set(edit_ids)
            selected = [e for e in self.edits if e.id in wanted]
            missing = wanted - {e.id for e in selected}
            if missing:
                raise KeyError(f"unknown edit id(s): {', '.join(sorted(missing))}")

        stale = [e for e in selected if source[e.start:e.end] != e.before]
        if stale:
            raise EditConflict(
                "the source has changed since these edits were computed: "
                + ", ".join(f"{e.id} ({e.check_id}) at line {e.line}" for e in stale)
            )

        result = source
        for edit in sorted(selected, key=lambda e: e.start, reverse=True):
            result = result[:edit.start] + edit.after + result[edit.end:]
        return result

    def unified_diff(self, source: str, edit_ids: list[str] | None = None) -> str:
        import difflib

        modified = self.apply(source, edit_ids)
        return "".join(difflib.unified_diff(
            source.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{self.file}",
            tofile=f"b/{self.file}",
        ))

    def per_edit_patches(self, source: str) -> dict[str, str]:
        """One standalone unified diff per edit, each applicable on its own."""
        return {edit.id: self.unified_diff(source, [edit.id]) for edit in self.edits}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def write(self, path: Path) -> Path:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path) -> "EditSet":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


class EditConflict(RuntimeError):
    """Raised when the source no longer matches what an edit was computed against."""


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Decision files
# ---------------------------------------------------------------------------

class Decisions(BaseModel):
    """An editor's accept/reject choices, as written by ``review.html``."""

    paper_id: str = ""
    source_sha256: str = ""
    decisions: dict[str, str] = Field(default_factory=dict)

    def accepted(self, editset: EditSet) -> list[str]:
        """AUTO edits plus every SUGGEST edit explicitly accepted."""
        ids = [e.id for e in editset.auto]
        ids += [
            e.id for e in editset.suggested
            if self.decisions.get(e.id) == "accepted"
        ]
        return ids

    @classmethod
    def read(cls, path: Path) -> "Decisions":
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Tolerate the shape the browser panel downloads.
        if "decisions" not in raw and isinstance(raw, dict):
            raw = {"decisions": raw}
        return cls.model_validate(raw)


# ---------------------------------------------------------------------------
# Helpers for edit generators
# ---------------------------------------------------------------------------

def make_edit(
    source: str,
    match: re.Match,
    after: str,
    *,
    check_id: str,
    tier: Tier,
    message: str,
    group: int = 0,
    rule: str | None = None,
    evidence: Evidence | None = None,
    confidence: Confidence = Confidence.CERTAIN,
    file: str = "",
) -> Edit | None:
    """Build an :class:`Edit` from a regex match, or ``None`` if it is a no-op.

    This is the only sanctioned way for a check to propose a source change: the
    span comes from the match, so it is correct by construction, and a
    replacement identical to the matched text returns ``None`` instead of
    becoming a phantom fix.
    """
    start, end = match.span(group)
    before = source[start:end]
    if before == after:
        return None
    return Edit(
        check_id=check_id,
        tier=tier,
        confidence=confidence,
        file=file,
        start=start,
        end=end,
        before=before,
        after=after,
        message=message,
        rule=rule,
        evidence=evidence or Evidence(source="local-rule"),
    )
