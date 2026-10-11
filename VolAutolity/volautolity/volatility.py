"""Thin wrapper around the Volatility 3 CLI.

Each plugin runs in its own process: one crashing or hanging plugin can't take the others down,
and plugins run truly in parallel (the framework isn't thread-safe and is GIL-bound in-process).

The expensive part of every `vol` invocation is stacking the memory layers and locating the kernel
(PDB scan + symbol lookup). The first ("bootstrap") plugin saves the resolved configuration with
`--save-config`; every later plugin loads it with `-c`, so that work is done once per image.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessOutcome:
    exit_code: int | None
    timed_out: bool
    duration: float
    stderr_tail: str

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.exit_code == 0


class VolatilityCli:
    def __init__(
        self,
        command: tuple[str, ...],
        image: Path,
        cache_dir: Path,
        plugin_dirs: tuple[Path, ...] = (),
        symbol_dirs: tuple[Path, ...] = (),
        remote_isf_url: str | None = None,
    ):
        self.command = command
        self.image = image
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)  # vol fails (identifier.cache) if it doesn't exist
        self.plugin_dirs = plugin_dirs
        self.symbol_dirs = tuple(p for p in symbol_dirs if p.exists())
        self.remote_isf_url = remote_isf_url
        self.config_file: Path | None = None

    def build(
        self,
        plugin: str,
        args: tuple[str, ...] = (),
        *,
        renderer: str = "csv",
        output_dir: Path | None = None,
        log_file: Path | None = None,
        save_config: Path | None = None,
        use_config: bool = True,
    ) -> list[str]:
        cmd = [*self.command, "-q", "-f", str(self.image), "-r", renderer, "--cache-path", str(self.cache_dir)]
        if self.plugin_dirs:
            cmd += ["-p", ";".join(str(p) for p in self.plugin_dirs)]
        if self.symbol_dirs:
            cmd += ["-s", ";".join(str(p) for p in self.symbol_dirs)]
        if self.remote_isf_url:  # Linux/Mac symbol lookup (Windows PDBs are fetched automatically)
            cmd += ["-u", self.remote_isf_url]
        if log_file:
            cmd += ["--log", str(log_file)]
        if output_dir:
            cmd += ["-o", str(output_dir)]
        if save_config:
            cmd += ["--save-config", str(save_config)]
        elif use_config and self.config_file and self.config_file.exists():
            cmd += ["-c", str(self.config_file)]
        cmd += [plugin, *args]
        return cmd


class ProcessRunner:
    """Runs a command with stdout/stderr to files, a hard timeout, and optional lower CPU priority."""

    def run(
        self,
        cmd: list[str],
        stdout_path: Path,
        stderr_path: Path,
        timeout: int,
        nice: int = 0,
        cwd: Path | None = None,
    ) -> ProcessOutcome:
        if nice and os.name == "posix":
            cmd = ["nice", "-n", str(nice), *cmd]
        log.debug("exec: %s", subprocess.list2cmdline(cmd))
        started = time.monotonic()
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            proc = subprocess.Popen(cmd, stdout=out, stderr=err, cwd=cwd, start_new_session=(os.name == "posix"))
            timed_out = False
            try:
                exit_code: int | None = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                self._kill(proc)
                exit_code = None
        return ProcessOutcome(
            exit_code=exit_code,
            timed_out=timed_out,
            duration=time.monotonic() - started,
            stderr_tail=_tail(stderr_path),
        )

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)  # take down helpers (e.g. nice -> vol) as well
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        proc.wait()


def _tail(path: Path, limit: int = 2000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""
