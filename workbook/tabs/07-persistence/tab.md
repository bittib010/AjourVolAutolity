# Persistence
Autostart locations from the registry hives in memory (Run keys, Winlogon, IFEO, AppInit/AppCert DLLs, LSA packages, BootExecute, print monitors, time providers, netsh helpers, COM/shell hijacks ...), services and scheduled tasks.
Registry values come from the recursive printkey of each hive (`printkey_SOFTWARE`, `printkey_SYSTEM`, `printkey_ntuser*` ...). Memory only holds the parts of a hive that were resident - an absent value is not proof that it is not set. The registry ControlSet in memory may be `ControlSet001`; `CurrentControlSet` is a volatile link.
