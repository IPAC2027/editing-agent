r"""Structural operations: changes that move text rather than replace a span.

Reordering ``\bibitem`` entries to match citation order is JACoW's first
reference rule and the sample corpus needs it on nine papers.  It cannot be an
:class:`~src.edits.Edit`, though: an edit owns a character span, and a
permutation of the whole entry list overlaps every narrow edit inside it (a DOI
fix, a unit fix), so the overlap resolver would have to discard one or the
other.  Forcing the choice would mean an editor who rejects a reorder also
loses the DOI fixes inside the references — which is exactly the
all-or-nothing behaviour this rewrite exists to remove.

So a structural operation is a **second stage**, applied after the span edits
and re-derived against the text those edits produced:

    original ──(span edits)──▶ intermediate ──(structural)──▶ final

It stays one decision, stays exactly reversible, and gets its own patch and
commit like everything else.  Re-deriving at apply time is what keeps it safe:
the permutation is recomputed from the entry keys actually present, and refuses
to run if they have changed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from src.models import Paper

_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


class ReorderPlan(BaseModel):
    """A permutation of the reference list, described by entry key."""

    id: str = "R1"
    check_id: str = "REF-NUM-02"
    tier: str = "suggest"
    current_order: list[str] = Field(default_factory=list)
    desired_order: list[str] = Field(default_factory=list)
    moved: int = 0
    message: str = ""
    rule: str = "JACoW: reference numbers follow order of first citation"

    @property
    def needed(self) -> bool:
        return bool(self.desired_order) and self.desired_order != self.current_order

    def summary(self) -> str:
        def _fmt(keys: list[str]) -> str:
            shown = ", ".join(f"[{i}] {k}" for i, k in enumerate(keys[:6], start=1))
            return shown + (f", … (+{len(keys) - 6})" if len(keys) > 6 else "")
        return f"was  {_fmt(self.current_order)}\nnow  {_fmt(self.desired_order)}"


class StructuralPlan(BaseModel):
    """Everything in the structural stage for one paper (currently one thing)."""

    schema_version: int = 1
    file: str = ""
    reorder: ReorderPlan | None = None

    def write(self, path: Path) -> Path:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path) -> "StructuralPlan":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    @property
    def decisions(self) -> list[ReorderPlan]:
        return [self.reorder] if (self.reorder and self.reorder.needed) else []


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def _entry_blocks(source: str) -> tuple[list[tuple[str, int, int]], int, int] | None:
    r"""``([(key, start, end)], region_start, region_end)`` for the entry list."""
    block = re.search(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", source, re.DOTALL
    )
    if not block:
        return None
    block_start, block_end = block.span()
    end_tag = source.rfind(r"\end{thebibliography}", block_start, block_end)
    matches = list(_BIBITEM_RE.finditer(source, block_start, block_end))
    if len(matches) < 2:
        return None
    entries: list[tuple[str, int, int]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else end_tag
        entries.append((match.group(1).strip(), start, end))
    return entries, matches[0].start(), end_tag


def plan_reorder(source: str, paper: Paper) -> ReorderPlan | None:
    r"""Plan a ``\bibitem`` permutation, or return ``None`` if none is needed.

    Only meaningful for ``thebibliography``: with BibLaTeX the numbering is
    derived from citation order already, which is one reason the rule pack
    prefers it.
    """
    parsed = paper.__dict__.get("_pt")
    if not parsed or parsed.bibliography_env != "thebibliography":
        return None

    found = _entry_blocks(source)
    if not found:
        return None
    entries, _region_start, _region_end = found

    current = [key for key, _s, _e in entries]
    known = set(current)
    desired = [key for key in dict.fromkeys(paper.citation_order) if key in known]
    # Entries never cited keep their relative order, at the end.
    desired += [key for key in current if key not in set(desired)]

    if desired == current:
        return None

    moved = sum(1 for old, new in zip(current, desired) if old != new)
    return ReorderPlan(
        current_order=current,
        desired_order=desired,
        moved=moved,
        message=(
            f"Reorder {len(desired)} reference entries so the numbers ascend with "
            f"first citation in the text ({moved} entr"
            f"{'y' if moved == 1 else 'ies'} move). No entry text is changed and no "
            "in-text citation needs touching — LaTeX renumbers automatically."
        ),
    )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class StructuralConflict(RuntimeError):
    """Raised when the reference list no longer matches the plan."""


def apply_reorder(source: str, plan: ReorderPlan) -> str:
    """Apply *plan* to *source*, re-deriving the block boundaries.

    Verifies that the set of entry keys is unchanged before moving anything, so
    a source that gained or lost a reference since the plan was made produces a
    clear conflict rather than a silently wrong reference list.
    """
    found = _entry_blocks(source)
    if not found:
        raise StructuralConflict("no \\thebibliography entry list found")
    entries, region_start, region_end = found

    present = [key for key, _s, _e in entries]
    if set(present) != set(plan.desired_order):
        missing = sorted(set(plan.desired_order) - set(present))
        extra = sorted(set(present) - set(plan.desired_order))
        raise StructuralConflict(
            "the reference list has changed since the plan was made"
            + (f"; missing {', '.join(missing)}" if missing else "")
            + (f"; unexpected {', '.join(extra)}" if extra else "")
        )

    blocks = {key: source[start:end] for key, start, end in entries}
    reordered = "".join(blocks[key] for key in plan.desired_order)
    return source[:region_start] + reordered + source[region_end:]


def diff_reorder(source: str, plan: ReorderPlan, filename: str) -> str:
    """Unified diff of the reorder alone."""
    import difflib

    after = apply_reorder(source, plan)
    return "".join(difflib.unified_diff(
        source.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))


def load_decision(decisions: dict[str, str], plan: ReorderPlan) -> bool:
    """True when the editor accepted *plan*."""
    return decisions.get(plan.id) == "accepted"


def read_decisions(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "decisions" in raw:
        raw = raw["decisions"]
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
