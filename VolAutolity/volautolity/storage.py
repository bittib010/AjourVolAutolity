"""Blob storage access: the upload inbox and the results container.

The old setup mounted the container with blobfuse and waited for inotify events, which never fire
for blobs uploaded from elsewhere (only for local writes through the mount). Polling the container
through the SDK sees every committed upload, and blob metadata records what has been processed, so
state survives VM restarts and nothing is written into the mount.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from azure.storage.blob import ContainerClient

from .models import utcnow
from .unpack import ImageUnpacker

log = logging.getLogger(__name__)

STATUS_KEY = "volautolity_status"


@dataclass(frozen=True)
class InboxItem:
    name: str
    size: int
    status: str | None
    expected_sha256: str | None = None  # optional `sha256` metadata set by the uploader (azcopy --metadata)


class BlobInbox:
    def __init__(self, account_url: str, container: str, credential, extensions: tuple[str, ...]):
        self._container = ContainerClient(account_url, container, credential=credential)
        self.extensions = {e.lower() for e in extensions}

    def pending(self, include_in_progress: bool = False) -> list[InboxItem]:
        """Unprocessed images, oldest first. `include_in_progress` picks up work interrupted by a restart."""
        items: list[tuple] = []
        for blob in self._container.list_blobs(include=["metadata"]):
            if not self._is_image(blob.name):
                continue
            metadata = {k.lower(): v for k, v in (blob.metadata or {}).items()}
            status = metadata.get(STATUS_KEY)
            if status is None or (include_in_progress and status == "processing"):
                expected = (metadata.get("sha256") or "").strip().lower() or None
                items.append((blob.last_modified, InboxItem(blob.name, blob.size, status, expected)))
        return [item for _, item in sorted(items, key=lambda pair: pair[0])]

    def mark(self, item: InboxItem, status: str, **details: str) -> None:
        client = self._container.get_blob_client(item.name)
        metadata = dict(client.get_blob_properties().metadata or {})
        metadata[STATUS_KEY] = status
        metadata["volautolity_updated"] = utcnow().isoformat(timespec="seconds")
        metadata["volautolity_host"] = socket.gethostname()
        for key, value in details.items():
            metadata[f"volautolity_{key}"] = _ascii(value)[:1024]
        client.set_blob_metadata(metadata)

    def download(self, item: InboxItem, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s (%.1f GiB)", item.name, item.size / 2**30)
        with destination.open("wb") as handle:
            self._container.get_blob_client(item.name).download_blob(max_concurrency=8).readinto(handle)
        return destination

    def _is_image(self, name: str) -> bool:
        if PurePosixPath(name).suffix.lower() == ".zip":
            return True  # the image inside is checked by the pipeline (it fails cleanly if it isn't one)
        inner = PurePosixPath(ImageUnpacker.inner_name(name)).suffix.lstrip(".").lower()
        return inner in self.extensions


class ResultsUploader:
    """Copies CSVs, logs and dumped files (registry hives, dumpfiles) back to storage, since the VM is disposable."""

    def __init__(self, account_url: str, container: str, credential):
        self._container = ContainerClient(account_url, container, credential=credential)

    def upload_tree(self, root: Path, prefix: str, skip_dirs: set[str]) -> int:
        count = 0
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if not path.is_file() or (relative.parts and relative.parts[0] in skip_dirs):
                continue
            with path.open("rb") as handle:
                self._container.upload_blob(f"{prefix}/{relative.as_posix()}", handle, overwrite=True, max_concurrency=4)
            count += 1
        return count


def _ascii(value: str) -> str:
    return value.encode("ascii", errors="replace").decode("ascii").replace("\n", " ").replace("\r", " ")
