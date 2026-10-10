import csv
import gzip
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from volautolity.csvnorm import ColumnType, CsvNormalizer
from volautolity.models import OsFamily, TaskResult, TaskStatus, Tier, utcnow
from volautolity.naming import DumpName, Identifiers, hive_table_suffix
from volautolity.scheduler import TaskScheduler
from volautolity.tasks import ClamScanParser, Task
from volautolity.unpack import ImageUnpacker
from volautolity.volatility import VolatilityCli


class NamingTests(unittest.TestCase):
    def test_os_and_database_from_file_name(self):
        name = DumpName("inbox/win_myCompany 13.02.24.vmem")
        self.assertEqual(name.os_family, OsFamily.WINDOWS)
        self.assertEqual(name.database_name, "win_myCompany_13.02.24")
        self.assertEqual(DumpName("linux_box.lime").os_family, OsFamily.LINUX)
        self.assertEqual(DumpName("osx_mbp.raw").os_family, OsFamily.MAC)
        self.assertIsNone(DumpName("memory.raw").os_family)

    def test_columns_keep_the_original_convention_and_are_unique(self):
        self.assertEqual(
            Identifiers.columns(["TreeDepth", "Offset(V)", "File output", "Offset V", "1st", ""]),
            ["TreeDepth", "OffsetV", "Fileoutput", "OffsetV_2", "c_1st", "Column6"],
        )

    def test_table_names_are_safe(self):
        self.assertEqual(Identifiers.table("printkey_ntuser"), "printkey_ntuser")
        self.assertEqual(Identifiers.table("x'; .drop"), "x_drop")

    def test_hive_suffix(self):
        self.assertEqual(hive_table_suffix("\\SystemRoot\\System32\\Config\\SOFTWARE"), "SOFTWARE")
        self.assertEqual(hive_table_suffix("\\??\\C:\\Users\\x\\ntuser.dat"), "ntuser")
        self.assertEqual(hive_table_suffix(""), "UnnamedKey")


class CsvNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _normalize(self, text, chunk_bytes=1 << 20):
        source = self.tmp / "in.csv"
        source.write_text(text, encoding="utf-8")
        return CsvNormalizer(chunk_bytes).normalize(source, "t", self.tmp / "out")

    def _rows(self, result):
        lines = []
        for chunk in result.chunks:
            with gzip.open(chunk, "rt", encoding="utf-8") as handle:
                lines += handle.read().splitlines()
        return lines

    def test_types_are_inferred_and_values_normalised(self):
        result = self._normalize(
            "Volatility 3 Framework 2.28.2\n"
            "TreeDepth,PID,Offset(V),CreateTime,Ratio,Name\n"
            "0,4,0x8413a920,2023-04-24 14:41:32.000000 ,1.5,System\n"
            "0,N/A,0x8adb0330,2023-04-24 14:41:33.000000 UTC,2,N/A\n"
        )
        types = {c.name: c.type for c in result.columns}
        self.assertEqual(types, {
            "TreeDepth": ColumnType.LONG, "PID": ColumnType.LONG, "OffsetV": ColumnType.STRING,
            "CreateTime": ColumnType.DATETIME, "Ratio": ColumnType.REAL, "Name": ColumnType.STRING,
        })
        self.assertEqual(self._rows(result), [
            "0,4,0x8413a920,2023-04-24T14:41:32.000000Z,1.5,System",
            "0,,0x8adb0330,2023-04-24T14:41:33.000000Z,2,N/A",  # N/A kept in string columns only
        ])

    def test_volatility_backslash_escaping_is_decoded(self):
        # Volatility's csv.DictWriter(escapechar="\\") doubles backslashes; our own CSVs don't escape.
        result = self._normalize('TreeDepth,Path,Note\n0,\\\\Device\\\\HarddiskVolume2\\\\Windows,"say ""hi"""\n')
        with gzip.open(result.chunks[0], "rt", encoding="utf-8") as handle:
            row = next(csv.reader(handle))
        self.assertEqual(row, ["0", "\\Device\\HarddiskVolume2\\Windows", 'say "hi"'])
        plain = self._normalize("File,Result\nC:\\x\\y,OK\n")
        self.assertEqual(self._rows(plain), ["C:\\x\\y,OK"])

    def test_values_beyond_int64_stay_strings(self):
        result = self._normalize("TreeDepth,Big\n0,18446744073709551615\n")
        self.assertEqual(result.columns[1].type, ColumnType.STRING)

    def test_header_only_file_yields_empty_table(self):
        result = self._normalize("TreeDepth,PID\n")
        self.assertEqual((result.rows, result.chunks), (0, []))
        self.assertEqual([c.name for c in result.columns], ["TreeDepth", "PID"])

    def test_empty_file_yields_nothing(self):
        self.assertIsNone(self._normalize(""))

    def test_output_is_chunked(self):
        body = "".join(f"0,{i},{'x' * 50}\n" for i in range(100))
        result = self._normalize("TreeDepth,PID,Name\n" + body, chunk_bytes=1000)
        self.assertGreater(len(result.chunks), 1)
        self.assertEqual(len(self._rows(result)), 100)

    def test_ragged_rows_keep_their_data(self):
        result = self._normalize("TreeDepth,Args\n0,a,b\n")
        self.assertEqual(self._rows(result), ["0,\"a,b\""])


class UnpackTests(unittest.TestCase):
    def test_gzip_and_zip_unpack_to_a_fixed_name(self):
        tmp = Path(tempfile.mkdtemp())
        gz = tmp / "win_a.raw.gz"
        with gzip.open(gz, "wb") as handle:
            handle.write(b"image-a")
        out = ImageUnpacker().unpack(gz)
        self.assertEqual((out.name, out.read_bytes(), gz.exists()), ("win_a.raw", b"image-a", False))

        archive = tmp / "win_b.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../../etc/evil.raw", b"image-b" * 100)  # member paths are never used
            zf.writestr("readme.txt", b"hi")
        out = ImageUnpacker().unpack(archive)
        self.assertEqual((out, out.read_bytes()), (tmp / "win_b", b"image-b" * 100))
        self.assertEqual(DumpName("win_b.zip").os_family, OsFamily.WINDOWS)
        self.assertEqual(DumpName("win_a.raw.gz").database_name, "win_a")


class ClamScanParserTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ClamScanParser.parse_line("/d/file.0x1.dat: OK\n"), ("/d/file.0x1.dat", "OK", ""))
        self.assertEqual(ClamScanParser.parse_line("/d/a: b.exe: Win.Trojan.X-1 FOUND"), ("/d/a: b.exe", "FOUND", "Win.Trojan.X-1"))
        self.assertEqual(ClamScanParser.parse_line("/d/x: Empty file"), ("/d/x", "OTHER", "Empty file"))
        self.assertIsNone(ClamScanParser.parse_line("----------- SCAN SUMMARY -----------"))


class VolatilityCliTests(unittest.TestCase):
    def test_saved_config_is_reused(self):
        tmp = Path(tempfile.mkdtemp())
        cli = VolatilityCli(("vol",), tmp / "img.raw", tmp / "cache", plugin_dirs=(Path("/a"), Path("/b")))
        self.assertNotIn("-c", cli.build("windows.pslist.PsList"))
        cli.config_file = tmp / "config.json"
        cli.config_file.write_text("{}")
        cmd = cli.build("windows.pslist.PsList", ("--pid", "4"))
        self.assertEqual(cmd[cmd.index("-c") + 1], str(cli.config_file))
        self.assertEqual(cmd[cmd.index("-p") + 1], f"{Path('/a')};{Path('/b')}")
        self.assertEqual(cmd[-3:], ["windows.pslist.PsList", "--pid", "4"])
        self.assertNotIn("-c", cli.build("windows.pslist.PsList", use_config=False))


class _FakeTask(Task):
    def __init__(self, name, tier, log, followups=(), crash=False):
        super().__init__(name, name, tier)
        self.log, self._followups, self.crash = log, list(followups), crash

    def run(self, ctx):
        self.log.append(self.name)
        if self.crash:
            raise RuntimeError("bug")
        now = utcnow()
        return TaskResult(self.name, self.table, TaskStatus.OK, now, now, followups=self._followups)


class SchedulerTests(unittest.TestCase):
    def test_priority_followups_and_crashes(self):
        order, seen = [], []
        tasks = [
            _FakeTask("slow", Tier.SLOW, order),
            _FakeTask("core", Tier.CORE, order, followups=[_FakeTask("child", Tier.DEFAULT, order)]),
            _FakeTask("crash", Tier.DEFAULT, order, crash=True),
        ]
        results = TaskScheduler(1, on_result=seen.append).run(tasks, ctx=None)
        self.assertEqual(order, ["core", "crash", "child", "slow"])
        self.assertEqual({r.name: r.status for r in results}["crash"], TaskStatus.FAILED)
        self.assertEqual(len(seen), 4)

    def test_stop_skips_queued_tasks(self):
        stop = threading.Event()
        stop.set()
        results = TaskScheduler(2, on_result=lambda r: None, stop_event=stop).run([_FakeTask("a", Tier.CORE, [])], ctx=None)
        self.assertEqual([r.status for r in results], [TaskStatus.SKIPPED])


if __name__ == "__main__":
    unittest.main()
