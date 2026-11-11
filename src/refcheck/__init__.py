"""The JACoW reference checker: find, fix, describe, and have the model fix the rest.

Three stages, each checked by the one before it:

1. **Rules** (:mod:`.rules`, :func:`.fixer.fix`): each JACoW rule finds its own
   errors and fixes those it can fix with no judgement — a DOI's form, "et
   al.", initials, quotes, "in Proc. IPAC'21", month abbreviations, "p." for an
   article number, a journal laid out "Journal, vol. V, p. P, Year", an arXiv
   paper's DOI. Every fix is checked against the author's text by the damage
   check, told exactly what the fix may change.
2. **Difficulty description** (:mod:`.difficulty`): what the rules could not
   fix, why, and who can — the local model (layout and judgement: a title's
   capitals, a title with no quotes, the long name of a conference) or the
   editor (a missing page range, a DOI for another conference, a status only
   the author knows).
3. **AI skill** (:mod:`.skill`): the local model is given the description of
   the problems meant for it, the JACoW layout, Annex B's example and the
   verified facts, and its answer is accepted only if the damage check and the
   rules both pass it.

What is still wrong at the end is described for the editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.refcheck.difficulty import LAYOUTS, Difficulty, describe, kind_of
from src.refcheck.fixer import Fixed, errors, fix, lint
from src.refcheck.model import EDITOR, ERROR, INFO, MODEL, WARNING, Fix, Issue
from src.refcheck.skill import Repair, repair

#: Facts a lookup verified that the model may write into a reference. Not the
#: month or the place: the conference table that supplies them is not always right.
MODEL_FACTS = ("doi", "pages", "volume", "issue", "year")


@dataclass
class Checked:
    original: str
    text: str                              # the best version found
    kind: str
    fixed: Fixed                           # what the rules did
    difficulty: Difficulty | None = None   # what the rules left, as described
    repair: Repair | None = None           # what the model did, if accepted
    left: list[Issue] = field(default_factory=list)   # still wrong at the end
    model_refused: bool = False            # the model was asked, its answers refused

    @property
    def changed(self) -> bool:
        return self.text != self.original

    def final_description(self, label: str = "") -> Difficulty | None:
        return describe(self.text, self.left, kind=self.kind, facts=self.difficulty.facts
                        if self.difficulty else {}, label=label)


def model_facts(facts: dict | None) -> dict:
    return {k: v for k, v in (facts or {}).items() if k in MODEL_FACTS and v and v[1]}


def check_reference(text: str, *, kind: str = "", facts: dict | None = None,
                    label: str = "", llm: bool = False, chat=None,
                    model: str | None = None) -> Checked:
    """Run the three stages on one reference (plain text)."""
    from src.references import check_rewrite

    facts = dict(facts or {})
    kind = kind_of(text, kind)
    ruled = fix(text, kind=kind, facts=facts)
    difficulty = describe(ruled.text, ruled.remaining, kind=kind, facts=model_facts(facts),
                          label=label, refused=ruled.refused)
    result = Checked(original=text, text=ruled.text, kind=kind, fixed=ruled,
                     difficulty=difficulty)
    if llm and difficulty and difficulty.model_issues:
        answer = repair(difficulty, chat=chat, model=model)
        if answer is not None:
            # The answer was checked against the rules' text; check it once more
            # against the author's, with everything both stages declared.
            verdict = check_rewrite(
                text, answer.text,
                allowed_substitutions=ruled.declared["allowed_substitutions"]
                + answer.declared["allowed_substitutions"],
                allowed_additions=ruled.declared["allowed_additions"]
                + answer.declared["allowed_additions"],
                allowed_removals=ruled.declared["allowed_removals"]
                + answer.declared["allowed_removals"])
            if verdict.ok:
                result.repair, result.text = answer, answer.text
            else:
                result.model_refused = True
        else:
            result.model_refused = True
    result.left = errors(lint(result.text, kind=kind, facts=facts))
    return result


__all__ = ["check_reference", "Checked", "Difficulty", "Fixed", "Issue", "Fix", "Repair",
           "describe", "errors", "fix", "kind_of", "lint", "repair", "LAYOUTS", "EDITOR",
           "MODEL", "ERROR", "WARNING", "INFO", "MODEL_FACTS", "model_facts"]
