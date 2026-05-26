"""Prompt templates for LLM-assisted suggestions.

Each function returns a (system_prompt, user_prompt) tuple ready for
``src.llm.client.chat()``.

Suggestions produced here are written to ``llm_suggestions.md`` and are
never applied automatically to the source.
"""

from __future__ import annotations

from src.models import Reference


SYSTEM_EDITOR = (
    "You are an expert editor for JACoW/IPAC accelerator-physics conference "
    "proceedings. You know the JACoW MS Word Style Guide Annex B reference rules "
    "thoroughly. Be precise and concise. Output only what is asked."
)


def doi_lookup_prompt(ref: Reference) -> tuple[str, str]:
    """Ask the LLM to suggest a DOI for a reference that lacks one."""
    user = (
        f"The following reference entry is missing a DOI. "
        f"Based on the available metadata, suggest the most likely DOI. "
        f"If you are uncertain, say so.\n\n"
        f"Raw entry: {ref.raw_text}\n\n"
        f"Reply with just the DOI string (e.g. 10.18429/JACoW-IPAC2023-MOPA001) "
        f"or 'UNKNOWN' if you cannot determine it."
    )
    return SYSTEM_EDITOR, user


def sentence_case_prompt(title: str) -> tuple[str, str]:
    """Ask the LLM to convert a reference list paper title to sentence case."""
    user = (
        f"Convert the following paper title to JACoW sentence case "
        f"(capitalise only the first word and proper nouns/acronyms):\n\n"
        f'"{title}"\n\n'
        f"Reply with only the corrected title string."
    )
    return SYSTEM_EDITOR, user


def journal_abbreviation_prompt(journal_name: str) -> tuple[str, str]:
    """Ask the LLM to provide the ISO 4 abbreviation for a journal name."""
    user = (
        f"Provide the ISO 4 abbreviated title for the following journal. "
        f"Use standard abbreviation conventions.\n\n"
        f"Journal: {journal_name}\n\n"
        f"Reply with only the abbreviated title string."
    )
    return SYSTEM_EDITOR, user


def missing_metadata_prompt(ref: Reference, missing_fields: list[str]) -> tuple[str, str]:
    """Ask the LLM to suggest values for missing reference fields."""
    fields = ", ".join(missing_fields)
    user = (
        f"The following reference entry is missing these fields: {fields}.\n\n"
        f"Raw entry: {ref.raw_text}\n\n"
        f"For each missing field, suggest the most likely value based on context. "
        f"Format your reply as a JSON object with the field names as keys. "
        f"Use null for any field you cannot determine."
    )
    return SYSTEM_EDITOR, user
