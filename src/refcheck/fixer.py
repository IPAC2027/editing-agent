"""Run the rules over a reference, and apply the fixes they offer.

Fixes are applied in rounds: the rules are run, every fix that does not touch
another is applied (right to left, so positions stay valid), and the rules are
run again on the result, until nothing more can be fixed. Each fix is checked
against the author's original text by the damage check, told only what that
fix (and the ones before it) may change; a fix it refuses is not applied, and
is reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.refcheck.model import INFO, Context, Issue, split
from src.refcheck.rules import RULES

log = logging.getLogger(__name__)


def lint(text: str, *, kind: str = "", facts: dict | None = None) -> list[Issue]:
    """Every way *text* breaks a JACoW reference rule."""
    from src.house_style import load_house_style

    ctx = Context(text=text, parts=split(text), kind=kind or "", facts=facts or {},
                  style=load_house_style())
    found: list[Issue] = []
    seen: set[tuple] = set()
    for check in RULES:
        try:
            for issue in check(ctx):
                key = (issue.code, issue.start, issue.end)
                if key not in seen:
                    seen.add(key)
                    found.append(issue)
        except Exception:  # noqa: BLE001 — one faulty rule must not stop the others
            log.exception("reference rule %s failed on %r", check.__name__, text[:80])
    return found


def errors(issues: list[Issue]) -> list[Issue]:
    """The issues an editor would act on (not stray spaces)."""
    return [i for i in issues if i.severity != INFO]


@dataclass
class Fixed:
    original: str
    text: str
    applied: list[Issue] = field(default_factory=list)
    remaining: list[Issue] = field(default_factory=list)
    refused: list[tuple[Issue, str]] = field(default_factory=list)
    declared: dict = field(default_factory=lambda: {
        "allowed_substitutions": [], "allowed_additions": [], "allowed_removals": []})

    @property
    def changed(self) -> bool:
        return self.text != self.original

    @property
    def presentation_only(self) -> bool:
        return all(i.fix.presentation for i in self.applied)

    @property
    def sources(self) -> list[str]:
        return sorted({i.fix.source for i in self.applied if i.fix.source})


def _declare(declared: dict, issue: Issue) -> dict:
    fix = issue.fix
    return {
        "allowed_substitutions": declared["allowed_substitutions"] + list(fix.substitutions),
        "allowed_additions": declared["allowed_additions"] + list(fix.additions),
        "allowed_removals": declared["allowed_removals"] + list(fix.removals),
    }


def _separate(issues: list[Issue]) -> list[Issue]:
    """Fixes that neither overlap nor touch, the earlier rule winning."""
    chosen: list[Issue] = []
    for issue in issues:
        f = issue.fix
        if any(not (f.end < c.fix.start or f.start > c.fix.end) for c in chosen):
            continue
        chosen.append(issue)
    return chosen


def fix(text: str, *, kind: str = "", facts: dict | None = None, rounds: int = 8,
        presentation_only: bool = False) -> Fixed:
    """Apply every fix the rules can make; return the result and what is left.

    *presentation_only*: only the fixes safe to apply without asking.
    """
    from src.references import check_rewrite

    result = Fixed(original=text, text=text)
    refused: set[tuple[str, str]] = set()
    for _ in range(rounds):
        issues = lint(result.text, kind=kind, facts=facts)
        fixable = [i for i in issues if i.fix is not None
                   and (i.fix.presentation or not presentation_only)
                   and (i.code, i.excerpt) not in refused]
        chosen = _separate(fixable)
        if not chosen:
            break
        progressed = False
        for issue in sorted(chosen, key=lambda i: i.fix.start, reverse=True):
            f = issue.fix
            candidate = result.text[:f.start] + f.replacement + result.text[f.end:]
            trial = _declare(result.declared, issue)
            verdict = check_rewrite(text, candidate, **trial)
            if verdict.ok:
                result.text, result.declared = candidate, trial
                result.applied.append(issue)
                progressed = True
            else:
                refused.add((issue.code, issue.excerpt))
                result.refused.append((issue, verdict.reason))
        if not progressed:
            break
    result.remaining = lint(result.text, kind=kind, facts=facts)
    return result
