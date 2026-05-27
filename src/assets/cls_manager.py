"""Download and cache the latest JACoW LaTeX class files.

Files are stored in ``<project_root>/assets/jacow/`` and re-used on subsequent
runs.  Call ``ensure_cls_files()`` to get the directory; it downloads only if
the files are missing or ``force=True`` is passed.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

# Raw GitHub URLs for the three required files (v3.0, 2026-02-10)
_BASE = "https://raw.githubusercontent.com/JACoW-org/JACoW_Templates/master/LaTeX"
_CLS_FILES = {
    "jacow.cls": f"{_BASE}/jacow.cls",
    "jacow.bbx": f"{_BASE}/jacow.bbx",
    "jacow.cbx": f"{_BASE}/jacow.cbx",
}

# assets/jacow/ lives two levels above this file: src/assets/ → project root
_ASSETS_DIR = Path(__file__).parent.parent.parent / "assets" / "jacow"


def ensure_cls_files(force: bool = False) -> Path:
    """Return the path to the local ``assets/jacow/`` directory.

    Downloads missing files from GitHub.  If *force* is ``True``, re-downloads
    all files regardless of whether they already exist.

    Raises ``RuntimeError`` if a download fails and no cached copy is present.
    """
    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in _CLS_FILES.items():
        dest = _ASSETS_DIR / filename
        if dest.exists() and not force:
            continue
        _download(url, dest)

    return _ASSETS_DIR


def _download(url: str, dest: Path) -> None:
    """Download *url* to *dest*, with a simple retry on failure."""
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        headers = {"User-Agent": "jacow-aiagent/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, tmp.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.replace(dest)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if dest.exists():
            # Keep stale cache rather than crash
            import warnings
            warnings.warn(
                f"Could not refresh {dest.name} ({exc}); using cached copy.",
                stacklevel=3,
            )
        else:
            raise RuntimeError(
                f"Failed to download {dest.name} from {url}: {exc}\n"
                "Check your internet connection or manually place the file in "
                f"{dest.parent}."
            ) from exc


def cls_files_present() -> bool:
    """Return ``True`` if all three cls files are already cached."""
    return all((_ASSETS_DIR / f).exists() for f in _CLS_FILES)
