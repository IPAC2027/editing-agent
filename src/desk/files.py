"""Files in a pool that several desks read and write at once.

The papers can sit in a folder shared over the network from the chief editor's
computer, with every editor's desk reading and writing it at the same time.
Two things that are harmless on one computer go wrong there:

* A file written in place is briefly half-written. A desk that reads it at
  that moment sees broken JSON — and the review state treats broken JSON as
  "no work yet", so the next save would erase the editor's decisions. Writing
  to a temporary file beside it and renaming it into place means a reader sees
  either the old file or the new one, never a mixture.

* A path recorded on one computer means nothing on another. The chief's
  ``/Users/chief/NAPAC2025/MOP001/...`` is ``/Volumes/NAPAC2025/MOP001/...`` on
  a Mac that mounts the share and ``Z:\\MOP001\\...`` on Windows. Paths are
  therefore stored relative to the paper, and an old absolute one is found
  again by its tail.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

#: How often a rename is retried. Windows refuses to replace a file another
#: program has open — on a share, another editor's desk reading it — so a
#: failed rename is usually a moment's wait, not an error.
_REPLACE_ATTEMPTS = 8


def write_text(path: Path, text: str) -> Path:
    """Write *text* to *path* so that no reader ever sees half of it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:10]}.part")
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(temp, path)
                return path
            except PermissionError:
                if attempt == _REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return path


def relative_to_paper(path: Path | str, folder: Path) -> str:
    """*path* as recorded in a paper's files: relative to the paper if it is inside.

    Forward slashes, so a report written on Windows reads on a Mac and back.
    """
    path = Path(path)
    try:
        return path.resolve().relative_to(Path(folder).resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def source_file(folder: Path, stored: str | None) -> Path | None:
    """The file a paper's report points at, on this computer.

    *stored* is relative to the paper (what reports record now), or an absolute
    path from whichever computer prepared the paper (what they used to record).
    An absolute path is matched by its tail inside *folder* first, so a paper
    prepared on the chief's computer is found from any editor's mount; it is
    used as it stands only when no part of it is under *folder*.
    """
    if not stored:
        return None
    parts = [part for part in re.split(r"[\\/]+", stored) if part and part != "."]
    if not parts:
        return None
    if re.fullmatch(r"[A-Za-z]:", parts[0]):  # a Windows drive letter
        parts = parts[1:]
    for start in range(len(parts)):
        if ".." in parts[start:]:
            continue
        candidate = Path(folder).joinpath(*parts[start:])
        if candidate.is_file():
            return candidate
    as_is = Path(stored)
    return as_is if as_is.is_absolute() and as_is.is_file() else None
