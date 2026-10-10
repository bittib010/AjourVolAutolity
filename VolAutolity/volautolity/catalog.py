"""What runs for each OS: one entry per Volatility plugin and the ADX table it feeds.

To add a plugin, add a PluginSpec to the right list. Columns and types are derived from the CSV, so
no schema has to be written. `python -m volautolity plugins --os windows` shows the result.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .models import OsFamily, Tier


class PluginKind(enum.Enum):
    PLUGIN = "plugin"        # plain plugin run, CSV to one table
    STRINGS = "strings"      # GNU strings pre-pass, then windows.strings
    HIVELIST = "hivelist"    # hivelist --dump, then a recursive printkey per hive (printkey_<HIVE> tables)
    DUMPFILES = "dumpfiles"  # dumps files, then ClamAV over them (clamscan table)
    YARA = "yara"            # only when YARA rules are configured


@dataclass(frozen=True)
class PluginSpec:
    name: str
    table: str
    tier: Tier = Tier.DEFAULT
    kind: PluginKind = PluginKind.PLUGIN
    args: tuple[str, ...] = ()
    timeout: int | None = None
    writes_files: bool = False  # give the plugin its own -o directory


P = PluginSpec

WINDOWS_BOOTSTRAP = P("windows.info.Info", "info", Tier.BOOTSTRAP)
WINDOWS: list[PluginSpec] = []

# Derived views, created as stored functions after ingestion (they used to be extra CSV tables).
WINDOWS_FUNCTIONS = {
    "taskhost_triage": 'pslist | where ImageFileName has "taskhost"',
}

LINUX_BOOTSTRAP = P("linux.boottime.Boottime", "boottime", Tier.BOOTSTRAP)
LINUX: list[PluginSpec] = []

MAC_BOOTSTRAP = P("mac.dmesg.Dmesg", "dmesg", Tier.BOOTSTRAP)
MAC: list[PluginSpec] = []

# Run when no OS profile resolves: tells the analyst which kernel (and so which symbols) the image has.
DIAGNOSTICS = P("banners.Banners", "banners", Tier.BOOTSTRAP)


class PluginCatalog:
    _BOOTSTRAP = {OsFamily.WINDOWS: WINDOWS_BOOTSTRAP, OsFamily.LINUX: LINUX_BOOTSTRAP, OsFamily.MAC: MAC_BOOTSTRAP}
    _PLUGINS = {OsFamily.WINDOWS: WINDOWS, OsFamily.LINUX: LINUX, OsFamily.MAC: MAC}
    _FUNCTIONS = {OsFamily.WINDOWS: WINDOWS_FUNCTIONS}

    def bootstrap(self, os_family: OsFamily) -> PluginSpec:
        return self._BOOTSTRAP[os_family]

    def plugins(self, os_family: OsFamily) -> list[PluginSpec]:
        return list(self._PLUGINS[os_family])

    def functions(self, os_family: OsFamily) -> dict[str, str]:
        return dict(self._FUNCTIONS.get(os_family, {}))

    def diagnostics(self) -> PluginSpec:
        return DIAGNOSTICS
