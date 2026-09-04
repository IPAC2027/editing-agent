"""External metadata lookups for the reformat autofix.

Currently houses the Open Library ISBN → publisher lookup
(``isbn_publisher_lookup``).  Migrated from the v1.0.0 standalone
formatter (line 4248).

The HTTP client is :mod:`httpx` (matches the rest of the package);
responses are in-memory cached for the process lifetime.  No
SqliteCache dependency in this Tier-1.5 pass.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# In-process cache: ISBN -> publisher string (or "" on failure).
# Lives for the life of the interpreter.
_cache: dict[str, str] = {}


def _http_get_json(url: str, timeout: float = 10.0) -> Optional[dict]:
    """GET *url* and return the parsed JSON body, or ``None`` on any failure.

    Used by :func:`isbn_publisher_lookup` for the Open Library request.
    Deliberately silent on errors — the lookup is best-effort and the
    caller (reformat autofix) treats a None return as "no publisher
    found" without a network warning.
    """
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": "aiagent-formatter/0.1"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("Open Library request failed: %s", exc)
        return None


def isbn_publisher_lookup(
    isbn: str,
    *,
    api_url: str = "https://openlibrary.org/api/books",
) -> Optional[str]:
    """Look up the publisher for a given ISBN via Open Library.

    Returns the publisher name string, or ``None`` on failure (bad
    ISBN format, network error, no publisher data, etc.).  Responses
    are cached for the process lifetime — publisher metadata is
    stable enough that this rarely changes.
    """
    if not isbn:
        return None

    isbn_clean = re.sub(r"[^0-9X]", "", isbn.upper())
    if len(isbn_clean) not in (10, 13):
        return None

    if isbn_clean in _cache:
        return _cache[isbn_clean] or None

    url = (
        f"{api_url}?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
    )
    data = _http_get_json(url)
    if not data:
        _cache[isbn_clean] = ""  # negative-cache so we don't retry forever
        return None

    book_data = data.get(f"ISBN:{isbn_clean}") or {}
    publishers = book_data.get("publishers") or []
    if publishers:
        name = publishers[0].get("name", "")
        if name:
            _cache[isbn_clean] = name
            logger.debug("ISBN publisher lookup: %s → %s", isbn_clean, name)
            return name

    _cache[isbn_clean] = ""
    return None
