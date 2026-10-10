"""What runs for each OS: one entry per Volatility plugin and the ADX table it feeds.

Targets Volatility 3 2.28.x (see requirements.txt). Table names are kept stable: they are what the
workbook and saved queries use, even when Volatility moves a plugin (`windows.malfind.Malfind` ->
`windows.malware.malfind.Malfind`). The old names are deprecated aliases past their removal date.

To add a plugin, add a PluginSpec to the right list. Columns and types are derived from the CSV, so
no schema has to be written. `python -m volautolity plugins --os windows` shows the result.

Deliberately not run (they need input no unattended run can provide, or produce no useful table):
  windows.pe_symbols / windows.pedump / linux.module_extract / linux.pagecache.InodePages (required
  --module/--base/--inode), regexscan / windows.vadregexscan / linux.vmaregexscan (required --pattern),
  windows.memmap (without --pid there is no PID column), windows.crashinfo (crash dumps only),
  windows.registry.hivescan (dropped earlier: hivelist covers it), windows.pstree (built in the workbook),
  layerwriter / configwriter / frameworkinfo / isfinfo (tooling, not analysis).
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


C, D, S = Tier.CORE, Tier.DEFAULT, Tier.SLOW
P = PluginSpec

# --------------------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------------------
WINDOWS_BOOTSTRAP = P("windows.info.Info", "info", Tier.BOOTSTRAP)

WINDOWS: list[PluginSpec] = [
    # Processes, sessions, command lines: what the workbook opens with
    P("windows.pslist.PsList", "pslist", C),
    P("windows.psscan.PsScan", "psscan", C),
    P("windows.cmdline.CmdLine", "cmdline", C),
    P("windows.privileges.Privs", "privileges", C),
    P("windows.getsids.GetSIDs", "getsids", C),
    P("windows.sessions.Sessions", "sessions", C),
    P("windows.envars.Envars", "envars", D),
    P("windows.dlllist.DllList", "dlllist", C),
    P("windows.handles.Handles", "handles", C),
    P("windows.joblinks.JobLinks", "joblinks", D),
    P("windows.verinfo.VerInfo", "verinfo", D),
    P("windows.iat.IAT", "iat", D),
    P("windows.consoles.Consoles", "consoles", C),           # new: console history + screen buffers (x64 Win10+)
    P("windows.cmdscan.CmdScan", "cmdscan", C),              # new: command history (x64 Win10+)
    P("windows.threads.Threads", "threads", D),
    P("windows.thrdscan.ThrdScan", "thrdscan", D),           # new
    P("windows.suspended_threads.SuspendedThreads", "suspended_threads", D),  # new
    P("windows.debugregisters.DebugRegisters", "debugregisters", D),          # new
    P("windows.vadinfo.VadInfo", "vadinfo", D),
    P("windows.vadwalk.VadWalk", "vadwalk", D),
    P("windows.virtmap.VirtMap", "virtmap", D),

    # Network
    P("windows.netscan.NetScan", "netscan", C),
    P("windows.netstat.NetStat", "netstat", C),

    # Malware / injection / rootkit checks (moved under windows.malware.* in 2.27)
    P("windows.malware.malfind.Malfind", "malfind", C),
    P("windows.malware.hollowprocesses.HollowProcesses", "hollowprocesses", D),
    P("windows.malware.processghosting.ProcessGhosting", "processghosting", D),
    P("windows.malware.ldrmodules.LdrModules", "ldrmodules", D),
    P("windows.malware.psxview.PsXView", "psxview", D),
    P("windows.malware.suspicious_threads.SuspiciousThreads", "suspicious_threads", D),
    P("windows.malware.skeleton_key_check.Skeleton_Key_Check", "skeleton_key_check", D),
    P("windows.malware.drivermodule.DriverModule", "drivermodule", D),
    P("windows.malware.svcdiff.SvcDiff", "svcdiff", D),                          # new (x64 Win10 15063+)
    P("windows.malware.pebmasquerade.PebMasquerade", "pebmasquerade", D),        # new
    P("windows.malware.unhooked_system_calls.UnhookedSystemCalls", "unhooked_system_calls", D),  # new
    P("windows.malware.direct_system_calls.DirectSystemCalls", "direct_system_calls", D),        # new, built-in rules
    P("windows.malware.indirect_system_calls.IndirectSystemCalls", "indirect_system_calls", D),  # new, built-in rules
    P("windows.etwpatch.EtwPatch", "etwpatch", D),                               # new
    P("windows.orphan_kernel_threads.Threads", "orphan_kernel_threads", D),      # new
    P("windows.truecrypt.Passphrase", "truecrypt", D),

    # Kernel, drivers, objects
    P("windows.modules.Modules", "modules", D),
    P("windows.modscan.ModScan", "modscan", D),
    P("windows.unloadedmodules.UnloadedModules", "unloadedmodules", D),
    P("windows.driverscan.DriverScan", "driverscan", D),
    P("windows.driverirp.DriverIrp", "driverirp", D),
    P("windows.devicetree.DeviceTree", "devicetree", D),
    P("windows.callbacks.Callbacks", "callbacks", D),
    P("windows.ssdt.SSDT", "ssdt", D),
    P("windows.timers.Timers", "timers", D),
    P("windows.kpcrs.KPCRs", "kpcrs", D),
    P("windows.mutantscan.MutantScan", "mutantscan", D),
    P("windows.symlinkscan.SymlinkScan", "symlinkscan", D),
    P("windows.bigpools.BigPools", "bigpools", D),
    P("windows.poolscanner.PoolScanner", "poolscanner", D),
    P("windows.statistics.Statistics", "Statistics", D),
    P("windows.mbrscan.MBRScan", "mbrscan", D),

    # GUI objects (new; x64 Win7+, other builds fail cleanly into volautolity_runs)
    P("windows.desktops.Desktops", "desktops", D),
    P("windows.deskscan.DeskScan", "deskscan", D),
    P("windows.windows.Windows", "gui_windows", D),
    P("windows.windowstations.WindowStations", "windowstations", D),

    # Services
    P("windows.svcscan.SvcScan", "svcscan", C),
    P("windows.svclist.SvcList", "svclist", D),               # new (x64 Win10 15063+)
    P("windows.getservicesids.GetServiceSIDs", "getservicesids", D),

    # Registry (credentials moved under windows.registry.* in 2.26)
    P("windows.registry.hivelist.HiveList", "registry_hivelist", C, PluginKind.HIVELIST),
    P("windows.registry.printkey.PrintKey", "registry_printkey", D),
    P("windows.registry.userassist.UserAssist", "registry_userassist", D),
    P("windows.registry.certificates.Certificates", "registry", D),
    P("windows.registry.getcellroutine.GetCellRoutine", "getcellroutine", D),
    P("windows.registry.hashdump.Hashdump", "hashdump", C),
    P("windows.registry.lsadump.Lsadump", "lsadump", C),
    P("windows.registry.cachedump.Cachedump", "cachedump", C),
    P("windows.registry.amcache.Amcache", "amcache", D),                 # new
    P("windows.registry.scheduled_tasks.ScheduledTasks", "scheduled_tasks", D),  # new (x64 only in 2.28.2)
    P("windows.shimcachemem.ShimcacheMem", "shimcachemem", D),

    # Files
    P("windows.filescan.FileScan", "filescan", D),
    P("windows.mftscan.MFTScan", "mftscan", D),
    P("windows.mftscan.ADS", "mftscan_ads", D),                       # new
    P("windows.mftscan.ResidentData", "mftscan_residentdata", S),     # new
    P("windows.dumpfiles.DumpFiles", "dumpfiles", S, PluginKind.DUMPFILES),

    # Whole-image passes: slow, scheduled last
    P("timeliner.Timeliner", "timeliner", S),
    P("windows.strings.Strings", "strings", S, PluginKind.STRINGS),
    P("vmscan.Vmscan", "vmscan", S),
    P("yarascan.YaraScan", "yarascan", S, PluginKind.YARA),
    P("windows.vadyarascan.VadYaraScan", "vadyarascan", S, PluginKind.YARA),
]

# Derived views, created as stored functions after ingestion (they used to be extra CSV tables).
WINDOWS_FUNCTIONS = {
    "taskhost_triage": 'pslist | where ImageFileName has "taskhost"',
}

# --------------------------------------------------------------------------------------------------
# Linux (needs an ISF symbol file for the exact kernel: VOL_SYMBOL_DIRS or VOL_REMOTE_ISF_URL)
# --------------------------------------------------------------------------------------------------
LINUX_BOOTSTRAP = P("linux.boottime.Boottime", "boottime", Tier.BOOTSTRAP)

LINUX: list[PluginSpec] = [
    P("linux.pslist.PsList", "pslist", C),
    P("linux.psscan.PsScan", "psscan", C),
    P("linux.pstree.PsTree", "pstree", C),
    P("linux.psaux.PsAux", "psaux", C),
    P("linux.bash.Bash", "bash", C),
    P("linux.envars.Envars", "envars", D),
    P("linux.lsof.Lsof", "lsof", D),
    P("linux.sockstat.Sockstat", "sockstat", C),
    P("linux.sockscan.Sockscan", "sockscan", D),                  # new
    P("linux.ip.Addr", "ip_addr", D),                              # new
    P("linux.ip.Link", "ip_link", D),                              # new
    P("linux.capabilities.Capabilities", "capabilities", D),
    P("linux.library_list.LibraryList", "library_list", D),
    P("linux.elfs.Elfs", "elfs", D),
    P("linux.proc.Maps", "proc_maps", D),
    P("linux.pidhashtable.PIDHashTable", "pidhashtable", D),       # new
    P("linux.pscallstack.PsCallStack", "pscallstack", D),          # new
    P("linux.ptrace.Ptrace", "ptrace", D),                         # new
    P("linux.kthreads.Kthreads", "kthreads", D),                   # new (kernel >= 5.8)
    P("linux.mountinfo.MountInfo", "mountinfo", D),
    P("linux.kmsg.Kmsg", "kmsg", D),
    P("linux.iomem.IOMem", "iomem", D),
    P("linux.lsmod.Lsmod", "lsmod", D),
    P("linux.kallsyms.Kallsyms", "kallsyms", D),                   # new
    P("linux.ebpf.EBPF", "ebpf", D),                               # new
    P("linux.vmcoreinfo.VMCoreInfo", "vmcoreinfo", D),             # new
    P("linux.graphics.fbdev.Fbdev", "fbdev", D),                   # new
    P("linux.malware.malfind.Malfind", "malfind", C),
    P("linux.malware.check_afinfo.Check_afinfo", "check_afinfo", D),
    P("linux.malware.check_creds.Check_creds", "check_creds", D),
    P("linux.malware.check_idt.Check_idt", "check_idt", D),
    P("linux.malware.check_modules.Check_modules", "check_modules", D),
    P("linux.malware.check_syscall.Check_syscall", "check_syscall", D),
    P("linux.malware.hidden_modules.Hidden_modules", "hidden_modules", D),
    P("linux.malware.keyboard_notifiers.Keyboard_notifiers", "keyboard_notifiers", D),
    P("linux.malware.modxview.Modxview", "modxview", D),
    P("linux.malware.netfilter.Netfilter", "netfilter", D),
    P("linux.malware.process_spoofing.ProcessSpoofing", "process_spoofing", D),   # new
    P("linux.malware.tty_check.Tty_Check", "tty_check", D),
    P("linux.tracing.ftrace.CheckFtrace", "ftrace", D),                    # new
    P("linux.tracing.perf_events.PerfEvents", "perf_events", D),           # new
    P("linux.tracing.tracepoints.CheckTracepoints", "tracepoints", D),     # new
    P("linux.pagecache.Files", "pagecache_files", S),                      # new
    P("linux.pagecache.RecoverFs", "pagecache_recoverfs", S, writes_files=True),  # new: tarball of cached files
    P("timeliner.Timeliner", "timeliner", S),
    P("linux.vmayarascan.VmaYaraScan", "vmayarascan", S, PluginKind.YARA),
    P("yarascan.YaraScan", "yarascan", S, PluginKind.YARA),
]

# --------------------------------------------------------------------------------------------------
# macOS (upstream no longer actively maintains mac support; needs KDK-derived ISF symbols)
# --------------------------------------------------------------------------------------------------
MAC_BOOTSTRAP = P("mac.dmesg.Dmesg", "dmesg", Tier.BOOTSTRAP)

MAC: list[PluginSpec] = [
    P("mac.pslist.PsList", "pslist", C),
    P("mac.pstree.PsTree", "pstree", C),
    P("mac.psaux.Psaux", "psaux", C),
    P("mac.bash.Bash", "bash", C),
    P("mac.netstat.Netstat", "netstat", C),
    P("mac.ifconfig.Ifconfig", "ifconfig", D),
    P("mac.lsof.Lsof", "lsof", D),
    P("mac.list_files.List_Files", "list_files", D),
    P("mac.mount.Mount", "mount", D),
    P("mac.proc_maps.Maps", "proc_maps", D),
    P("mac.malfind.Malfind", "malfind", C),
    P("mac.lsmod.Lsmod", "lsmod", D),
    P("mac.check_syscall.Check_syscall", "check_syscall", D),
    P("mac.check_sysctl.Check_sysctl", "check_sysctl", D),
    P("mac.check_trap_table.Check_trap_table", "check_trap_table", D),
    P("mac.kauth_listeners.Kauth_listeners", "kauth_listeners", D),
    P("mac.kauth_scopes.Kauth_scopes", "kauth_scopes", D),
    P("mac.kevents.Kevents", "kevents", D),
    P("mac.socket_filters.Socket_filters", "socket_filters", D),
    P("mac.timers.Timers", "timers", D),
    P("mac.trustedbsd.Trustedbsd", "trustedbsd", D),
    P("mac.vfsevents.VFSevents", "vfsevents", D),
    P("timeliner.Timeliner", "timeliner", S),
    P("yarascan.YaraScan", "yarascan", S, PluginKind.YARA),
]

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
