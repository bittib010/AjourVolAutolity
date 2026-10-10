"""End-to-end pipeline run against tests/fake_vol.py instead of a real image and ADX."""

import csv
import gzip
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from volautolity.catalog import PluginCatalog, PluginKind, PluginSpec
from volautolity.models import OsFamily, TaskStatus, Tier
from volautolity.naming import DumpName
from volautolity.pipeline import DumpPipeline
from volautolity.settings import Settings
from volautolity.sinks import ResultSink

FAKE_VOL = Path(__file__).with_name("fake_vol.py")


class RecordingSink(ResultSink):
    def __init__(self):
        self.tables = {}
        self.functions = {}

    def open(self, dump: DumpName) -> str:
        return dump.database_name

    def ingest(self, normalized):
        rows = []
        for chunk in normalized.chunks:  # read now: the queue deletes staging files after ingest()
            with gzip.open(chunk, "rt", encoding="utf-8") as handle:
                rows += list(csv.reader(handle))
        self.tables[normalized.table] = ([c.name for c in normalized.columns], rows)

    def create_functions(self, functions):
        self.functions.update(functions)


class TestCatalog(PluginCatalog):
    _BOOTSTRAP = {**PluginCatalog._BOOTSTRAP, OsFamily.WINDOWS: PluginSpec("windows.info.Info", "info", Tier.BOOTSTRAP)}
    _PLUGINS = {**PluginCatalog._PLUGINS, OsFamily.WINDOWS: [
        PluginSpec("windows.pslist.PsList", "pslist", Tier.CORE),
        PluginSpec("windows.config.Probe", "probe"),
        PluginSpec("windows.registry.hivelist.HiveList", "registry_hivelist", kind=PluginKind.HIVELIST),
        PluginSpec("windows.Fail", "failing"),
        PluginSpec("windows.yarascan.YaraScan", "yarascan", Tier.SLOW, kind=PluginKind.YARA),
    ]}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.image = self.tmp / "win_case1.raw"
        self.image.write_bytes(b"MZ" * 1024)
        self.settings = Settings(
            work_dir=self.tmp / "work", vol_command=(sys.executable, str(FAKE_VOL)), workers=3,
            plugin_timeout=60, slow_plugin_timeout=60, poll_interval=1, include_slow=True, enable_clamav=False,
            yara_rules=None, plugin_dirs=(), symbol_dirs=(), extensions=("raw",), keep_dumps=True, azure=None,
        )

    def test_full_run(self):
        sink = RecordingSink()
        report = DumpPipeline(self.settings, sink, catalog=TestCatalog()).process(self.image)
        status = {r.table: r.status for r in report.results}

        self.assertEqual(report.database, "win_case1")
        self.assertEqual(report.os_family, OsFamily.WINDOWS)
        self.assertEqual(report.sha256, hashlib.sha256(self.image.read_bytes()).hexdigest())

        # bootstrap ran first and its saved config was handed to every later plugin
        self.assertEqual(status["info"], TaskStatus.OK)
        self.assertEqual(sink.tables["probe"][1], [["0", "True"]])

        # columns cleaned the way the workbook expects; types normalised
        columns, rows = sink.tables["pslist"]
        self.assertEqual(columns, ["TreeDepth", "PID", "Process", "OffsetV", "CreateTime"])
        self.assertEqual(rows[0][4], "2023-04-24T14:41:32.000000Z")
        self.assertEqual(rows[1][4], "")

        # hivelist fans out into one recursive printkey per hive; duplicate hive names are numbered
        printkeys = sorted(t for t in sink.tables if t.startswith("printkey_"))
        self.assertEqual(printkeys, ["printkey_SYSTEM", "printkey_UnnamedKey", "printkey_ntuser", "printkey_ntuser2"])
        self.assertEqual(sink.tables["printkey_SYSTEM"][1][0][2], "0x87c1a248")

        # failures and skips are recorded, not fatal
        self.assertEqual(status["failing"], TaskStatus.FAILED)
        self.assertEqual(status["yarascan"], TaskStatus.SKIPPED)
        runs = {row[1]: row for row in sink.tables["volautolity_runs"][1]}
        self.assertIn("boom", runs["failing"][8])  # retried without config after "Unsatisfied requirement"
        self.assertEqual(runs["pslist"][4], "2")
        image_row = sink.tables["volautolity_image"][1][0]
        self.assertEqual(image_row[:3], ["win_case1.raw", str(self.image.stat().st_size), report.sha256])

        self.assertIn("taskhost_triage", sink.functions)

    def test_only_filter(self):
        sink = RecordingSink()
        DumpPipeline(self.settings, sink, catalog=TestCatalog(), only_tables={"pslist"}).process(self.image)
        self.assertEqual(set(sink.tables), {"info", "pslist", "volautolity_runs", "volautolity_image"})

    def test_unknown_os_tries_bootstraps(self):
        sink = RecordingSink()
        image = self.tmp / "memory.raw"
        image.write_bytes(b"\0" * 64)
        report = DumpPipeline(self.settings, sink, catalog=TestCatalog()).process(image)
        self.assertEqual(report.os_family, OsFamily.WINDOWS)  # fake vol "succeeds" for windows.info


if __name__ == "__main__":
    unittest.main()
