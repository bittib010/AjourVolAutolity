# Triage workbook source

`cfg/windows_triage.json` (the Azure Workbook deployed by `cfg/workbook.tf`) is **generated** from the KQL in
this directory. Edit the `.kql` files, never the JSON.

```
workbook/
  build.py              builds cfg/windows_triage.json
  lib/<Name>.kql        shared `let Name = ...;` definitions (process model, detectors, lists)
  tabs/NN-key/          one directory per workbook tab
    tab.md              "# Title" + intro text
    params.json         optional tab parameters (dropdowns/text); "kql" for query-backed dropdowns
    NNN-slug.kql        one workbook query, with a metadata header (see build.py)
  validate/check.js     semantic KQL validation with Microsoft's Kusto.Language analyzer
```

```powershell
python workbook/build.py                                   # regenerate cfg/windows_triage.json
python workbook/build.py --check                           # CI: fail if the JSON is stale
cd workbook/validate; npm ci; cd ../..
python workbook/build.py --export-queries $env:TEMP/q.json
node workbook/validate/check.js $env:TEMP/q.json VolAutolity/volautolity/schemas.json
```

## How it fits together

- **Self-contained queries.** A query that mentions a library name (e.g. `Procs()`, `Det_Network()`,
  `StagingDirHigh`) gets that definition, and whatever it depends on, prepended at build time. Every query in
  the workbook can therefore be copied into the ADX web UI and run as is.
- **Every table exists.** The worker creates every table up front, from `schemas.json` (Volatility's own
  column declarations). A plugin that failed or found nothing leaves an empty, correctly typed table, so
  queries never break on a missing table.
- **The validator checks against those same schemas:**
  - unknown tables and columns,
  - type errors,
  - wrong function signatures.

## Detectors

- **Output.** Each `lib/Det_*.kql` returns `PID, Process, Severity, Category, Finding, Detail`.
- **Aggregation.** `AllFindings()` unions all detectors. It feeds the Overview, the per-process score
  and the Pivot tab.
- **Severity.** One of Critical / High / Medium / Low; *Info* is used only for review lists.
- **Documentation per query.** Each tab query documents why it matters, its known false positives,
  ATT&CK techniques and references. The workbook shows these above the result.

The detection logic comes from SANS *Hunt Evil*, Sigma, Elastic detection rules, LOLBAS, MITRE ATT&CK,
The DFIR Report, CISA advisories, loldrivers.io and the Volatility plugin sources.

### Calibration on a real image

The process, credential and injection detectors were replayed against a clean Windows 10 (19041) memory
image (the Volatility project's own test image). That replay changed several rules:
- **Look-alike process names.** Legitimate Windows binaries similar to core names (for example
  `logonui.exe` vs `winlogon.exe`, `synchost.exe` vs `svchost.exe`) are allowlisted. The list was measured
  against every `.exe` in `C:\Windows`, `System32` and `SysWOW64`.
- **Similarity scope.** Name similarity only counts outside the Windows directories.
- **Early-boot parentage.** System (PID 4) is always accepted as a parent: the Registry process is created
  seconds *before* System's recorded CreateTime.
- **lsass handles.** System's own handles to lsass are allowlisted.
- **Unlinked modules.** Processes whose loader lists are unreadable (paged-out PEB, suspended UWP apps)
  are skipped. Resource-only DLLs are Low.
- **JIT processes.** Browsers, .NET/PowerShell, AV and cloud agents are down-ranked for RWX memory and
  direct system calls.

On that clean image the remaining findings are Low-severity RWX regions in Microsoft Defender and the Azure
guest agent.
