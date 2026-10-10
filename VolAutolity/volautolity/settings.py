"""Runtime settings, read from environment variables.

On the VM these come from /etc/volautolity/volautolity.env (rendered by cloud-init from OpenTofu
outputs). Locally you can export them yourself, or run `process --no-ingest` with no Azure settings.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXTENSIONS = ("dd", "raw", "mem", "vmem", "dmp", "dump", "lime", "bin", "img", "core", "elf")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value if value else default


def _env_required(name: str) -> str:
    value = _env(name)
    if value is None:
        raise SettingsError(f"Missing required environment variable {name}")
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_paths(name: str) -> tuple[Path, ...]:
    value = _env(name)
    return tuple(Path(p) for p in value.split(":") if p) if value else ()


class SettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class AzureSettings:
    subscription_id: str
    resource_group: str
    location: str
    cluster_name: str
    cluster_uri: str
    cluster_ingest_uri: str
    storage_account_url: str
    inbox_container: str
    results_container: str | None
    managed_identity_client_id: str | None

    @classmethod
    def from_env(cls) -> "AzureSettings":
        return cls(
            subscription_id=_env_required("AZURE_SUBSCRIPTION_ID"),
            resource_group=_env_required("AZURE_RESOURCE_GROUP"),
            location=_env_required("AZURE_LOCATION"),
            cluster_name=_env_required("ADX_CLUSTER_NAME"),
            cluster_uri=_env_required("ADX_CLUSTER_URI"),
            cluster_ingest_uri=_env_required("ADX_INGEST_URI"),
            storage_account_url=_env_required("STORAGE_ACCOUNT_URL"),
            inbox_container=_env_required("INBOX_CONTAINER"),
            results_container=_env("RESULTS_CONTAINER"),
            managed_identity_client_id=_env("AZURE_CLIENT_ID"),
        )


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    vol_command: tuple[str, ...]
    workers: int
    plugin_timeout: int
    slow_plugin_timeout: int
    poll_interval: int
    include_slow: bool
    enable_clamav: bool
    yara_rules: Path | None
    plugin_dirs: tuple[Path, ...]
    symbol_dirs: tuple[Path, ...]
    extensions: tuple[str, ...]
    keep_dumps: bool
    azure: AzureSettings | None
    remote_isf_url: str | None = None

    @classmethod
    def from_env(cls, require_azure: bool = True) -> "Settings":
        yara = _env("YARA_RULES_FILE")
        extensions = _env("DUMP_EXTENSIONS")
        return cls(
            work_dir=Path(_env("WORK_DIR", "/mnt/volautolity")),
            vol_command=tuple(shlex.split(_env("VOL_COMMAND", "vol"))),
            workers=_env_int("WORKERS", default_workers()),
            plugin_timeout=_env_int("PLUGIN_TIMEOUT_SECONDS", 2 * 3600),
            slow_plugin_timeout=_env_int("SLOW_PLUGIN_TIMEOUT_SECONDS", 8 * 3600),
            poll_interval=_env_int("POLL_INTERVAL_SECONDS", 30),
            include_slow=_env_bool("INCLUDE_SLOW_PLUGINS", True),
            enable_clamav=_env_bool("ENABLE_CLAMAV", True),
            yara_rules=Path(yara) if yara else None,
            plugin_dirs=_env_paths("VOL_PLUGIN_DIRS"),
            symbol_dirs=_env_paths("VOL_SYMBOL_DIRS"),
            remote_isf_url=_env("VOL_REMOTE_ISF_URL"),
            extensions=tuple(e.strip().lower().lstrip(".") for e in extensions.split(",")) if extensions else DEFAULT_EXTENSIONS,
            keep_dumps=_env_bool("KEEP_LOCAL_DUMPS", False),
            azure=AzureSettings.from_env() if require_azure else None,
        )


def default_workers() -> int:
    """One Volatility process per core, but budget ~2 GiB RAM per process (big plugins are memory hungry)."""
    cpus = os.cpu_count() or 2
    try:
        mem_gib = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (AttributeError, ValueError, OSError):
        return max(1, cpus)
    return max(1, min(cpus, int(mem_gib // 2)))
