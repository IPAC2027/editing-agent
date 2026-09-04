"""Title similarity using Jaccard + Dice over tokens and bigrams.

Migrated verbatim from the v1.0.0 standalone formatter (lines 1719-1745).
Pure stdlib, no network. Used by :mod:`src.refs.conference_db` matching and by
any future RefDB-style search code.
"""

from __future__ import annotations

import re
import unicodedata


def ascii_fold(s: str) -> str:
    """Return *s* normalised to ASCII lowercase (strips accents and case)."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def title_tokens(s: str) -> list[str]:
    """Tokenise *s* for similarity scoring.

    Folds to ASCII, replaces non-word chars with spaces, then keeps tokens of
    length ≥ 3 so common short words don't dominate the Jaccard intersection.
    """
    s = ascii_fold(s)
    s = re.sub(r"[^\w\s]", " ", s)
    return [w for w in s.split() if len(w) >= 3]


def bigrams(s: str) -> list[str]:
    """Return character bigrams of *s* after ASCII-folding and removing whitespace."""
    s = ascii_fold(re.sub(r"\s+", "", s))
    return [s[i : i + 2] for i in range(len(s) - 1)]


def title_similarity(a: str, b: str) -> float:
    """Return a 0–1 similarity score between two title strings.

    Blends Jaccard / containment over ≥3-char tokens with Dice over character
    bigrams. Returns ``0.0`` if either input is empty or has no usable tokens.
    Rounded to 4 decimal places to keep cache keys stable.
    """
    if not a or not b:
        return 0.0
    ta, tb = set(title_tokens(a)), set(title_tokens(b))
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    shorter = ta if len(ta) <= len(tb) else tb
    longer = tb if len(ta) <= len(tb) else ta
    containment = len(shorter & longer) / len(shorter) if shorter else 0.0
    ba, bb = bigrams(a), bigrams(b)
    dice = (
        2 * len(set(ba) & set(bb)) / (len(ba) + len(bb))
        if ba and bb
        else 0.0
    )
    return round(0.65 * max(jaccard, containment * 0.9) + 0.35 * dice, 4)
