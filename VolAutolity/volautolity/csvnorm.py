"""Normalise Volatility CSV output for ADX ingestion.

Instead of maintaining a hand-written schema per plugin (which silently drifts whenever Volatility
adds or renames a column), the schema is derived from each CSV's header and the column types are
inferred from the data. The normalised rows are written as headerless, gzip-compressed chunks and
ingested with an explicit ordinal mapping, so a changed column order can never shift data into the
wrong column.
"""

from __future__ import annotations

import csv
import enum
import gzip
import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .naming import Identifiers

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))  # malfind/strings rows can be very wide

_NULL_TOKENS = {"", "N/A", "-"}
_INT_RE = re.compile(r"^-?\d{1,19}$")
_REAL_RE = re.compile(r"^-?\d+\.\d+$")
_DATETIME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*(?P<tz>UTC|Z|[+-]\d{2}:?\d{2})?\s*$"
)
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1


class ColumnType(str, enum.Enum):
    STRING = "string"
    LONG = "long"
    REAL = "real"
    DATETIME = "datetime"


@dataclass(frozen=True)
class Column:
    name: str
    type: ColumnType


@dataclass
class NormalizedCsv:
    table: str
    columns: list[Column]
    chunks: list[Path] = field(default_factory=list)
    rows: int = 0
    raw_bytes: int = 0


class _ColumnTypeInferrer:
    """Narrows a column's type as values are observed. Starts optimistic, falls back to string."""

    def __init__(self) -> None:
        self.candidates = {ColumnType.LONG, ColumnType.REAL, ColumnType.DATETIME}
        self.saw_value = False

    def observe(self, value: str) -> None:
        if not self.candidates:
            return
        value = value.strip()
        if value in _NULL_TOKENS:
            return
        self.saw_value = True
        if ColumnType.LONG in self.candidates and not _is_int64(value):
            self.candidates.discard(ColumnType.LONG)
        if ColumnType.REAL in self.candidates and not (_is_int64(value) or _REAL_RE.match(value)):
            self.candidates.discard(ColumnType.REAL)
        if ColumnType.DATETIME in self.candidates and not _DATETIME_RE.match(value):
            self.candidates.discard(ColumnType.DATETIME)

    @property
    def result(self) -> ColumnType:
        if not self.saw_value:
            return ColumnType.STRING
        for preferred in (ColumnType.LONG, ColumnType.REAL, ColumnType.DATETIME):
            if preferred in self.candidates:
                return preferred
        return ColumnType.STRING


def _is_int64(value: str) -> bool:
    return bool(_INT_RE.match(value)) and _INT64_MIN <= int(value) <= _INT64_MAX


def _normalize_datetime(value: str) -> str:
    match = _DATETIME_RE.match(value)
    if not match:
        return value
    tz = match.group("tz")
    suffix = "Z" if tz in (None, "UTC", "Z") else tz
    return f"{match.group('date')}T{match.group('time')}{suffix}"


class CsvNormalizer:
    """Two passes over the source file: infer types, then write typed, headerless gzip chunks."""

    HEADER_SCAN_LINES = 5

    def __init__(self, chunk_bytes: int = 512 * 1024 * 1024):
        self.chunk_bytes = chunk_bytes

    def normalize(self, source: Path, table: str, dest_dir: Path) -> NormalizedCsv | None:
        """Returns None when the file has no header (plugin produced nothing usable)."""
        header_index, header = self._find_header(source)
        if header is None:
            return None

        names = Identifiers.columns(header)
        inferrers = [_ColumnTypeInferrer() for _ in names]
        for row in self._rows(source, header_index):
            for inferrer, value in zip(inferrers, row):
                inferrer.observe(value)
        columns = [Column(name, inferrer.result) for name, inferrer in zip(names, inferrers)]

        result = NormalizedCsv(table=table, columns=columns)
        dest_dir.mkdir(parents=True, exist_ok=True)
        writer = _ChunkWriter(dest_dir, table, self.chunk_bytes)
        try:
            for row in self._rows(source, header_index):
                writer.write(self._convert(row, columns))
                result.rows += 1
        finally:
            writer.close()
        result.chunks = writer.paths
        result.raw_bytes = writer.total_bytes
        return result

    def _find_header(self, source: Path) -> tuple[int, list[str] | None]:
        """Volatility CSV always starts with `TreeDepth`; skip any banner lines that precede it."""
        with source.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            first: tuple[int, list[str]] | None = None
            for index, row in enumerate(reader):
                if index >= self.HEADER_SCAN_LINES:
                    break
                if not row:
                    continue
                if first is None:
                    first = (index, row)
                if row[0].strip() == "TreeDepth":
                    return index, row
        return first if first else (0, None)

    @staticmethod
    def _rows(source: Path, header_index: int):
        with source.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            for index, row in enumerate(reader):
                if index <= header_index or not row:
                    continue
                yield row

    @staticmethod
    def _convert(row: list[str], columns: list[Column]) -> list[str]:
        out: list[str] = []
        for index, column in enumerate(columns):
            value = row[index] if index < len(row) else ""
            if column.type is ColumnType.STRING:
                out.append(value)
                continue
            value = value.strip()
            if value in _NULL_TOKENS:
                out.append("")
            elif column.type is ColumnType.DATETIME:
                out.append(_normalize_datetime(value))
            else:
                out.append(value)
        if len(row) > len(columns):  # ragged row: keep the overflow in the last column rather than dropping it
            out[-1] = ",".join([out[-1], *row[len(columns):]])
        return out


class _ChunkWriter:
    def __init__(self, directory: Path, table: str, chunk_bytes: int):
        self.directory = directory
        self.table = table
        self.chunk_bytes = chunk_bytes
        self.paths: list[Path] = []
        self.total_bytes = 0
        self._current_bytes = 0
        self._handle: io.TextIOWrapper | None = None
        self._buffer = io.StringIO()
        self._csv = csv.writer(self._buffer)

    def write(self, row: list[str]) -> None:
        if self._handle is None or self._current_bytes >= self.chunk_bytes:
            self._rotate()
        self._buffer.seek(0)
        self._buffer.truncate()
        self._csv.writerow(row)
        line = self._buffer.getvalue()
        self._handle.write(line)
        self._current_bytes += len(line)  # character count is close enough for chunking and size hints
        self.total_bytes += len(line)

    def _rotate(self) -> None:
        self.close()
        path = self.directory / f"{self.table}.{len(self.paths):03d}.csv.gz"
        self._handle = io.TextIOWrapper(gzip.open(path, "wb", compresslevel=5), encoding="utf-8", newline="")
        self.paths.append(path)
        self._current_bytes = 0

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
