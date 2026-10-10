"""Units of work for one memory image.

Every task produces zero or more CSV artifacts (one per ADX table) and may return follow-up tasks
that depend on its output (hivelist -> printkey per hive, dumpfiles -> ClamAV). That keeps the
scheduler a simple priority queue while still expressing those dependencies.
"""

from __future__ import annotations

import csv
import logging
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .catalog import PluginKind, PluginSpec
from .models import CsvArtifact, TaskResult, TaskStatus, Tier, utcnow
from .naming import hive_table_suffix
from .settings import Settings
from .volatility import ProcessOutcome, ProcessRunner, VolatilityCli

log = logging.getLogger(__name__)

_CONFIG_PROBLEM = re.compile(r"Unsatisfied requirement|unable to validate the plugin requirements", re.IGNORECASE)


@dataclass
class RunContext:
    settings: Settings
    cli: VolatilityCli
    runner: ProcessRunner
    csv_dir: Path
    files_dir: Path
    logs_dir: Path
    scratch_dir: Path  # intermediate files that are neither results nor uploaded

    def __post_init__(self) -> None:
        for directory in (self.csv_dir, self.files_dir, self.logs_dir, self.scratch_dir):
            directory.mkdir(parents=True, exist_ok=True)


class Task(ABC):
    def __init__(self, name: str, table: str, tier: Tier):
        self.name = name
        self.table = table
        self.tier = tier

    @abstractmethod
    def run(self, ctx: RunContext) -> TaskResult: ...

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r} -> {self.table!r})"


class VolatilityTask(Task):
    """Runs one Volatility plugin and captures its CSV output."""

    dumps_files = False

    def __init__(self, spec: PluginSpec, table: str | None = None, extra_args: tuple[str, ...] = ()):
        super().__init__(spec.name, table or spec.table, spec.tier)
        self.spec = spec
        self.extra_args = extra_args

    def args(self, ctx: RunContext) -> tuple[str, ...]:
        return (*self.spec.args, *self.extra_args)

    def output_dir(self, ctx: RunContext) -> Path | None:
        if not (self.dumps_files or self.spec.writes_files):
            return None
        directory = ctx.files_dir / self.table
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def timeout(self, ctx: RunContext) -> int:
        if self.spec.timeout:
            return self.spec.timeout
        return ctx.settings.slow_plugin_timeout if self.tier is Tier.SLOW else ctx.settings.plugin_timeout

    def run(self, ctx: RunContext) -> TaskResult:
        started = utcnow()
        csv_path = ctx.csv_dir / f"{self.table}.csv"
        outcome = self._invoke(ctx, csv_path, use_config=True)
        if not outcome.ok and ctx.cli.config_file and _CONFIG_PROBLEM.search(outcome.stderr_tail):
            log.warning("%s rejected the saved config, retrying with full automagic", self.name)
            outcome = self._invoke(ctx, csv_path, use_config=False)

        result = TaskResult(
            name=self.name,
            table=self.table,
            status=_status(outcome),
            started=started,
            finished=utcnow(),
            exit_code=outcome.exit_code,
            error="" if outcome.ok else outcome.stderr_tail[-1000:],
        )
        # Keep partial output from failed/timed-out runs: some rows beat no rows during triage,
        # and the run status table tells the analyst the table may be incomplete.
        if csv_path.exists() and csv_path.stat().st_size > 0:
            result.artifacts.append(CsvArtifact(self.table, csv_path))
        if outcome.ok:
            result.followups = self.followups(ctx, csv_path)
        return result

    def followups(self, ctx: RunContext, csv_path: Path) -> list[Task]:
        return []

    def _invoke(self, ctx: RunContext, csv_path: Path, use_config: bool, save_config: Path | None = None) -> ProcessOutcome:
        cmd = ctx.cli.build(
            self.name,
            self.args(ctx),
            output_dir=self.output_dir(ctx),
            log_file=ctx.logs_dir / f"{self.table}.log",
            save_config=save_config,
            use_config=use_config,
        )
        nice = 10 if self.tier is Tier.SLOW else 0
        # cwd inside the image's output tree: anything a plugin writes relative to it stays there.
        return ctx.runner.run(cmd, csv_path, ctx.logs_dir / f"{self.table}.stderr", self.timeout(ctx),
                              nice=nice, cwd=ctx.files_dir)


class BootstrapTask(VolatilityTask):
    """First plugin for an image. Saves the resolved layer/symbol configuration for every later plugin."""

    def run(self, ctx: RunContext) -> TaskResult:
        started = utcnow()
        csv_path = ctx.csv_dir / f"{self.table}.csv"
        config_path = ctx.logs_dir / "volatility-config.json"
        config_path.unlink(missing_ok=True)  # vol refuses to overwrite it, and bootstrap may run once per OS candidate
        ctx.cli.config_file = None
        outcome = self._invoke(ctx, csv_path, use_config=False, save_config=config_path)
        result = TaskResult(
            name=self.name,
            table=self.table,
            status=_status(outcome),
            started=started,
            finished=utcnow(),
            exit_code=outcome.exit_code,
            error="" if outcome.ok else outcome.stderr_tail[-1000:],
        )
        if outcome.ok:
            if config_path.exists():
                ctx.cli.config_file = config_path
            result.artifacts.append(CsvArtifact(self.table, csv_path))
        return result


class StringsTask(VolatilityTask):
    """GNU strings (ASCII + UTF-16LE) over the image, then windows.strings maps them to processes."""

    def args(self, ctx: RunContext) -> tuple[str, ...]:
        return (*super().args(ctx), "--strings-file", str(self._strings_file(ctx)))

    def run(self, ctx: RunContext) -> TaskResult:
        strings_file = self._strings_file(ctx)
        started = utcnow()
        try:
            with strings_file.open("wb") as out:
                for encoding_args in ((), ("-el",)):  # the old script overwrote the ASCII pass with the UTF-16 pass
                    subprocess.run(
                        ["strings", "-a", "-td", *encoding_args, str(ctx.cli.image)],
                        stdout=out,
                        stderr=subprocess.DEVNULL,
                        check=True,
                        timeout=self.timeout(ctx),
                    )
        except (OSError, subprocess.SubprocessError) as exc:
            strings_file.unlink(missing_ok=True)
            return TaskResult(self.name, self.table, TaskStatus.FAILED, started, utcnow(), error=f"strings pre-pass failed: {exc}")
        try:
            return super().run(ctx)
        finally:
            strings_file.unlink(missing_ok=True)  # can be several GB

    def _strings_file(self, ctx: RunContext) -> Path:
        return ctx.scratch_dir / "strings.txt"


class HiveListTask(VolatilityTask):
    """Lists (and dumps) registry hives, then schedules a recursive printkey per hive."""

    dumps_files = True

    def args(self, ctx: RunContext) -> tuple[str, ...]:
        return (*super().args(ctx), "--dump")

    def followups(self, ctx: RunContext, csv_path: Path) -> list[Task]:
        tasks: list[Task] = []
        counts: dict[str, int] = {}
        printkey = PluginSpec("windows.registry.printkey.PrintKey", "registry_printkey", tier=Tier.DEFAULT)
        for offset, full_path in _read_columns(csv_path, "Offset", "FileFullPath"):
            if not offset:
                continue
            suffix = hive_table_suffix(full_path)
            counts[suffix] = counts.get(suffix, 0) + 1
            if counts[suffix] > 1:
                suffix = f"{suffix}{counts[suffix]}"
            tasks.append(VolatilityTask(printkey, table=f"printkey_{suffix}", extra_args=("--offset", offset, "--recurse")))
        return tasks


class DumpFilesTask(VolatilityTask):
    """Dumps cached files in one pass (the old script ran the plugin twice) and queues a ClamAV scan."""

    dumps_files = True

    def followups(self, ctx: RunContext, csv_path: Path) -> list[Task]:
        directory = ctx.files_dir / self.table
        if ctx.settings.enable_clamav and directory.exists() and any(directory.iterdir()):
            return [ClamScanTask(directory)]
        return []


class YaraTask(VolatilityTask):
    def args(self, ctx: RunContext) -> tuple[str, ...]:
        return (*super().args(ctx), "--yara-file", str(ctx.settings.yara_rules))


class ClamScanTask(Task):
    def __init__(self, directory: Path):
        super().__init__("clamscan", "clamscan", Tier.SLOW)
        self.directory = directory

    def run(self, ctx: RunContext) -> TaskResult:
        started = utcnow()
        if shutil.which("clamscan") is None:
            return TaskResult.skipped(self.name, self.table, "clamscan is not installed")
        raw = ctx.logs_dir / "clamscan.txt"
        outcome = ctx.runner.run(
            ["clamscan", "-r", "--no-summary", str(self.directory)],
            raw,
            ctx.logs_dir / "clamscan.stderr",
            ctx.settings.slow_plugin_timeout,
            nice=10,
        )
        # clamscan: 0 = clean, 1 = something found, 2 = some errors (still has per-file results)
        status = TaskStatus.TIMEOUT if outcome.timed_out else (TaskStatus.OK if outcome.exit_code in (0, 1) else TaskStatus.FAILED)
        csv_path = ctx.csv_dir / "clamscan.csv"
        rows = ClamScanParser.to_csv(raw, csv_path)
        result = TaskResult(self.name, self.table, status, started, utcnow(), exit_code=outcome.exit_code, rows=rows)
        if status is not TaskStatus.OK:
            result.error = outcome.stderr_tail[-1000:]
        if rows:
            result.artifacts.append(CsvArtifact(self.table, csv_path))
        return result


class ClamScanParser:
    """`/path/file.dat: OK` | `/path/file.dat: Win.Trojan.X-1 FOUND` | `/path/x: Empty file`."""

    @staticmethod
    def parse_line(line: str) -> tuple[str, str, str] | None:
        line = line.rstrip("\r\n")
        if ": " not in line:
            return None
        path, verdict = line.rsplit(": ", 1)
        if verdict.endswith(" FOUND"):
            return path, "FOUND", verdict[: -len(" FOUND")]
        if verdict == "OK":
            return path, "OK", ""
        if verdict.endswith("ERROR"):
            return path, "ERROR", verdict[: -len("ERROR")].strip()
        return path, "OTHER", verdict

    @classmethod
    def to_csv(cls, raw: Path, csv_path: Path) -> int:
        if not raw.exists():
            return 0
        rows = 0
        with raw.open("r", encoding="utf-8", errors="replace") as src, csv_path.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.writer(dst)
            writer.writerow(["File", "DumpedFile", "Result", "Signature"])
            for line in src:
                parsed = cls.parse_line(line)
                if parsed:
                    path, result, signature = parsed
                    writer.writerow([path, Path(path).name, result, signature])
                    rows += 1
        return rows


class TaskFactory:
    _CLASSES: dict[PluginKind, type[VolatilityTask]] = {
        PluginKind.PLUGIN: VolatilityTask,
        PluginKind.STRINGS: StringsTask,
        PluginKind.HIVELIST: HiveListTask,
        PluginKind.DUMPFILES: DumpFilesTask,
        PluginKind.YARA: YaraTask,
    }

    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, specs: list[PluginSpec]) -> tuple[list[Task], list[TaskResult]]:
        """Returns (tasks to run, results for tasks skipped by configuration)."""
        tasks: list[Task] = []
        skipped: list[TaskResult] = []
        for spec in specs:
            reason = self._skip_reason(spec)
            if reason:
                skipped.append(TaskResult.skipped(spec.name, spec.table, reason))
                continue
            tasks.append(self._CLASSES[spec.kind](spec))
        return tasks, skipped

    def bootstrap(self, spec: PluginSpec) -> BootstrapTask:
        return BootstrapTask(spec)

    def _skip_reason(self, spec: PluginSpec) -> str:
        if spec.tier is Tier.SLOW and not self.settings.include_slow:
            return "slow plugins disabled (INCLUDE_SLOW_PLUGINS=false)"
        if spec.kind is PluginKind.YARA and not (self.settings.yara_rules and self.settings.yara_rules.exists()):
            return "no YARA rules configured (YARA_RULES_FILE)"
        if spec.kind is PluginKind.STRINGS and shutil.which("strings") is None:
            return "GNU strings (binutils) is not installed"
        return ""


def _status(outcome: ProcessOutcome) -> TaskStatus:
    if outcome.timed_out:
        return TaskStatus.TIMEOUT
    return TaskStatus.OK if outcome.exit_code == 0 else TaskStatus.FAILED


def _read_columns(csv_path: Path, *wanted: str):
    """Yield the wanted columns from a Volatility CSV, matching headers loosely (`Offset(V)` == `OffsetV`)."""
    def key(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        header = next((row for row in reader if row and row[0].strip() == "TreeDepth"), None)
        if header is None:
            return
        positions = {key(name): index for index, name in enumerate(header)}
        indexes = [positions.get(key(name)) for name in wanted]
        for row in reader:
            yield tuple(row[i].strip() if i is not None and i < len(row) else "" for i in indexes)
