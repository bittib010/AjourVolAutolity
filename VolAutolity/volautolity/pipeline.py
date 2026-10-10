"""Processing of a single memory image, end to end."""

from __future__ import annotations

import csv
import hashlib
import logging
import shutil
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .catalog import PluginCatalog
from .csvnorm import Column, CsvNormalizer
from .models import CsvArtifact, OsFamily, TaskResult, TaskStatus, utcnow
from .naming import DumpName
from .scheduler import TaskScheduler
from .schemas import TableSchemas
from .settings import Settings
from .sinks import ResultSink
from .tasks import RunContext, TaskFactory, VolatilityTask
from .volatility import ProcessRunner, VolatilityCli

log = logging.getLogger(__name__)

STATUS_TABLE = "volautolity_runs"
IMAGE_TABLE = "volautolity_image"
SCRATCH_DIR = "scratch"  # under each image's output dir; never uploaded


class ImageHasher:
    """SHA-256 of the image for chain of custody, computed in the background while Volatility runs."""

    def __init__(self, image: Path):
        self._digest = ""
        self._thread = threading.Thread(target=self._hash, args=(image,), name="sha256", daemon=True)
        self._thread.start()

    def _hash(self, image: Path) -> None:
        digest = hashlib.sha256()
        try:
            with image.open("rb") as handle:
                while chunk := handle.read(8 * 1024 * 1024):
                    digest.update(chunk)
        except OSError as exc:
            log.error("hashing %s failed: %s", image, exc)
            return
        self._digest = digest.hexdigest()

    def result(self) -> str:
        self._thread.join()
        return self._digest


@dataclass
class PipelineReport:
    database: str
    os_family: OsFamily | None
    output_dir: Path
    results: list[TaskResult] = field(default_factory=list)
    sha256: str = ""

    @property
    def succeeded(self) -> bool:
        return self.os_family is not None

    @property
    def failed_tasks(self) -> list[TaskResult]:
        return [r for r in self.results if r.status in (TaskStatus.FAILED, TaskStatus.TIMEOUT)]


class IngestionQueue:
    """Normalises and ingests CSVs in the background while Volatility keeps running."""

    def __init__(self, sink: ResultSink, normalizer: CsvNormalizer, staging_dir: Path, workers: int = 2):
        self.sink = sink
        self.normalizer = normalizer
        self.staging_dir = staging_dir
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ingest")
        self._futures: list[tuple[CsvArtifact, Future]] = []
        self.schemas: dict[str, list[Column]] = {}  # declared table schemas, set once the OS is known

    def submit(self, result: TaskResult) -> None:
        for artifact in result.artifacts:
            self._futures.append((artifact, self._pool.submit(self._ingest, artifact)))

    def _ingest(self, artifact: CsvArtifact) -> int:
        staging = self.staging_dir / artifact.table
        declared = TableSchemas.lookup(self.schemas, artifact.table)
        normalized = self.normalizer.normalize(artifact.path, artifact.table, staging, declared)
        if normalized is None:
            return 0
        try:
            self.sink.ingest(normalized)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return normalized.rows

    def join(self) -> dict[str, tuple[int, str]]:
        """Wait for everything queued so far. Returns table -> (rows, error)."""
        outcome: dict[str, tuple[int, str]] = {}
        for artifact, future in self._futures:
            try:
                outcome[artifact.table] = (future.result(), "")
            except Exception as exc:
                log.exception("ingestion of %s failed", artifact.table)
                outcome[artifact.table] = (0, f"{type(exc).__name__}: {exc}"[:1000])
        self._futures.clear()
        return outcome

    def close(self) -> None:
        self._pool.shutdown(wait=True)


class DumpPipeline:
    def __init__(self, settings: Settings, sink: ResultSink, catalog: PluginCatalog | None = None,
                 stop_event: threading.Event | None = None, only_tables: set[str] | None = None,
                 schemas: TableSchemas | None = None):
        self.settings = settings
        self.sink = sink
        self.catalog = catalog or PluginCatalog()
        self.stop_event = stop_event or threading.Event()
        self.only_tables = only_tables
        self.factory = TaskFactory(settings)
        self.schemas = schemas or TableSchemas()

    def process(self, image: Path, original_name: str | None = None, os_override: OsFamily | None = None) -> PipelineReport:
        dump = DumpName(original_name or image.name)
        database = self.sink.open(dump)
        output_dir = self.settings.work_dir / "output" / database
        ctx = RunContext(
            settings=self.settings,
            cli=VolatilityCli(self.settings.vol_command, image, self.settings.work_dir / "cache",
                              self.settings.plugin_dirs, self.settings.symbol_dirs, self.settings.remote_isf_url),
            runner=ProcessRunner(),
            csv_dir=output_dir / "csv",
            files_dir=output_dir / "files",
            logs_dir=output_dir / "logs",
            scratch_dir=output_dir / SCRATCH_DIR,
        )
        ingestion = IngestionQueue(self.sink, CsvNormalizer(), output_dir / SCRATCH_DIR / "staging")
        report = PipelineReport(database=database, os_family=None, output_dir=output_dir)
        log.info("processing %s into database %s", dump.filename, database)
        started = utcnow()
        hasher = ImageHasher(image)
        try:
            report.os_family, bootstrap = self._bootstrap(ctx, dump, os_override, report)
            self._prepare_database(report.os_family, ingestion)
            if bootstrap is not None:
                ingestion.submit(bootstrap)
            if report.os_family is None:
                log.error("%s: no OS profile could be resolved; skipping remaining plugins", dump.filename)
                diagnostics = VolatilityTask(self.catalog.diagnostics()).run(ctx)
                report.results.append(diagnostics)
                ingestion.submit(diagnostics)
            else:
                tasks, skipped = self.factory.build(self._selected(self.catalog.plugins(report.os_family)))
                report.results += skipped
                scheduler = TaskScheduler(self.settings.workers, on_result=ingestion.submit, stop_event=self.stop_event)
                report.results += scheduler.run(tasks, ctx)
            ingested = ingestion.join()
            report.sha256 = hasher.result()
            self._write_summaries(report, dump, image, started, ingested, ctx, ingestion)
        finally:
            ingestion.close()
        log.info("%s finished: %d tasks, %d failed/timed out", dump.filename, len(report.results), len(report.failed_tasks))
        return report

    def _bootstrap(self, ctx: RunContext, dump: DumpName, os_override: OsFamily | None,
                   report: PipelineReport) -> tuple[OsFamily | None, TaskResult | None]:
        """Run the OS's bootstrap plugin. Without an OS prefix in the file name, try each OS in turn."""
        candidates = [os_override or dump.os_family] if (os_override or dump.os_family) else list(OsFamily)
        for os_family in candidates:
            result = self.factory.bootstrap(self.catalog.bootstrap(os_family)).run(ctx)
            report.results.append(result)
            if result.status is TaskStatus.OK:
                return os_family, result
            log.warning("%s bootstrap (%s) failed: %s", os_family.value, result.name, result.error[-300:])
        return None, None

    def _prepare_database(self, os_family: OsFamily | None, ingestion: IngestionQueue) -> None:
        """Create every table (empty, with declared types) and the helper functions before any data
        arrives, so the workbook can query tables of plugins that fail or are still running."""
        tables = self.schemas.for_os(os_family)
        ingestion.schemas = tables
        self.sink.create_tables({name: columns for name, columns in tables.items() if not name.endswith("*")})
        if os_family is not None:
            self.sink.create_functions(self.catalog.functions(os_family))

    def _selected(self, specs):
        if not self.only_tables:
            return specs
        return [s for s in specs if s.table in self.only_tables]

    def _write_summaries(self, report: PipelineReport, dump: DumpName, image: Path, started,
                         ingested: dict[str, tuple[int, str]], ctx: RunContext, ingestion: IngestionQueue) -> None:
        """volautolity_runs: one row per task, so analysts can see which tables are missing or incomplete and why.
        volautolity_image: what was analysed (name, size, SHA-256) for chain of custody."""
        runs = ctx.csv_dir / f"{STATUS_TABLE}.csv"
        with runs.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Plugin", "Table", "Status", "ExitCode", "Rows", "StartedUtc", "FinishedUtc",
                             "DurationSeconds", "Error", "IngestError"])
            for r in report.results:
                rows, ingest_error = ingested.get(r.table, (r.rows, ""))
                r.rows = rows
                writer.writerow([r.name, r.table, r.status.value, "" if r.exit_code is None else r.exit_code, rows,
                                 _timestamp(r.started), _timestamp(r.finished), f"{r.duration_seconds:.1f}",
                                 r.error.replace("\n", " | "), ingest_error])

        info = ctx.csv_dir / f"{IMAGE_TABLE}.csv"
        with info.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ImageName", "SizeBytes", "Sha256", "OsFamily", "Database", "StartedUtc", "FinishedUtc",
                             "Tasks", "FailedTasks", "VolAutolityVersion"])
            writer.writerow([dump.filename, image.stat().st_size, report.sha256,
                             report.os_family.value if report.os_family else "", report.database,
                             _timestamp(started), _timestamp(utcnow()), len(report.results), len(report.failed_tasks),
                             __version__])

        now = utcnow()
        ingestion.submit(TaskResult("summary", STATUS_TABLE, TaskStatus.OK, now, now,
                                    artifacts=[CsvArtifact(STATUS_TABLE, runs), CsvArtifact(IMAGE_TABLE, info)]))
        ingestion.join()


def _timestamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")
