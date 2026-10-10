"""Service loop: poll the upload container and process images one at a time.

Images are processed sequentially on purpose. Each image already uses every core (one Volatility
process per worker); running several images at once only made them all slower and starved RAM.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

from .pipeline import SCRATCH_DIR, DumpPipeline
from .settings import Settings
from .storage import BlobInbox, InboxItem, ResultsUploader
from .unpack import ImageUnpacker

log = logging.getLogger(__name__)


class InboxWatcher:
    def __init__(self, settings: Settings, inbox: BlobInbox, pipeline: DumpPipeline,
                 uploader: ResultsUploader | None, stop_event: threading.Event):
        self.settings = settings
        self.inbox = inbox
        self.pipeline = pipeline
        self.uploader = uploader
        self.stop_event = stop_event

    def run(self) -> None:
        log.info("watching for memory images (every %ss)", self.settings.poll_interval)
        first_poll = True
        while not self.stop_event.is_set():
            try:
                items = self.inbox.pending(include_in_progress=first_poll)
                first_poll = False
            except Exception:
                log.exception("listing the inbox failed; retrying")  # e.g. RBAC still propagating after deploy
                items = []
            for item in items:
                if self.stop_event.is_set():
                    break
                self._handle(item)
            self.stop_event.wait(self.settings.poll_interval)

    def _handle(self, item: InboxItem) -> None:
        # Only the base name is used locally: blob names are uploader-controlled (no path traversal).
        local = self.settings.work_dir / "inbox" / Path(item.name).name
        wrapped = ImageUnpacker.is_wrapped(item.name)
        try:
            self.inbox.mark(item, "processing")
            # images compress ~3-5x, and outputs (dumped files, strings) can be as large as the image
            self._ensure_space(item.size * (8 if wrapped else 2))
            self.inbox.download(item, local)
            if wrapped:
                local = ImageUnpacker().unpack(local)
            report = self.pipeline.process(local, item.name)
            if self.stop_event.is_set():
                # Interrupted: leave it "processing" so the first poll after restart picks it up again.
                log.warning("%s interrupted by shutdown; will be reprocessed", item.name)
                return
            status = "done" if report.succeeded else "failed"
            details = {"database": report.database, "failed_tasks": str(len(report.failed_tasks)), "sha256": report.sha256}
            if item.expected_sha256 and item.expected_sha256 != report.sha256:
                # The image is not what the uploader hashed: corrupted or tampered with in transit.
                log.error("%s: SHA-256 mismatch (uploader %s, received %s)", item.name, item.expected_sha256, report.sha256)
                status, details["error"] = "failed", "sha256 mismatch with uploader-supplied hash"
            self.inbox.mark(item, status, **details)
            if self.uploader:
                count = self.uploader.upload_tree(report.output_dir, report.database, skip_dirs={SCRATCH_DIR})
                log.info("uploaded %d result files for %s", count, report.database)
                shutil.rmtree(report.output_dir, ignore_errors=True)  # results live in blob storage now
        except Exception as exc:
            log.exception("processing %s failed", item.name)
            try:
                self.inbox.mark(item, "failed", error=f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("could not record the failure on %s", item.name)
        finally:
            if not self.settings.keep_dumps:
                local.unlink(missing_ok=True)

    def _ensure_space(self, needed: int) -> None:
        self.settings.work_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.settings.work_dir).free
        if free < needed:
            raise RuntimeError(f"not enough free space in {self.settings.work_dir}: "
                               f"{free / 2**30:.1f} GiB free, ~{needed / 2**30:.1f} GiB needed")
