"""Where normalised results go. ADX in production; nowhere (CSV files only) for local runs."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .csvnorm import Column, NormalizedCsv
from .naming import DumpName

log = logging.getLogger(__name__)


class ResultSink(ABC):
    @abstractmethod
    def open(self, dump: DumpName) -> str:
        """Prepare a destination for one image and return the database name used."""

    @abstractmethod
    def ingest(self, normalized: NormalizedCsv) -> None: ...

    def create_tables(self, tables: dict[str, list[Column]]) -> None:
        """Create empty tables with their declared schema (before any data arrives)."""

    def create_functions(self, functions: dict[str, str]) -> None:
        """Create/replace stored KQL functions (derived views such as taskhost_triage)."""


class LocalSink(ResultSink):
    """Keeps results on disk only. Useful for testing plugins without an ADX cluster."""

    def open(self, dump: DumpName) -> str:
        return dump.database_name

    def ingest(self, normalized: NormalizedCsv) -> None:
        log.info("local: %s has %d rows (%d columns), not ingesting", normalized.table, normalized.rows, len(normalized.columns))
