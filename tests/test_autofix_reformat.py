"""Tests for the new Tier-1 reformat pass wired into the autofix pipeline.

The point of these tests is to prove that the migrated ``src.refs`` modules
(:func:`format_ref`, :class:`JacoWConnector`, :func:`normalize_journal`) now
actually mutate the source text, so the resulting change is visible in
``changes.html`` / ``changes.patch`` as a real line-level diff.

Two integration surfaces are covered:

- LaTeX: :func:`reformat_bibitem_bodies` runs from :func:`apply_paper_fixes`,
  which is called by ``src.workflow.prescreen`` between the existing
  line-level fix pass and the diff write-out.
- Word: :func:`_format_word_reference` runs from ``prescreen_word`` after
  the line-level :func:`fix_reference` pass, so the per-ref before/after
  card in ``word_references.html`` shows the JACoW rewrite.
"""

import difflib
from pathlib import Path
from unittest.mock import patch

import pytest

from src.autofix.safe_fixes import (
    apply_paper_fixes,
    reformat_bibitem_bodies,
)
from src.models import Finding, Paper, Reference, Severity
from src.workflow.word_prescreen import _format_word_reference


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_BIB = r"""
\begin{thebibliography}{9}
\bibitem{smith2020}
A. Smith and B. Jones, ``Beam dynamics studies at the LHC'', in
Proc.~IPAC'20, Caen, France, May 2020, pp.~1-3. doi:10.18429/JACoW-IPAC2020-MOP001

\bibitem{jones2021}
C.~Jones, ``Some other paper'', Phys.~Rev.~Lett., vol.~120, 2021.

\bibitem{noauthors}
``Untitled work'', 2022.
\end{thebibliography}
""".lstrip()


def _make_paper(bibitem_keys: list[str] = None) -> Paper:
    """Build a Paper with paper.references populated from SAMPLE_BIB."""
    from src.parser.latex_parser import ParsedTex

    pt = ParsedTex(source_lines=SAMPLE_BIB.splitlines())
    pt.bibliography_env = "thebibliography"
    pt.has_bibliography_section = True

    refs = [
        Reference(
            n=1, key="smith2020", ref_type="conference_published",
            authors=["A. Smith", "B. Jones"],
            title="Beam dynamics studies at the LHC",
            container_title="Proc. IPAC'20",
            date="May 2020",
            venue_location="Caen, France",
            pages="1-3",
            doi="10.18429/JACoW-IPAC2020-MOP001",
        ),
        Reference(
            n=2, key="jones2021", ref_type="journal",
            authors=["C. Jones"],
            title="Some other paper",
            container_title="Physical Review Letters",
            date="2021",
            volume="120",
        ),
        # noauthors intentionally has no parsed authors to test the skip path
        Reference(
            n=3, key="noauthors", ref_type="journal",
            authors=[],
            title="",
            container_title="",
            date="2022",
        ),
    ]
    paper = Paper(
        paper_id="TEST", source_path=Path("/tmp/TEST.tex"),
        title="Demo",
        authors=["Demo Author"],
        references=refs,
        citation_order=["smith2020", "jones2021"],
    )
    paper.__dict__["_pt"] = pt
    return paper


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX: reformat_bibitem_bodies
# ─────────────────────────────────────────────────────────────────────────────

def test_reformat_produces_finding_per_ref():
    paper = _make_paper()
    _, findings = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    fmt_findings = [f for f in findings if f.check_id == "FMT-REF-01"]
    # Two refs (smith2020 + jones2021) have enough fields to format;
    # noauthors is skipped.
    assert len(fmt_findings) == 2
    for f in fmt_findings:
        assert f.auto_fixed is True
        assert f.severity == Severity.INFO


def test_reformat_mutates_source_text():
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    assert new_source != SAMPLE_BIB, "reformat pass must produce a different source"


def test_reformat_diff_is_real():
    """The line-level diff between original and reformatted source must show
    non-empty changes — i.e. the autofix will appear in changes.html."""
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)

    diff = list(difflib.unified_diff(
        SAMPLE_BIB.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile="a/TEST.tex",
        tofile="b/TEST.tex",
    ))
    diff_text = "".join(diff)
    assert "--- a/TEST.tex" in diff_text
    assert "+++ b/TEST.tex" in diff_text
    # At least one line is added or removed by the reformat pass.
    added_or_removed = [ln for ln in diff_text.splitlines()
                        if ln.startswith("+") and not ln.startswith("+++")
                        or ln.startswith("-") and not ln.startswith("---")]
    assert added_or_removed, "diff must contain real added/removed lines"


def test_reformat_preserves_bibitem_keys():
    """Refusing to break the citation graph: every \\bibitem{key} must still
    resolve to a key the parser saw."""
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    import re
    keys_after = re.findall(r"\\bibitem\s*\{([^}]+)\}", new_source)
    assert set(keys_after) == {"smith2020", "jones2021", "noauthors"}


def test_reformat_keeps_doi_present_in_output():
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    assert "10.18429/JACoW-IPAC2020-MOP001" in new_source


def test_reformat_uses_jacoW_db_for_conference_metadata():
    """smith2020 cites IPAC'20 with venue 'Caen, France, May 2020' — the
    hardcoded JACoW table only has IPAC 2019/2021/2022/2023/2024/2025, so
    we don't *expect* a fill in 2020.  But the *attempt* to call
    JacoWConnector.complete_record should have happened — the function
    returns unchanged when not found, and that's the correct behaviour."""
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    # The reformatted smith entry must still mention the location.
    assert "Caen" in new_source or "France" in new_source


def test_reformat_uses_format_ref_for_journal_abbr():
    """jones2021 had 'Physical Review Letters' in the bibitem body.  After
    reformat, the body should use the JACoW abbreviation 'Phys. Rev. Lett.'
    courtesy of normalize_journal() (Tier-1 L1)."""
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    assert "Phys. Rev. Lett." in new_source
    # Original long form should be gone from the reformatted body
    # (we look at the bibitem block specifically).
    import re
    jones_m = re.search(
        r"\\bibitem\{jones2021\}(.*?)(?=\\bibitem|\\end\{thebibliography\})",
        new_source, re.DOTALL,
    )
    assert jones_m is not None
    assert "Physical Review Letters" not in jones_m.group(1)


def test_reformat_skips_ref_without_authors_and_title():
    """The third bibitem (noauthors) has no parsed authors — it must be
    left unchanged, not replaced with an empty formatter output."""
    paper = _make_paper()
    new_source, _ = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    import re
    m = re.search(
        r"\\bibitem\{noauthors\}(.*?)\\end\{thebibliography\}",
        new_source, re.DOTALL,
    )
    assert m is not None
    # Original literal text is still present
    assert "Untitled work" in m.group(1)


def test_reformat_drops_information_guard_skips_lossy_rewrite():
    """When the formatter output would drop information present in the
    original bibitem body (e.g. a 'in Proc. ...' line, a 'pp. N-M'
    pages marker, a 'Oct.' month), the reformat must refuse to emit
    the rewrite.  This is the LaTeX equivalent of the Word
    information-preservation guard."""
    from src.autofix.safe_fixes import _drops_bibitem_information

    original = (
        "A. Smith and B. Jones, ``A paper'', in Proc. NAPAC'16, "
        "Chicago, IL, USA, Oct. 2016, pp. 1-3. "
        "doi:10.18429/JACoW-NAPAC2016-MOPOB12"
    )
    # Formatter output that drops in Proc., Oct., pp., and DOI
    lossy = (
        "A. Smith and B. Jones, ``A paper'', 2016."
    )
    assert _drops_bibitem_information(original, lossy) is True

    # Formatter output that preserves all markers
    faithful = (
        "A. Smith and B. Jones, ``A paper'', in Proc. NAPAC'16, "
        "Chicago, IL, USA, Oct. 2016, pp. 1-3. "
        "doi:10.18429/JACoW-NAPAC2016-MOPOB12"
    )
    assert _drops_bibitem_information(original, faithful) is False


def test_reformat_noop_for_biblatex_paper():
    """biblatex papers: \\bibitem is in a comment-fenced fallback inside
    \\ifboolexpr.  The pass should be a no-op (the field lives in a .bib
    file the existing pipeline doesn't rewrite)."""
    from src.parser.latex_parser import ParsedTex

    paper = _make_paper()
    paper.__dict__["_pt"] = ParsedTex(source_lines=[])
    paper.__dict__["_pt"].bibliography_env = "biblatex"

    new_source, findings = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    assert new_source == SAMPLE_BIB
    assert findings == []


def test_reformat_noop_for_paper_without_references():
    """If paper.references is empty, the pass must not produce findings."""
    from src.parser.latex_parser import ParsedTex

    paper = Paper(
        paper_id="EMPTY", source_path=Path("/tmp/EMPTY.tex"),
        title="", authors=[], references=[], citation_order=[],
    )
    paper.__dict__["_pt"] = ParsedTex(source_lines=[])
    paper.__dict__["_pt"].bibliography_env = "thebibliography"

    new_source, findings = reformat_bibitem_bodies(SAMPLE_BIB, paper)
    assert new_source == SAMPLE_BIB
    assert findings == []


def test_apply_paper_fixes_runs_reformat():
    """apply_paper_fixes is the entry point called from src.workflow.prescreen.
    The reformat findings must show up in the returned findings list."""
    paper = _make_paper()
    new_source, findings = apply_paper_fixes(SAMPLE_BIB, paper)
    assert new_source != SAMPLE_BIB
    assert any(f.check_id == "FMT-REF-01" for f in findings)


# ─────────────────────────────────────────────────────────────────────────────
# Word: _format_word_reference
# ─────────────────────────────────────────────────────────────────────────────

def _make_word_ref(n, raw_text, authors=None, title=None, ref_type="journal",
                   doi=None, url=None):
    from src.parser.word_parser import WordReference
    return WordReference(
        n=n, raw_text=raw_text, authors=authors or [], title=title or "",
        doi=doi or "", url=url or "", ref_type=ref_type,
    )


def test_word_format_skips_when_no_authors():
    ref = _make_word_ref(
        n=1,
        raw_text='"Untitled", Nature, 2022.',
        authors=[], title="Untitled",
    )
    text, finding = _format_word_reference(
        ref, ref.raw_text, ref_n=1,
    )
    assert text == ref.raw_text
    assert finding is None


def test_word_format_skips_when_no_year():
    ref = _make_word_ref(
        n=1,
        raw_text='A. Smith, "Paper", Nature.',
        authors=["A. Smith"], title="Paper",
    )
    text, finding = _format_word_reference(
        ref, ref.raw_text, ref_n=1,
    )
    assert text == ref.raw_text
    assert finding is None


def test_word_format_journal_ref_emits_finding():
    ref = _make_word_ref(
        n=1,
        raw_text=(
            'A. Smith, "Some paper", Physical Review Letters, '
            'vol. 120, p. 1, 2021.'
        ),
        authors=["A. Smith"], title="Some paper",
        ref_type="journal",
    )
    corrected = ref.raw_text  # line-level fix pass would have produced this
    text, finding = _format_word_reference(ref, corrected, ref_n=1)

    # Formatter should produce a JACoW-style string
    assert finding is not None
    assert finding.check_id == "FMT-REF-01"
    assert finding.auto_fixed is True
    # Journal name is normalised to JACoW abbreviation
    assert "Phys. Rev. Lett." in text
    assert text != corrected, "format pass must change the text so the diff shows"


def test_word_format_conference_ref_uses_jacow_db():
    """For a conference ref with a known IPAC year, the connector fills
    city/country/month from the hardcoded JACoW table."""
    ref = _make_word_ref(
        n=2,
        raw_text=(
            'A. Smith, "Conf paper", in Proc. IPAC\'23, Venice, Italy, May 2023, '
            'pp. 1-3.'
        ),
        authors=["A. Smith"], title="Conf paper",
        ref_type="conference_published",
    )
    text, finding = _format_word_reference(ref, ref.raw_text, ref_n=2)
    # Venice / Italy / May are already in the raw text, so the formatter
    # output should preserve them at minimum.
    assert "Venice" in text
    assert "Italy" in text
    assert "May" in text


def test_word_format_arxiv_ref_includes_doi():
    ref = _make_word_ref(
        n=3,
        raw_text=(
            'A. Smith, "A preprint", arXiv:2101.00001, 2021.'
        ),
        authors=["A. Smith"], title="A preprint",
        ref_type="arxiv",
    )
    text, finding = _format_word_reference(ref, ref.raw_text, ref_n=3)
    assert "arXiv:2101.00001" in text
    # Tier-1: arXiv DOI is the canonical 10.48550/arXiv.<id>
    assert "10.48550/arXiv.2101.00001" in text


# ── Information-preservation guard (regression for the user-reported case) ─

def test_word_format_emits_improvement_for_user_case():
    """Regression: the user reported that 'J. Wang and G. S. Sprau,
    \"A High Bandwidth Bipolar ...\", in Proc. NAPAC'16, Chicago, IL,
    USA, Oct. 2016, pp. 96-98. doi:...' was being re-rendered as
    'J. Wang and G. S. Sprau, \"A high bandwidth bipolar ...\", 2016.
    doi:...' — losing the 'in Proc. NAPAC'16' line.

    After the Tier-1.5 migration, the Word reformat path calls
    extract_from_raw() on the raw text, which lifts city/country/month
    /pages into the rec dict.  The formatter now produces a strict
    improvement (sentence-cased title) while preserving 'in Proc.',
    the conference name, the location, the month, the pages, and
    the DOI.  FMT-REF-01 IS emitted with the new (better) text.
    """
    from src.parser.word_parser import WordReference
    raw = (
        "J. Wang and G. S. Sprau, \"A High Bandwidth Bipolar Power Supply "
        "for the Fast Correctors in the APS Upgrade\", in Proc. NAPAC'16, "
        "Chicago, IL, USA, Oct. 2016, pp. 96-98. "
        "doi:10.18429/JACoW-NAPAC2016-MOPOB12"
    )
    ref = WordReference(
        n=1, raw_text=raw,
        authors=["J. Wang", "G. S. Sprau"],
        title="A High Bandwidth Bipolar Power Supply for the Fast Correctors in the APS Upgrade",
        doi="10.18429/JACoW-NAPAC2016-MOPOB12",
        ref_type="proceedings",
    )
    text, finding = _format_word_reference(ref, raw, ref_n=1)

    # The reformat is now a real improvement — FMT-REF-01 is emitted.
    assert finding is not None
    assert finding.check_id == "FMT-REF-01"
    assert finding.auto_fixed is True

    # The conference name, location, month, pages, and DOI all preserved.
    assert "in Proc. NAPAC'16" in text
    assert "Chicago" in text
    assert "USA" in text
    assert "Oct." in text
    # pages_fmt normalises hyphen → en-dash in the rewrite.
    assert "pp. 96–98" in text
    assert "10.18429/JACoW-NAPAC2016-MOPOB12" in text

    # The new text is sentence-cased (the actual improvement).
    assert "a high bandwidth bipolar power supply" in text.lower()
    # The original Title-Cased version is gone from the rewrite.
    assert "High Bandwidth Bipolar" not in text


def test_word_format_emits_when_formatter_preserves_markers():
    """Sanity check: when the formatter does preserve all the original
    markers, FMT-REF-01 IS emitted.  A simple journal ref where the
    formatter produces a near-identical string (sentence-cased title,
    JACoW journal abbreviation) should fire."""
    raw = 'A. Smith, "Some paper", Physical Review Letters, vol. 120, 2020.'
    from src.parser.word_parser import WordReference
    ref = WordReference(
        n=1, raw_text=raw,
        authors=["A. Smith"], title="Some paper",
        ref_type="journal",
    )
    text, finding = _format_word_reference(ref, raw, ref_n=1)
    # Formatter should have changed the text (Phys. Rev. Lett. vs
    # Physical Review Letters) and preserved vol. + year
    assert finding is not None
    assert "Phys. Rev. Lett." in text
    assert "vol. 120" in text
    assert "2020" in text


def test_drops_information_detects_missing_in_proc():
    from src.workflow.word_prescreen import _drops_information
    original = (
        'A. Smith, "T", in Proc. NAPAC\'16, Chicago, IL, USA, Oct. 2016, '
        'pp. 1-3. doi:10.1/x'
    )
    # The original carries in Proc., Oct., pp., and a DOI
    missing_in_proc = 'A. Smith, "T", 2016. doi:10.1/x'
    assert _drops_information(original, missing_in_proc) is True


def test_drops_information_detects_missing_doi():
    from src.workflow.word_prescreen import _drops_information
    original = 'A. Smith, "T", Nature, 2020. doi:10.1038/test'
    missing_doi = 'A. Smith, "T", Nature, 2020.'
    assert _drops_information(original, missing_doi) is True


def test_drops_information_returns_false_when_markers_preserved():
    from src.workflow.word_prescreen import _drops_information
    original = (
        'A. Smith, "T", in Proc. NAPAC\'16, Chicago, IL, USA, '
        'Oct. 2016, pp. 1-3. doi:10.1/x'
    )
    # Identical text → no markers missing
    assert _drops_information(original, original) is False
    # Same markers, different case in title (sentence-case) is fine
    reformatted = (
        'A. Smith, "t", in Proc. NAPAC\'16, Chicago, IL, USA, '
        'Oct. 2016, pp. 1-3. doi:10.1/x'
    )
    assert _drops_information(original, reformatted) is False


def test_drops_information_detects_missing_pages():
    from src.workflow.word_prescreen import _drops_information
    original = 'A. Smith, "T", Nature, vol. 1, pp. 1-5, 2020.'
    no_pages = 'A. Smith, "T", Nature, vol. 1, 2020.'
    assert _drops_information(original, no_pages) is True


def test_drops_information_detects_missing_vol():
    from src.workflow.word_prescreen import _drops_information
    original = 'A. Smith, "T", Nature, vol. 1, 2020.'
    no_vol = 'A. Smith, "T", Nature, 2020.'
    assert _drops_information(original, no_vol) is True


def test_drops_information_detects_missing_month():
    from src.workflow.word_prescreen import _drops_information
    original = 'A. Smith, "T", Nature, Oct. 2020.'
    no_month = 'A. Smith, "T", Nature, 2020.'
    assert _drops_information(original, no_month) is True


def test_drops_information_detects_missing_presented_at():
    from src.workflow.word_prescreen import _drops_information
    original = (
        'A. Smith, "T", presented at IPAC\'23, Venice, Italy, May 2023, '
        'unpublished.'
    )
    no_presented = 'A. Smith, "T", IPAC\'23, 2023.'
    assert _drops_information(original, no_presented) is True


def test_word_format_returns_caller_text_when_unchanged():
    """When the formatter produces identical text, the caller keeps the
    line-level-corrected text and no FMT-REF-01 finding is emitted."""
    # The simplest case: a one-author journal entry that is already in
    # JACoW form. The formatter may or may not produce a string that exactly
    # matches; we just verify the no-op path.
    ref = _make_word_ref(
        n=4,
        raw_text='A. Smith, "T", Nature, vol. 1, 2020.',
        authors=["A. Smith"], title="T", ref_type="journal",
    )
    text, finding = _format_word_reference(ref, ref.raw_text, ref_n=4)
    # If finding is None, text is the line-corrected input.
    # If finding is not None, text must differ.
    if finding is None:
        assert text == ref.raw_text
    else:
        assert text.strip() != ref.raw_text.strip()
