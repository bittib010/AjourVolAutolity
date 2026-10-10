"""Command line entry point.

    python -m volautolity watch                         # service mode (systemd)
    python -m volautolity process win_case1.vmem        # one local image, ingest into ADX
    python -m volautolity process win_case1.vmem --no-ingest --only pslist,netscan
    python -m volautolity plugins --os windows          # show what would run
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from . import __version__
from .catalog import PluginCatalog
from .models import OsFamily
from .settings import Settings
from .sinks import LocalSink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="volautolity", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("watch", help="poll the upload container and process new images")

    process = sub.add_parser("process", help="process one local image")
    process.add_argument("image", type=Path)
    process.add_argument("--name", help="name to derive OS/database from (default: the file name)")
    process.add_argument("--os", choices=[o.value for o in OsFamily], help="override OS detection")
    process.add_argument("--no-ingest", action="store_true", help="only write CSVs locally")
    process.add_argument("--only", help="comma separated table names to run (bootstrap always runs)")

    plugins = sub.add_parser("plugins", help="list the plugin catalog")
    plugins.add_argument("--os", choices=[o.value for o in OsFamily], default=OsFamily.WINDOWS.value)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(threadName)-10s %(name)s: %(message)s",
    )
    for noisy in ("azure", "urllib3", "msal"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "plugins":
        return _list_plugins(OsFamily(args.os))

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    if args.command == "watch":
        return _watch(stop)
    return _process(args, stop)


def _credential(settings: Settings):
    from azure.identity import DefaultAzureCredential

    # On the VM this resolves to the user-assigned managed identity; locally it falls back to `az login`.
    return DefaultAzureCredential(managed_identity_client_id=settings.azure.managed_identity_client_id)


def _watch(stop: threading.Event) -> int:
    from .adx import AdxSink
    from .pipeline import DumpPipeline
    from .storage import BlobInbox, ResultsUploader
    from .watcher import InboxWatcher

    settings = Settings.from_env(require_azure=True)
    credential = _credential(settings)
    azure = settings.azure
    pipeline = DumpPipeline(settings, AdxSink(azure, credential), stop_event=stop)
    inbox = BlobInbox(azure.storage_account_url, azure.inbox_container, credential, settings.extensions)
    uploader = ResultsUploader(azure.storage_account_url, azure.results_container, credential) if azure.results_container else None
    InboxWatcher(settings, inbox, pipeline, uploader, stop).run()
    return 0


def _process(args: argparse.Namespace, stop: threading.Event) -> int:
    from .pipeline import DumpPipeline

    settings = Settings.from_env(require_azure=not args.no_ingest)
    if args.no_ingest:
        sink = LocalSink()
    else:
        from .adx import AdxSink

        sink = AdxSink(settings.azure, _credential(settings))
    only = {t.strip() for t in args.only.split(",")} if args.only else None
    pipeline = DumpPipeline(settings, sink, stop_event=stop, only_tables=only)
    report = pipeline.process(args.image.resolve(), args.name, OsFamily(args.os) if args.os else None)
    print(f"database: {report.database}\noutput:   {report.output_dir}")
    for result in report.results:
        print(f"  {result.status.value:8} {result.table:32} {result.duration_seconds:8.0f}s  {result.error[:80]}")
    return 0 if report.succeeded else 1


def _list_plugins(os_family: OsFamily) -> int:
    catalog = PluginCatalog()
    bootstrap = catalog.bootstrap(os_family)
    print(f"bootstrap: {bootstrap.name} -> {bootstrap.table}")
    for spec in sorted(catalog.plugins(os_family), key=lambda s: (s.tier, s.table)):
        args = " ".join(spec.args)
        print(f"  [{spec.tier.name:7}] {spec.table:28} {spec.name} {args}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
