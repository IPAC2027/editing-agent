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
:func:`src.refs.verify.check_rewrite`, and a rewrite that fails is discarded
with the reason recorded as a finding — the editor is told the reference looks
wrong *and* why the agent would not touch it, which is more useful than a
damaged reference.
"""

from __future__ import annotations

import re

from src.edits import Confidence, Edit, Evidence, Tier, make_edit
from src.models import Finding, Paper, Reference, Severity
from src.refs.text_utils import sent_case_report
from src.refs.verify import check_rewrite, proper_noun_risk

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
) -> tuple[list[Edit], list[Finding]]:
    """Offer a JACoW-formatted rewrite of each ``\\bibitem`` body.

    Always :attr:`Tier.SUGGEST` — a whole-reference rewrite is never applied
    without a human looking at it — and always verified by
    :func:`src.refs.verify.check_rewrite` first.  When verification fails the
    rewrite is dropped and a finding explains what the formatter would have
    damaged, so the editor knows to look at the reference themselves.
    """
    from src.refs import JacoWConnector, format_ref, normalize_journal

    edits: list[Edit] = []
    findings: list[Finding] = []
    parsed = paper.__dict__.get("_pt")
    if not parsed or parsed.bibliography_env != "thebibliography":
        return edits, findings

    by_key = {ref.key: ref for ref in paper.references if getattr(ref, "key", None)}
    if not by_key:
        return edits, findings

    connector = JacoWConnector(allow_network=False)

    for key, body_start, body_end in bibitem_spans(source):
        reference = by_key.get(key)
        if reference is None:
            continue
        record = _reference_to_record(reference, evidence_words)
        if not record:
            continue

        if record.get("conference") and record.get("year"):
            record = connector.complete_record(record, [])
        if record.get("journal"):
            normalised = normalize_journal(record["journal"])
            if normalised:
                record["journal"] = normalised

        try:
            formatted = format_ref(record, record.get("ref_type", "journal"))
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding(
                check_id="FMT-REF-01",
                severity=Severity.INFO,
                message=(
                    f"Reference {{{key}}} could not be reformatted automatically "
                    f"({type(exc).__name__}); left exactly as submitted."
                ),
            ))
            continue

        original_body = source[body_start:body_end]
        original = original_body.strip()
        rewritten = (formatted or "").strip()
        if not rewritten or rewritten == original:
            continue

        verdict = check_rewrite(
            original,
            rewritten,
            allow_case_change=False,
            unsure_tokens=record.get("_unsure_tokens", ()),
        )
        if not verdict.ok:
            risky = proper_noun_risk(original, rewritten)
            detail = verdict.reason
            if risky:
                detail += f" (words at risk: {', '.join(risky[:4])})"
            findings.append(Finding(
                check_id="FMT-REF-01",
                severity=Severity.INFO,
                message=(
                    f"Reference {{{key}}}: a JACoW-style rewrite was computed but "
                    f"rejected because it would have {detail}. The reference is "
                    "unchanged — check it by hand if the formatting looks wrong."
                ),
                original=original[:240],
            ))
            continue

        # Preserve the surrounding whitespace so the diff stays a body change.
        leading = original_body[: len(original_body) - len(original_body.lstrip())]
        trailing = original_body[len(original_body.rstrip()):]
        after = f"{leading}{rewritten}{trailing}"
        if after == original_body:
            continue

        edits.append(Edit(
            check_id="FMT-REF-01",
            tier=Tier.SUGGEST,
            confidence=Confidence.LIKELY,
            file=file,
            start=body_start,
            end=body_end,
            before=original_body,
            after=after,
            message=(
                f"Reference {{{key}}} reformatted to JACoW Annex B style. "
                "Verified to preserve every number, DOI, word and capital in the original."
            ),
            rule="JACoW Annex B: reference layout",
            evidence=Evidence(source="local-rule", detail="deterministic formatter"),
        ))

    return edits, findings


def _reference_to_record(
    reference: Reference,
    evidence_words: set[str] | None = None,
) -> dict | None:
    """Map a :class:`Reference` onto the formatter's record dict.

    Returns ``None`` when the minimum fields (authors, title, year) are absent —
    the formatter has nothing to work with and guessing is exactly what this
    codebase must not do.
    """
    authors_raw = " and ".join(reference.authors) if reference.authors else ""
    if not authors_raw:
        return None
    title = (reference.title or "").strip()
    if not title:
        return None

    date = reference.date or ""
    month = ""
    year = ""
    match = re.match(r"^(\S+)\s+(\d{4})$", date)
    if match:
        month, year = match.group(1), match.group(2)
    else:
        found = re.search(r"\d{4}", date)
        year = found.group(0) if found else ""
    if not year:
        return None

    casing = _case_report(title, evidence=evidence_words)
    record: dict = {
        "authors_raw": authors_raw,
        "title": casing.text if not casing.unsure else title,
        "year": year,
        "_unsure_tokens": casing.unsure,
    }
    if month:
        record["month"] = month
    if reference.ref_type:
        record["ref_type"] = reference.ref_type

    container = reference.container_title
    ref_type = (reference.ref_type or "").lower()
    if container:
        if ref_type in ("journal", "journal_accepted", "journal_submitted"):
            record["journal"] = container
        elif ref_type in ("book", "book_chapter"):
            record["booktitle"] = container
        elif ref_type.startswith(("proceedings", "conference")):
            record["conference"] = container

    if reference.venue_location:
        parts = [part.strip() for part in reference.venue_location.split(",", 1)]
        if parts:
            record["city"] = parts[0]
        if len(parts) > 1:
            record["country"] = parts[1]

    for key in ("doi", "url", "volume", "issue", "pages"):
        value = getattr(reference, key, None)
        if value:
            record[key] = value

    if ref_type == "arxiv" and not record.get("doi"):
        found = re.search(
            r"arXiv:\s*([\w.\-]+/?\d+|\d{4}\.\d{4,5})",
            reference.raw_text or "",
            re.IGNORECASE,
        )
        if found:
            record["arxiv_id"] = found.group(1)

    return record


# ---------------------------------------------------------------------------
# Citation-order reordering lives in src.autofix.structural: a permutation of
# the entry list overlaps every narrow edit inside it, so it cannot be a span
# edit without forcing the editor to choose between reordering and the DOI and
# unit fixes in the same region.  See that module's docstring.
# ---------------------------------------------------------------------------
