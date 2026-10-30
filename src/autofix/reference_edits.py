r"""Reference-level edits for ``\bibitem`` bodies and ``.bib`` fields.

Two gaps this closes.

**BibLaTeX submissions used to get nothing.**  Both bibitem passes returned
early unless ``bibliography_env == "thebibliography"``, and the ``.bib`` file was
never rewritten — which in the sample corpus was the majority of submissions.
That is backwards: editing a structured BibTeX field is *safer* than rewriting
LaTeX prose, because the field boundaries are explicit and a change to
``doi = {...}`` cannot spill into the title.  So ``.bib`` field edits come first
here.

**Whole-reference rewrites used to be unguarded.**  A reference was re-parsed
into fields and re-emitted from a template, checked only for a handful of
missing markers.  Every rewrite now goes through
:func:`jacow_formatter.check_rewrite`, and a rewrite that fails is discarded
with the reason recorded as a finding — the editor is told the reference looks
wrong *and* why the agent would not touch it, which is more useful than a
damaged reference.
"""

from __future__ import annotations

import re

from src.edits import Confidence, Edit, Evidence, Tier, make_edit
from src.models import Finding, Paper, Severity
from src.references import check_rewrite, sent_case_report

def _case_report(text: str, *, evidence: set[str] | None = None):
    """Sentence-case *text*, letting a model resolve abstentions if configured.

    With no model this is the deterministic pass and nothing more, which is the
    default: ``LLM_ENABLED`` is off unless the operator turns it on.
    """
    try:
        from src.llm.classify import resolve_title_casing

        return resolve_title_casing(text, evidence=evidence)
    except Exception:  # noqa: BLE001 — a model problem never blocks a run
        return sent_case_report(text, evidence=evidence)


# ---------------------------------------------------------------------------
# .bib field edits
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s}]+)\s*,", re.IGNORECASE)
_FIELD_RE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*"
    r"(?P<open>[{\"])(?P<value>(?:[^{}\"]|\{[^{}]*\})*)(?P<close>[}\"])",
    re.DOTALL,
)

_DOI_IN_VALUE_RE = re.compile(
    r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)(10\.\d{4,9}/.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:-|--|\u2013|\u2014)\s*(\d+)\s*$")

_BIB_RULE = "JACoW Annex B: reference field conventions"


def _entry_spans(source: str) -> list[tuple[int, int]]:
    """Character span of each ``@type{key, ...}`` entry, so field logic can be
    scoped to one reference."""
    starts = [m.start() for m in _ENTRY_RE.finditer(source)]
    spans: list[tuple[int, int]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(source)
        spans.append((start, end))
    return spans


def bib_field_edits(source: str, file: str = "") -> list[Edit]:
    """Edits for a ``.bib`` file, field by field.

    Only presentation is touched, and only inside a recognised field value.  No
    bibliographic fact is invented, changed, or moved between entries.

    This is also where BibLaTeX submissions stop being second-class.  Both
    bibitem passes used to return early unless the paper used
    ``thebibliography``, and the ``.bib`` file was never rewritten — so the
    majority of submissions in the sample corpus received no reference edits at
    all, even though editing a delimited BibTeX field is *safer* than rewriting
    LaTeX prose.
    """
    edits: list[Edit] = []
    entries = _entry_spans(source)

    for field in _FIELD_RE.finditer(source):
        name = field.group("name").lower()
        value = field.group("value")
        value_start = field.start("value")
        value_end = field.end("value")

        # url = {https://doi.org/10.x} → doi = {10.x}
        # JACoW wants the DOI in the doi field so biblatex renders it; a DOI
        # parked in url renders as a bare link and loses the doi: prefix.
        if name == "url":
            match = _DOI_IN_VALUE_RE.match(value)
            if match:
                doi = match.group(1).strip().rstrip(".,;")
                entry_start, entry_end = next(
                    ((a, b) for a, b in entries if a <= field.start() < b),
                    (0, len(source)),
                )
                entry = source[entry_start:entry_end]
                has_doi = re.search(r"\bdoi\s*=\s*[{\"]", entry, re.IGNORECASE)
                whole = source[field.start():field.end()]
                if has_doi:
                    # Both fields carry the same DOI; dropping the duplicate is
                    # a judgement call, so offer it rather than take it.
                    edits.append(Edit(
                        check_id="URL-AS-DOI-01",
                        tier=Tier.SUGGEST,
                        file=file,
                        start=field.start(),
                        end=field.end(),
                        before=whole,
                        after=f"doi = {{{doi}}}",
                        message=(
                            "This entry already has a doi field, and the url field is "
                            "the same DOI as a resolver link. Keeping only the doi "
                            "field is the JACoW convention."
                        ),
                        rule=_BIB_RULE,
                    ))
                else:
                    edits.append(Edit(
                        check_id="URL-AS-DOI-01",
                        tier=Tier.AUTO,
                        file=file,
                        start=field.start(),
                        end=field.end(),
                        before=whole,
                        after=f"doi = {{{doi}}}",
                        message=(
                            "A DOI held in the url field renders as a plain link; moved "
                            "to the doi field so biblatex prints doi:10.xxxx/yyyy."
                        ),
                        rule=_BIB_RULE,
                        evidence=Evidence(
                            source="local-rule",
                            detail="the DOI was taken verbatim from the URL, not looked up",
                        ),
                    ))
            continue

        # doi = {https://doi.org/10.x} → doi = {10.x}
        if name == "doi":
            match = _DOI_IN_VALUE_RE.match(value)
            if match:
                cleaned = match.group(1).strip().rstrip(".,;")
                if cleaned != value.strip():
                    edits.append(Edit(
                        check_id="DOI-FMT-03",
                        tier=Tier.AUTO,
                        file=file,
                        start=value_start,
                        end=value_end,
                        before=value,
                        after=cleaned,
                        message=(
                            "A BibTeX doi field holds the bare DOI, not a resolver URL — "
                            "biblatex builds the link itself."
                        ),
                        rule=_BIB_RULE,
                    ))
            continue

        # pages = {611-632} → en dash, the JACoW/biblatex convention
        if name in ("pages", "page"):
            match = _PAGE_RANGE_RE.match(value)
            if match:
                cleaned = f"{match.group(1)}--{match.group(2)}"
                if cleaned != value.strip():
                    edits.append(Edit(
                        check_id="REF-PAGES-01",
                        tier=Tier.AUTO,
                        file=file,
                        start=value_start,
                        end=value_end,
                        before=value,
                        after=cleaned,
                        message="A BibTeX page range uses '--'.",
                        rule=_BIB_RULE,
                    ))
            continue

        # title = {Level Set Learning For Poincaré Plots} → sentence case, but
        # only when every word could be classified.
        #
        # Deliberately NOT booktitle/journal: those hold a *container* name — a
        # conference or book title — which JACoW keeps in title case.
        # Sentence-casing them turned "Proc. 15th International Particle
        # Accelerator Conference" into lowercase prose.
        if name in ("title", "subtitle"):
            edits.extend(_title_case_edit(
                source, value, value_start, value_end, name, file,
            ))
            continue

    return edits


def _title_case_edit(
    source: str,
    value: str,
    start: int,
    end: int,
    field_name: str,
    file: str,
) -> list[Edit]:
    """Sentence-case a title field, or nothing at all.

    A title containing even one word the caser could not classify is left
    completely alone.  Partial sentence-casing is worse than none: it looks
    deliberate, so an editor is less likely to check it.
    """
    # Protect anything already brace-protected — {LHC}, {GaAs} — and maths.
    if "{" in value or "$" in value or "\\" in value:
        return []
    report = _case_report(value)
    if not report.changed or report.unsure:
        return []
    verdict = check_rewrite(value, report.text, allow_case_change=False)
    # A pure sentence-case pass legitimately changes case, so only the
    # non-case problems disqualify it.
    blocking = [p for p in verdict.problems if not p.startswith("changed the capitalisation")]
    if blocking:
        return []
    return [Edit(
        check_id="FMT-TITLE-03",
        tier=Tier.SUGGEST,
        confidence=Confidence.LIKELY,
        file=file,
        start=start,
        end=end,
        before=value,
        after=report.text,
        message=(
            f"JACoW reference titles are sentence case. Every word in this "
            f"{field_name} was recognised as an ordinary word, so lowercasing is safe; "
            "reject if any of them is a name."
        ),
        rule="JACoW Annex B: reference titles in sentence case",
    )]


# ---------------------------------------------------------------------------
# \bibitem body edits
# ---------------------------------------------------------------------------

_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


def bibitem_spans(source: str) -> list[tuple[str, int, int]]:
    """``(key, body_start, body_end)`` for each ``\\bibitem`` in the bibliography."""
    block = re.search(
        r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}", source, re.DOTALL
    )
    if not block:
        return []
    block_start, block_end = block.span()
    end_tag = source.rfind(r"\end{thebibliography}", block_start, block_end)
    matches = list(_BIBITEM_RE.finditer(source, block_start, block_end))
    spans: list[tuple[str, int, int]] = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else end_tag
        spans.append((match.group(1).strip(), body_start, body_end))
    return spans


def bibitem_rewrite_edits(
    source: str,
    paper: Paper,
    *,
    file: str = "",
    evidence_words: set[str] | None = None,
    offline: bool = False,
) -> tuple[list[Edit], list[Finding]]:
    """Offer a JACoW-formatted rewrite of each ``\\bibitem`` body.

    Every body goes through :func:`src.references.screen_reference` — the
    same engine and the same tiers as a Word reference — after conversion to
    plain text; the result is converted back with DOIs as ``\\doi{…}``.
    A rewrite that fails ``check_rewrite`` is dropped and reported.
    """
    from src.references import latex_to_plain, plain_to_latex, screen_reference

    edits: list[Edit] = []
    findings: list[Finding] = []
    parsed = paper.__dict__.get("_pt")
    if not parsed or parsed.bibliography_env != "thebibliography":
        return edits, findings

    for number, (key, body_start, body_end) in enumerate(bibitem_spans(source), start=1):
        original_body = source[body_start:body_end]
        plain = latex_to_plain(original_body)
        if not plain:
            continue
        result = screen_reference(plain, label=f"Reference {{{key}}}", offline=offline)
        findings.extend(result.findings)
        if result.after is None or result.tier is None:
            continue

        rewritten = plain_to_latex(result.after)
        leading = original_body[: len(original_body) - len(original_body.lstrip())]
        trailing = original_body[len(original_body.rstrip()):]
        after = f"{leading}{rewritten}{trailing}"
        if after == original_body:
            continue

        edits.append(Edit(
            check_id="FMT-REF-01",
            # A whole-reference rewrite of LaTeX source is always a decision:
            # the conversion back to LaTeX is ours, not the author's.
            tier=Tier.SUGGEST,
            confidence=Confidence.LIKELY,
            file=file,
            start=body_start,
            end=body_end,
            before=original_body,
            after=after,
            message=result.message,
            rule="JACoW Annex B: reference layout",
            evidence=Evidence(
                source=result.evidence_source if result.added_from else "local-rule",
                detail=(f"added from {result.added_from}" if result.added_from
                        else "jacow_formatter, verified by check_rewrite"),
            ),
        ))

    return edits, findings


# ---------------------------------------------------------------------------
# Citation-order reordering lives in src.autofix.structural: a permutation of
# the entry list overlaps every narrow edit inside it, so it cannot be a span
# edit without forcing the editor to choose between reordering and the DOI and
# unit fixes in the same region.  See that module's docstring.
# ---------------------------------------------------------------------------
