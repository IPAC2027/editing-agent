"""Document-level audit of a Word paper, from the jacow-paper-formatting skill.

The skill's ``scripts/audit_jacow_docx.py`` is vendored unchanged in
``src/checks/vendor/`` (the whole skill is kept in
``src/knowledge/jacow-paper-formatting-skill/`` as the rule reference).  Its
PASS/WARN/FAIL lines become findings; what the agent already checks or fixes
paragraph by paragraph (justification, indent, widow control) is not repeated.
"""

from __future__ import annotations

from pathlib import Path

from src.models import Finding, Severity

# Message prefix -> check id.  Lines the agent covers itself map to None.
_MAP = (
    ("Section", "WORD-LAYOUT-01"),            # page size, margins, columns
    ("Fonts", "WORD-FONT-01"),
    ("Font ", "WORD-FONT-01"),
    ("Non-allowed font", "WORD-FONT-01"),
    ("Dominant font size", "WORD-FONT-02"),
    ("Fonts not embedded", "WORD-FONT-03"),
    ("Non-DOI hyperlinks", "WORD-LINK-01"),
    ("DOI hyperlink", "WORD-LINK-02"),
    ("Page-number", "WORD-PAGENUM-01"),
    ("Page number", "WORD-PAGENUM-01"),
    ("Word footnotes", "WORD-FOOTNOTE-01"),
    ("Reference line spacing", "WORD-REFSPACE-01"),
    ("Title", "WORD-TITLE-03"),
    ("Body justification", None),
    ("Body first-line indent", None),
    ("Widow/orphan", None),
)


def audit_findings(doc_path: Path) -> list[Finding]:
    from docx import Document

    from src.checks.vendor import audit_jacow_docx as audit

    audit.results.clear()
    doc = Document(str(doc_path))
    for check in (audit.check_page, audit.check_fonts, audit.check_structure):
        try:
            check(doc)
        except Exception:  # noqa: BLE001 — one failing audit never hides the others
            continue
    for check in (audit.check_zip,):
        try:
            check(str(doc_path))
        except Exception:  # noqa: BLE001
            continue
    try:
        audit.check_doi_links(doc, str(doc_path))
    except Exception:  # noqa: BLE001
        pass
    findings = []
    for level, message in list(audit.results):
        if level not in ("FAIL", "WARN"):
            continue
        check_id = next((cid for prefix, cid in _MAP if message.startswith(prefix)), "WORD-AUDIT-01")
        if check_id is None:
            continue
        findings.append(Finding(
            check_id=check_id,
            severity=Severity.WARNING if level == "FAIL" else Severity.INFO,
            message=message))
    audit.results.clear()
    return findings
