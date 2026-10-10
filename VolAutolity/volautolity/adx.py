"""Azure Data Explorer sink.

Authenticates with the VM's managed identity (no service principal secret on disk or on the
command line), creates one database per image through ARM, creates tables from the CSV headers
and queues ingestion with an explicit ordinal CSV mapping.
"""

from __future__ import annotations

import logging
import threading

from azure.core.exceptions import ResourceNotFoundError
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.data_format import DataFormat, IngestionMappingKind
from azure.kusto.ingest import ColumnMapping, FileDescriptor, IngestionProperties, QueuedIngestClient, ReportLevel
from azure.mgmt.kusto import KustoManagementClient
from azure.mgmt.kusto.models import ReadWriteDatabase

from .csvnorm import Column, ColumnType, NormalizedCsv
from .models import utcnow
from .naming import DumpName
from .settings import AzureSettings
from .sinks import ResultSink

log = logging.getLogger(__name__)


class AdxSink(ResultSink):
    def __init__(self, azure: AzureSettings, credential, batching_seconds: int = 20):
        self.azure = azure
        self.batching_seconds = batching_seconds
        self._query = KustoClient(KustoConnectionStringBuilder.with_azure_token_credential(azure.cluster_uri, credential))
        self._ingest = QueuedIngestClient(KustoConnectionStringBuilder.with_azure_token_credential(azure.cluster_ingest_uri, credential))
        self._arm = KustoManagementClient(credential, azure.subscription_id)
        self._lock = threading.Lock()
        self._tables: dict[str, dict[str, ColumnType]] = {}
        self.database: str | None = None

    # -- database ------------------------------------------------------------------------------

    def open(self, dump: DumpName) -> str:
        name = self._unused_database_name(dump.database_name)
        log.info("creating ADX database %s", name)
        self._arm.databases.begin_create_or_update(
            self.azure.resource_group,
            self.azure.cluster_name,
            name,
            ReadWriteDatabase(location=self.azure.location),
        ).result()
        self.database = name
        self._tables = {}
        # Queued ingestion batches for up to 5 minutes by default; results should show up quickly.
        self._mgmt(
            f".alter database ['{name}'] policy ingestionbatching "
            f"'{{\"MaximumBatchingTimeSpan\":\"00:00:{self.batching_seconds:02d}\",\"MaximumNumberOfItems\":500,\"MaximumRawDataSizeMB\":1024}}'"
        )
        return name

    def _unused_database_name(self, base: str) -> str:
        """Re-uploading an image with the same name gets a fresh database instead of duplicate rows."""
        try:
            self._arm.databases.get(self.azure.resource_group, self.azure.cluster_name, base)
        except ResourceNotFoundError:
            return base
        return f"{base}_{utcnow():%Y%m%d%H%M%S}"

    # -- tables & ingestion -------------------------------------------------------------------

    def ingest(self, normalized: NormalizedCsv) -> None:
        columns = self._ensure_table(normalized.table, normalized.columns)
        if normalized.rows == 0:
            return
        properties = IngestionProperties(
            database=self.database,
            table=normalized.table,
            data_format=DataFormat.CSV,
            column_mappings=[ColumnMapping(column_name=c.name, column_type=c.type.value, ordinal=i) for i, c in enumerate(columns)],
            ingestion_mapping_kind=IngestionMappingKind.CSV,
            report_level=ReportLevel.FailuresOnly,
        )
        per_chunk = max(1, normalized.raw_bytes // max(1, len(normalized.chunks)))
        for chunk in normalized.chunks:
            self._ingest.ingest_from_file(FileDescriptor(str(chunk), per_chunk), ingestion_properties=properties)
        log.info("queued %s: %d rows in %d chunk(s)", normalized.table, normalized.rows, len(normalized.chunks))

    def _ensure_table(self, table: str, columns: list[Column]) -> list[Column]:
        """Create the table or add missing columns. Returns the columns typed as they exist in ADX."""
        with self._lock:
            existing = self._tables.get(table)
            if existing is None:
                self._mgmt(f".create-merge table ['{table}'] ({_schema(columns)})")
                self._tables[table] = {c.name: c.type for c in columns}
                return columns
            missing = [c for c in columns if c.name not in existing]
            if missing:
                self._mgmt(f".alter-merge table ['{table}'] ({_schema(missing)})")
                existing.update({c.name: c.type for c in missing})
            conflicts = [c.name for c in columns if existing[c.name] is not c.type]
            if conflicts:
                log.warning("%s: keeping existing ADX types for %s", table, ", ".join(conflicts))
            return [Column(c.name, existing[c.name]) for c in columns]

    def create_functions(self, functions: dict[str, str]) -> None:
        for name, body in functions.items():
            self._mgmt(
                f".create-or-alter function with (folder='VolAutolity', skipvalidation='true') {name}() {{ {body} }}"
            )

    def _mgmt(self, command: str):
        return self._query.execute_mgmt(self.database or "NetDefaultDB", command)


def _schema(columns: list[Column]) -> str:
    return ", ".join(f"['{c.name}']:{c.type.value}" for c in columns)
