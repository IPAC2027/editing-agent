"""The local model fixes what the rules could not; the rules then check its answer.

Given a :class:`~src.refcheck.difficulty.Difficulty`, the model is asked to fix
only the problems meant for it. Its answer is accepted only if

1. the damage check (``check_rewrite``) finds nothing lost or invented against
   the reference it was given — only what the problems allow may change
   (a title's capitals; a conference's long name; verified facts added); and
2. the rules, run again on the answer, find none of those problems left and
   no new one.

A refused answer is sent back once with the reasons; a second refusal leaves
the reference to the editor, with the description.

A title's capitals are a special case: the model is never asked to rewrite the
title. ``src.llm.classify.resolve_title_casing`` asks it only to label the
words the deterministic sentence case could not decide, keeps a label only
when three samples agree, and rebuilds the title in code; a word still in
doubt leaves the title for the editor.

After the model answers, the rules run again over the answer and fix what
they can (a title in quotes lets them see the journal's name, for instance),
and the damage check is told about those fixes too. The model is a local one
by default (``LLM_BASE_URL``, Ollama), named by ``REFERENCE_FIX_MODEL`` or
``LLM_MODEL``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from src.refcheck.difficulty import Difficulty
from src.refcheck.fixer import errors, fix, lint
from src.refcheck.model import split

SYSTEM = (
    "You correct one reference from the reference list of a JACoW conference paper "
    "(accelerator physics), following JACoW Annex B exactly. Change only what the list "
    "of problems asks for. Never invent or guess an author, title, journal, volume, page, "
    "year, DOI or any other fact: use only what is in the reference or in the verified "
    "facts given. Reply with the corrected reference alone, on one line, without a "
    "number in front and without any explanation."
)

#: Long-name words a JACoW conference's full name is made of ("12th Int. Particle
#: Acc. Conf."), which may go when it is replaced by "in Proc. IPAC'21".
_VENUE_WORDS = re.compile(r"\b(?:\d+(?:st|nd|rd|th)|Int|International|Conf|Conference|"
                          r"Particle|Accelerator|Acc|Accel|on|of|the|Proceedings|Proc|"
                          r"Workshop|Symposium|Symp|Annual|IEEE)\b\.?", re.I)


TITLE_CODES = frozenset({"REF-TITLE-CAPS", "REF-TITLE-CASE"})


@dataclass
class Repair:
    text: str
    model: str
    attempts: int
    fixed: list[str] = field(default_factory=list)
    left: list = field(default_factory=list)
    # What the damage check must be told, against the rules' text, to accept it.
    declared: dict = field(default_factory=lambda: {
        "allowed_substitutions": [], "allowed_additions": [], "allowed_removals": []})
    how: list[str] = field(default_factory=list)     # "title capitals", "free-form"


def _merge(*declarations: dict) -> dict:
    keys = ("allowed_substitutions", "allowed_additions", "allowed_removals")
    return {k: [v for d in declarations for v in d.get(k, [])] for k in keys}


def model_name() -> str:
    return (os.getenv("REFERENCE_FIX_MODEL") or os.getenv("LLM_MODEL") or "qwen3:14b").strip()


def available() -> bool:
    from src.llm import client
    return client.is_enabled()


def clean(answer: str) -> str:
    """The reference out of a model's reply (thinking, fences, labels and all)."""
    text = re.sub(r"<think>.*?</think>", "", answer or "", flags=re.S | re.I)
    text = text.replace("```text", "```").strip()
    if "```" in text:
        inside = re.findall(r"```(.*?)```", text, re.S)
        text = inside[0] if inside else text.replace("```", "")
    label = re.compile(r"(?i)^(?:the\s+)?(?:corrected reference|answer|here is[^:]*)\s*:?\s*")
    lines = [label.sub("", ln.strip()) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    text = lines[0] if lines else ""
    text = re.sub(r"^\[\d+\]\s*", "", text).strip()
    if len(text) > 2 and text[0] == text[-1] == "'" :
        text = text[1:-1]
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def allowances(before: str, answer: str, d: Difficulty
               ) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """What the problems given to the model allow it to change: (substitutions,
    additions, removals) for the damage check."""
    targeted = {i.code for i in d.model_issues}
    substitutions: list[tuple[str, str]] = []
    removals: list[str] = []
    if targeted & {"REF-TITLE-CAPS", "REF-TITLE-CASE"}:
        was, now = split(before), split(answer)
        old_title, new_title = was.get(was.title), now.get(now.title)
        if old_title and new_title and _words(old_title) == _words(new_title):
            substitutions.append((old_title, new_title))
    if "REF-PROC-NAME" in targeted:
        removals += [m.group(0) for m in _VENUE_WORDS.finditer(before)]
    if "REF-LATEX" in targeted:
        removals += re.findall(r"\\([A-Za-z]+)", before)
    if "REF-ARXIV-PREPRINT" in targeted:
        removals.append("preprint")
    additions = [value for _, value, _ in d.verified_facts()]
    return substitutions, additions, removals


def verify(before: str, answer: str, d: Difficulty, extra: dict | None = None) -> list[str]:
    """Why *answer* cannot replace *before*; empty when it can.

    *extra*: what the rules changed after the model, declared for the damage check.
    """
    from src.references import check_rewrite, proper_noun_risk

    problems: list[str] = []
    if not answer or len(answer) > 2 * len(before) + 120:
        return ["the answer was not a single corrected reference"]
    targeted = {i.code for i in d.model_issues}
    substitutions, additions, removals = allowances(before, answer, d)
    extra = extra or {}
    verdict = check_rewrite(
        before, answer,
        allowed_substitutions=substitutions + extra.get("allowed_substitutions", []),
        allowed_additions=additions + extra.get("allowed_additions", []),
        allowed_removals=removals + extra.get("allowed_removals", []))
    if not verdict.ok:
        problems.append(f"It {verdict.reason}; nothing may be lost or invented.")
    if not targeted & TITLE_CODES:
        risky = [w for w in proper_noun_risk(before, answer) if w]
        if risky:
            problems.append("It lowercased words that may be names: " + ", ".join(risky[:5])
                            + "; leave their capitals as they were.")
    before_codes = {i.code for i in errors(lint(before, kind=d.kind, facts=d.facts))}
    for issue in errors(lint(answer, kind=d.kind, facts=d.facts)):
        if issue.code in targeted:
            problems.append(f"Still wrong: {issue.message}"
                            + (f' (in "{issue.excerpt}")' if issue.excerpt else ""))
        elif issue.code not in before_codes:
            problems.append(f"New problem: {issue.message}"
                            + (f' (in "{issue.excerpt}")' if issue.excerpt else ""))
    return problems


Chat = Callable[..., str]


def recase_title(text: str) -> tuple[str | None, tuple[str, ...]]:
    """The reference with its title in sentence case, decided word by word.

    ``(None, words in doubt)`` when the model could not settle every word.
    """
    from src.llm.classify import resolve_title_casing

    parts = split(text)
    title = parts.get(parts.title)
    if not title:
        return None, ()
    casing = resolve_title_casing(title)
    if casing.unsure or not casing.changed or casing.text == title:
        return None, tuple(casing.unsure)
    return text[:parts.title[0]] + casing.text + text[parts.title[1]:], ()


def repair(d: Difficulty, *, model: str | None = None, attempts: int = 2,
           chat: Chat | None = None, timeout: float | None = None,
           recase=recase_title) -> Repair | None:
    """Ask the model to fix *d*'s problems; return its answer only if it checks out."""
    from dataclasses import replace

    if not d.model_issues:
        return None
    name = model or model_name()
    text = d.text
    declared = _merge()
    how: list[str] = []
    titles = [i for i in d.model_issues if i.code in TITLE_CODES]
    others = [i for i in d.model_issues if i.code not in TITLE_CODES]
    attempt = 0
    if titles:
        try:
            recased, _ = recase(text)
        except Exception:  # noqa: BLE001 — the title stays for the editor
            recased = None
        if recased:
            old_title, new_title = split(text).get(split(text).title), \
                split(recased).get(split(recased).title)
            declared = _merge(declared, {"allowed_substitutions": [(old_title, new_title)]})
            text = recased
            how.append("title capitals, word by word")
    if others:
        if chat is None:
            from src.llm import client
            chat = client.chat
        wait = timeout if timeout is not None else float(os.getenv("REFERENCE_FIX_TIMEOUT",
                                                                    "120"))
        task = replace(d, text=text, model_issues=others, refused=d.refused)
        feedback = ""
        accepted = None
        for attempt in range(1, attempts + 1):
            try:
                raw = chat(SYSTEM, task.for_model(feedback), model=name,
                           temperature=0.0 if attempt == 1 else 0.3, timeout=wait)
            except Exception:  # noqa: BLE001 — no model: the editor has the description
                break
            answer = clean(raw)
            polished = fix(answer, kind=d.kind, facts=d.facts)
            problems = verify(text, polished.text, task, extra=polished.declared)
            if not problems:
                accepted = polished
                break
            feedback = "\n".join(f"- {p}" for p in problems)
        if accepted is not None:
            subs, adds, rems = allowances(text, accepted.text, task)
            declared = _merge(declared, {"allowed_substitutions": subs,
                                         "allowed_additions": adds,
                                         "allowed_removals": rems}, accepted.declared)
            text = accepted.text
            how.append("free-form, checked by the rules")
    if text == d.text:
        return None
    # The rules once more over the result (a name the title skill lowercased, say).
    polished = fix(text, kind=d.kind, facts=d.facts)
    if polished.changed:
        declared = _merge(declared, polished.declared)
        text = polished.text
    left = errors(lint(text, kind=d.kind, facts=d.facts))
    fixed = sorted({i.code for i in d.model_issues} - {i.code for i in left})
    return Repair(text=text, model=name, attempts=max(attempt, 1), fixed=fixed, left=left,
                  declared=declared, how=how)
