"""Shared value objects used across the pipeline."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class OsFamily(str, enum.Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MAC = "mac"


class Tier(enum.IntEnum):
    """Scheduling priority. Lower runs first, so analysts get the core tables early."""

    BOOTSTRAP = 0
    CORE = 1
    DEFAULT = 2
    SLOW = 3


class TaskStatus(str, enum.Enum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class CsvArtifact:
    """A CSV file produced by a task, destined for one ADX table."""

    table: str
    path: Path


@dataclass
class TaskResult:
    name: str
    table: str
    status: TaskStatus
    started: datetime
    finished: datetime
    exit_code: int | None = None
    error: str = ""
    artifacts: list[CsvArtifact] = field(default_factory=list)
    followups: list = field(default_factory=list)  # list[tasks.Task]; untyped to avoid an import cycle
    rows: int = 0

    @property
    def duration_seconds(self) -> float:
        return (self.finished - self.started).total_seconds()

    @classmethod
    def skipped(cls, name: str, table: str, reason: str) -> "TaskResult":
        now = utcnow()
        return cls(name=name, table=table, status=TaskStatus.SKIPPED, started=now, finished=now, error=reason)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
