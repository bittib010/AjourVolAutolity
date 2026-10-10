"""Checks for the Azure-facing modules. Skipped when the Azure SDKs aren't installed."""

import importlib.util
import unittest

def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:  # parent package missing
        return False


HAVE_AZURE = all(_installed(m) for m in ("azure.kusto.ingest", "azure.mgmt.kusto", "azure.storage.blob"))


@unittest.skipUnless(HAVE_AZURE, "Azure SDKs not installed (pip install -r requirements.txt)")
class AzureModuleTests(unittest.TestCase):
    def test_modules_import(self):
        import volautolity.__main__  # noqa: F401
        import volautolity.adx  # noqa: F401
        import volautolity.watcher  # noqa: F401

    def test_inbox_extension_filter(self):
        from volautolity.storage import BlobInbox

        inbox = object.__new__(BlobInbox)  # skip the client; only the filter is under test
        inbox.extensions = {"raw", "vmem"}
        self.assertTrue(inbox._is_image("win_a.raw"))
        self.assertTrue(inbox._is_image("case/win_a.vmem.gz"))
        self.assertTrue(inbox._is_image("win_a.zip"))
        self.assertFalse(inbox._is_image("notes.txt.gz"))
        self.assertFalse(inbox._is_image("win_a.raw.sha256"))

    def test_schema_rendering_is_bracketed(self):
        from volautolity.adx import _schema
        from volautolity.csvnorm import Column, ColumnType

        self.assertEqual(_schema([Column("Type", ColumnType.STRING), Column("PID", ColumnType.LONG)]),
                         "['Type']:string, ['PID']:long")


@unittest.skipUnless(HAVE_AZURE, "Azure SDKs not installed (pip install -r requirements.txt)")
class WatcherTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        import threading
        from pathlib import Path

        from volautolity.settings import Settings
        from volautolity.storage import InboxItem

        self.tmp = Path(tempfile.mkdtemp())
        self.settings = Settings(
            work_dir=self.tmp, vol_command=("vol",), workers=1, plugin_timeout=1, slow_plugin_timeout=1,
            poll_interval=1, include_slow=False, enable_clamav=False, yara_rules=None, plugin_dirs=(),
            symbol_dirs=(), extensions=("raw",), keep_dumps=False, azure=None,
        )
        self.stop = threading.Event()
        self.item = InboxItem("case/win_a.raw", 10, None, expected_sha256="aa")
        self.marks = []
        test = self

        class FakeInbox:
            def mark(self, item, status, **details):
                test.marks.append((status, details))

            def download(self, item, destination):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"x" * 10)
                return destination

        self.inbox = FakeInbox()

    def _watcher(self, process):
        from volautolity.pipeline import PipelineReport
        from volautolity.models import OsFamily
        from volautolity.watcher import InboxWatcher

        class FakePipeline:
            def process(_, image, name):
                process(image)
                return PipelineReport("win_a", OsFamily.WINDOWS, self.tmp / "out", sha256="bb")

        return InboxWatcher(self.settings, self.inbox, FakePipeline(), None, self.stop)

    def test_hash_mismatch_fails_and_local_copy_is_removed(self):
        seen = []
        self._watcher(seen.append)._handle(self.item)
        self.assertEqual(seen[0], self.tmp / "inbox" / "win_a.raw")  # blob path never becomes a local path
        self.assertFalse(seen[0].exists())
        status, details = self.marks[-1]
        self.assertEqual((status, details["sha256"]), ("failed", "bb"))
        self.assertIn("mismatch", details["error"])

    def test_interrupted_run_stays_processing(self):
        self._watcher(lambda image: self.stop.set())._handle(self.item)
        self.assertEqual([m[0] for m in self.marks], ["processing"])

    def test_pipeline_crash_is_recorded(self):
        def boom(image):
            raise RuntimeError("kaput")

        self._watcher(boom)._handle(self.item)
        self.assertEqual(self.marks[-1][0], "failed")
        self.assertIn("kaput", self.marks[-1][1]["error"])


if __name__ == "__main__":
    unittest.main()
