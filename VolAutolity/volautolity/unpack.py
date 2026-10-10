"""Compressed uploads (`win_host.raw.gz`, `win_host.zip`). Memory images typically compress 3-5x,
which matters far more for upload time than anything that happens on the worker."""

from __future__ import annotations

import gzip
import logging
import shutil
import zipfile
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

WRAPPER_SUFFIXES = (".gz", ".zip")
_BUFFER = 16 * 1024 * 1024


class ImageUnpacker:
    @staticmethod
    def is_wrapped(name: str) -> bool:
        return PurePosixPath(name).suffix.lower() in WRAPPER_SUFFIXES

    @staticmethod
    def inner_name(name: str) -> str:
        """`win_host.raw.gz` -> `win_host.raw`; `win_host.zip` -> `win_host` (member name is not trusted)."""
        path = PurePosixPath(name)
        return path.stem if path.suffix.lower() in WRAPPER_SUFFIXES else path.name

    def unpack(self, archive: Path) -> Path:
        """Decompress next to the archive and delete the archive. Never uses member paths from the archive."""
        target = archive.with_name(self.inner_name(archive.name))
        if target == archive:
            raise ValueError(f"not a compressed image: {archive}")
        log.info("decompressing %s", archive.name)
        if archive.suffix.lower() == ".gz":
            with gzip.open(archive, "rb") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, _BUFFER)
        else:
            with zipfile.ZipFile(archive) as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                if not members:
                    raise ValueError(f"{archive.name} is empty")
                largest = max(members, key=lambda m: m.file_size)  # the image; ignore readme/hash files
                with zf.open(largest) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, _BUFFER)
        archive.unlink()
        return target
