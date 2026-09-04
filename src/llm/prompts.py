"""Prompt templates for LLM-assisted suggestions.

Each function returns a (system_prompt, user_prompt) tuple ready for
``src.llm.client.chat()``.

Suggestions produced here are written to ``llm_suggestions.md`` and are
never applied automatically to the source.
"""

from __future__ import annotations

from src.knowledge import agent_context
from src.models import Reference


SYSTEM_EDITOR = (
    "You are an expert editor for JACoW/IPAC accelerator-physics conference "
    "proceedings. You know the JACoW MS Word Style Guide Annex B reference rules "
    "thoroughly. Be precise and concise. Output only what is asked."
)


# ---------------------------------------------------------------------------
# Removed on purpose
#
# `doi_lookup_prompt` asked a model to guess a DOI from metadata.
# `missing_metadata_prompt` asked it to supply missing years, volumes and page
# ranges.  Both are exactly the fields an editor cannot verify at a glance,
# which makes a plausible wrong value worse than a blank one.  DOIs and
# bibliographic facts now come from Crossref, DataCite or refs.jacow.org and
# are verified before they are shown; see src/llm/classify.py for what a model
# is allowed to be asked instead.
#
# `sentence_case_prompt` and `journal_abbreviation_prompt` are likewise gone:
# sentence case is decided per word by classify.classify_title_words (with
# abstention), and ISO-4 abbreviation is a table lookup against the LTWA list,
# which either answers or reports NOT CHECKED.
# ---------------------------------------------------------------------------


def latex_source_review_prompt(source: str) -> tuple[str, str]:
    """Ask the model to review the complete LaTeX source without editing it."""
    rules = agent_context(categories=("template", "units", "references"), applies_to="latex")
    user = (
        "Review this complete JACoW LaTeX source. Check title case, author-name "
        "format, number--unit spacing and unit case, and any source-level issues "
        "that require an editor's judgement. Do not rewrite the source or invent "
        "missing information. Return Markdown with one bullet per issue, including "
        "the source line when it can be determined, the exact text, why it is a "
        "problem, and a suggested correction. If there are no issues, reply PASS.\n\n"
        "Use this versioned rule-pack context as the authoritative policy:\n\n"
        f"{rules}\n\n"
        "```latex\n"
        f"{source}\n"
        "```"
    )
    return SYSTEM_EDITOR, user


def reference_review_prompt(ref: Reference) -> tuple[str, str]:
    """Ask the model to review one reference in addition to deterministic rules."""
    rules = agent_context(categories=("references",), applies_to="latex")
    user = (
        "Review this single JACoW reference against Annex B conventions. Check "
        "author formatting, title case, venue and proceedings/journal formatting, "
        "dates, pages, DOI presentation, and suspicious or missing metadata. Do not "
        "invent a DOI or bibliographic fact. Return Markdown with one bullet per "
        "issue, followed by a suggested entry only when the evidence supports it. "
        "Reply PASS when it needs no change.\n\n"
        "Use this versioned rule-pack context as the authoritative policy:\n\n"
        f"{rules}\n\n"
        f"Reference number: {ref.n}\n"
        f"Citation key: {ref.key}\n"
        f"Detected type: {ref.ref_type}\n"
        f"Raw entry:\n{ref.raw_text or '(metadata-only entry)'}"
    )
    return SYSTEM_EDITOR, user
