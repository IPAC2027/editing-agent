"""Papers packed as zip files, to travel between the chief's desk and an editor's.

Both directions read a zip that came over the network, so reading is strict:
every name must sit under the folder the zip is meant to hold, with no
absolute paths, no ``..``, no backslashes, no links, and limits on how many
files and how many bytes it may unpack to.
"""

from __future__ import annotations

import io
import os
import stat
import zipfile
from pathlib import Path

#: A whole conference paper with its build is a few MB; this is far above it.
MAX_BYTES = 300 * 1024 * 1024
MAX_FILES = 5000

#: Files never packed: the claim belongs to the chief's desk alone, and
#: half-written files (``files.write_text``) are not files yet.
NEVER_PACKED = {"claim.json"}


def _skipped(path: Path) -> bool:
    return path.name in NEVER_PACKED or path.name.endswith(".part") or path.is_symlink()


def pack(base: Path, folder: Path) -> bytes:
    """Zip every file under *folder*, named relative to *base* with ``/``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if folder.is_dir() and not folder.is_symlink():
            # os.walk does not follow links into other folders.
            for here, dirs, names in os.walk(folder):
                dirs.sort()
                for name in sorted(names):
                    path = Path(here) / name
                    if path.is_file() and not _skipped(path):
                        archive.write(path, path.relative_to(base).as_posix())
    return buffer.getvalue()


class BadBundle(ValueError):
    """A zip that is not what it should be; nothing from it was written."""


def read(data: bytes, prefix: str) -> dict[str, bytes]:
    """The files in zip *data*, keyed by their names after *prefix* (``"a/b/"``).

    Raises :class:`BadBundle` for anything outside *prefix* or unsafe, before
    a single file has been written anywhere.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BadBundle("that is not a zip file") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES:
            raise BadBundle(f"too many files ({len(infos)})")
        out: dict[str, bytes] = {}
        total = 0
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            if "\\" in name or name.startswith("/") or not name.startswith(prefix):
                raise BadBundle(f"unexpected file {name!r}")
            rel = name[len(prefix):]
            parts = rel.split("/")
            if not rel or any(part in ("", ".", "..") for part in parts) or ":" in rel:
                raise BadBundle(f"unexpected file {name!r}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise BadBundle(f"{name!r} is a link")
            if parts[-1] in NEVER_PACKED:
                continue
            total += info.file_size
            if total > MAX_BYTES:
                raise BadBundle("too large")
            content = archive.read(info)
            if len(content) != info.file_size:
                raise BadBundle(f"{name!r} is damaged")
            out[rel] = content
        return out


def write_tree(target: Path, contents: dict[str, bytes]) -> None:
    """Write *contents* under *target*, each file replaced whole."""
    from src.desk import files

    for rel, content in contents.items():
        files.write_bytes(target.joinpath(*rel.split("/")), content)
