# Injection & evasion
Code that lives where it should not: executable private memory, hollowed or ghosted processes, DLLs hidden from the loader, threads starting in unbacked memory, direct/indirect system calls that bypass EDR hooks, and patched ETW/AMSI.
Calibrated on real images: browsers, PowerShell/.NET, Chromium WebView and AV engines legitimately hold RWX memory and call syscalls directly, so findings in those processes are downgraded, and processes whose loader lists could not be read at all are not reported as "unlinked".
