"""Tests for src.autofix.word_fixes — the line-level Word reference auto-fixers.

Today this covers AUTH-01 (Oxford-comma insertion).  The Oxford comma is
only valid for 3+ author lists; for 1 or 2 authors it would be wrong.
The fix counts authors by splitting the author section on ``, `` and
the separator ``and``, not by counting commas naively (which used to
mis-classify 3-author no-Oxford lists like ``"A. Alpha, B. Beta and
C. Gamma"`` as 2-author).
"""

from src.autofix.word_fixes import _fix_oxford_comma


# ── 1 author ────────────────────────────────────────────────────────────────

def test_1_author_no_change():
    text, findings = _fix_oxford_comma(
        1, 'A. Smith, "A paper", Nature, 2020.',
    )
    assert text == 'A. Smith, "A paper", Nature, 2020.'
    assert findings == []


# ── 2 authors (the regression case) ─────────────────────────────────────────

def test_2_authors_no_comma_added():
    """The exact case from the user report: 2 authors must not get an
    Oxford comma inserted.  Previously the buggy guard ``n_and < 1``
    let this case through and produced ``J. Wang, and G. S. Sprau``."""
    text, findings = _fix_oxford_comma(
        1, 'J. Wang and G. S. Sprau, "A paper", Nature, 2020.',
    )
    assert text == 'J. Wang and G. S. Sprau, "A paper", Nature, 2020.'
    assert findings == []


def test_2_authors_with_initials():
    text, findings = _fix_oxford_comma(
        1, 'A. B. Smith and C. D. Jones, "A paper", 2020.',
    )
    assert text == 'A. B. Smith and C. D. Jones, "A paper", 2020.'
    assert findings == []


def test_2_authors_comma_between_first_names_not_after_comma():
    """The author count must look at name boundaries (', ' followed by a
    capital letter), not every comma.  Initials like 'A. B.' contain
    periods that should not influence the count."""
    text, findings = _fix_oxford_comma(
        1, 'A. B. Smith, C. D. Jones and E. F. King, "A paper", 2020.',
    )
    # This is 3 authors, no Oxford — should be rewritten with Oxford.
    assert 'B. Smith, C. D. Jones, and E. F. King' in text
    assert len(findings) == 1 and findings[0].check_id == 'AUTH-01'


# ── 3 authors ───────────────────────────────────────────────────────────────

def test_3_authors_no_oxford_adds_comma():
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta and C. Gamma, "A paper", 2020.',
    )
    assert text == 'A. Alpha, B. Beta, and C. Gamma, "A paper", 2020.'
    assert len(findings) == 1
    assert findings[0].check_id == 'AUTH-01'
    assert findings[0].auto_fixed is True
    assert '3 authors' in findings[0].message


def test_3_authors_with_oxford_unchanged():
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta, and C. Gamma, "A paper", 2020.',
    )
    assert text == 'A. Alpha, B. Beta, and C. Gamma, "A paper", 2020.'
    assert findings == []


# ── 4+ authors ─────────────────────────────────────────────────────────────

def test_4_authors_no_oxford_adds_only_one_comma():
    """The fix must only insert the Oxford comma, not duplicate existing
    commas.  ``"A, B, C and D"`` becomes ``"A, B, C, and D"``, not
    ``"A,, B,, C, and D"``."""
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta, C. Gamma and D. Delta, "A paper", 2020.',
    )
    assert text == 'A. Alpha, B. Beta, C. Gamma, and D. Delta, "A paper", 2020.'
    assert len(findings) == 1
    assert findings[0].check_id == 'AUTH-01'
    # No double-commas anywhere
    assert ',,' not in text


def test_4_authors_with_oxford_unchanged():
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta, C. Gamma, and D. Delta, "A paper", 2020.',
    )
    assert text == 'A. Alpha, B. Beta, C. Gamma, and D. Delta, "A paper", 2020.'
    assert findings == []


def test_5_authors_no_oxford():
    text, findings = _fix_oxford_comma(
        1, 'A. A, B. B, C. C, D. D and E. E, "A paper", 2020.',
    )
    assert text == 'A. A, B. B, C. C, D. D, and E. E, "A paper", 2020.'
    assert len(findings) == 1


# ── Edge cases ──────────────────────────────────────────────────────────────

def test_no_title_returns_unchanged():
    """No quoted title means we can't safely identify the author section,
    so the fix is a no-op."""
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta and C. Gamma',  # no title
    )
    assert findings == []
    assert text == 'A. Alpha, B. Beta and C. Gamma'


def test_3_authors_with_lowercase_and():
    """The ``and`` match is case-insensitive (\\b pattern)."""
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta And C. Gamma, "T", 2020.',
    )
    assert 'and C. Gamma' in text
    assert len(findings) == 1


def test_finding_records_author_count():
    """The diagnostic message should report how many authors were detected
    so editors can spot misclassifications."""
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta and C. Gamma, "T", 2020.',
    )
    assert findings[0].message == (
        "Reference [1]: added Oxford comma before 'and' in "
        "author list (3 authors)."
    )


def test_finding_carries_original_and_suggested():
    text, findings = _fix_oxford_comma(
        1, 'A. Alpha, B. Beta and C. Gamma, "T", 2020.',
    )
    # author_part runs up to the opening quote of the title, so it
    # includes the trailing comma that separates the author list from
    # the title.
    assert findings[0].original.strip() == 'A. Alpha, B. Beta and C. Gamma,'
    assert findings[0].suggested.strip() == 'A. Alpha, B. Beta, and C. Gamma,'
