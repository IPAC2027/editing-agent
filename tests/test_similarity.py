"""Tests for src.refs.similarity (adapted from TestTitleSimilarity)."""

from src.refs.similarity import title_similarity


def test_identical_titles():
    assert title_similarity(
        "Deep learning for physics", "Deep learning for physics",
    ) == 1.0


def test_completely_different():
    assert title_similarity(
        "Deep learning", "Quantum computing experiments",
    ) < 0.3


def test_empty_a():
    assert title_similarity("", "anything") == 0.0


def test_empty_b():
    assert title_similarity("anything", "") == 0.0


def test_both_empty():
    assert title_similarity("", "") == 0.0


def test_slight_variation_high_score():
    a = "Novel techniques for future TeV electron accelerators"
    b = "Novel techniques for a future TeV electron accelerator"
    assert title_similarity(a, b) > 0.7


def test_short_tokens_are_filtered():
    # Tokens shorter than 3 characters do not contribute to Jaccard
    # so 'a' / 'an' / 'or' do not match by themselves.
    assert title_similarity("a or an", "if so be") == 0.0


def test_ascii_fold_strips_accents():
    # Accented characters should fold to their ASCII counterparts for the
    # purpose of similarity scoring.  The bigram component still shifts
    # slightly when surrounding characters differ, so the score is close to
    # but not exactly 1.0 even on otherwise-identical strings.
    assert title_similarity(
        "Étude de l'accélérateur linéaire",
        "Etude de l'accelerateur lineaire",
    ) > 0.95
    # With a removed apostrophe one extra token boundary is lost, so the
    # score drops further but still beats two unrelated strings handily.
    assert title_similarity(
        "Étude de l'accélérateur linéaire",
        "Etude de laccelerateur lineaire",
    ) > 0.6
