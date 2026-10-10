"""Naming rules: dump file names -> OS family / database name, and ADX-safe identifiers."""

from __future__ import annotations

import re
from pathlib import PurePath

from .models import OsFamily
from .unpack import WRAPPER_SUFFIXES

_OS_PREFIXES: dict[str, OsFamily] = {
    "win": OsFamily.WINDOWS,
    "windows": OsFamily.WINDOWS,
    "linux": OsFamily.LINUX,
    "lin": OsFamily.LINUX,
    "osx": OsFamily.MAC,
    "mac": OsFamily.MAC,
    "macos": OsFamily.MAC,
}


class DumpName:
    """Interprets the `<os>_<anything>.<ext>` naming convention used for uploads."""

    def __init__(self, filename: str):
        self.filename = PurePath(filename).name

    @property
    def stem(self) -> str:
        path = PurePath(self.filename)
        while path.suffix.lower() in WRAPPER_SUFFIXES:
            path = path.with_suffix("")
        return path.stem if path.suffix else path.name

    @property
    def os_family(self) -> OsFamily | None:
        prefix = self.stem.split("_", 1)[0].lower()
        return _OS_PREFIXES.get(prefix)

    @property
    def database_name(self) -> str:
        return Identifiers.database(self.stem)


class Identifiers:
    """ADX entity name helpers. Names are kept conservative so they never need escaping in KQL."""

    _NON_ENTITY = re.compile(r"[^A-Za-z0-9_.\-]+")
    _NON_COLUMN = re.compile(r"[^A-Za-z0-9_]+")

    @classmethod
    def database(cls, raw: str) -> str:
        name = cls._NON_ENTITY.sub("_", raw).strip("_.-")
        return (name or "dump")[:200]

    @classmethod
    def table(cls, raw: str) -> str:
        name = cls._NON_COLUMN.sub("_", raw).strip("_")
        if not name:
            name = "table"
        if name[0].isdigit():
            name = f"t_{name}"
        return name[:200]

    @classmethod
    def columns(cls, headers: list[str]) -> list[str]:
        """Clean CSV headers into unique ADX column names.

        Mirrors the original convention (drop spaces and parentheses, so `Offset(V)` -> `OffsetV`
        and `File output` -> `Fileoutput`) so existing workbook queries keep working.
        """
        cleaned: list[str] = []
        seen: dict[str, int] = {}
        for index, header in enumerate(headers):
            name = cls._NON_COLUMN.sub("", header.replace(" ", "")) or f"Column{index + 1}"
            if name[0].isdigit():
                name = f"c_{name}"
            count = seen.get(name.lower(), 0)
            seen[name.lower()] = count + 1
            cleaned.append(name if count == 0 else f"{name}_{count + 1}")
        return cleaned


def hive_table_suffix(file_full_path: str) -> str:
    """`\\SystemRoot\\System32\\Config\\SOFTWARE` -> `SOFTWARE`, `\\??\\C:\\Users\\x\\ntuser.dat` -> `ntuser`."""
    base = file_full_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    base = base.split(".", 1)[0]
    base = re.sub(r"[^A-Za-z0-9_]+", "", base)
    return base or "UnnamedKey"
