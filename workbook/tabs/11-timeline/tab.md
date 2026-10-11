# Timeline
One timeline built from the timestamped tables (process start/exit, network sockets, registry key writes, services/tasks, Amcache/ShimCache/UserAssist, unloaded drivers, symbolic links). Set **Pivot time** to the first malicious event you found (UTC, e.g. `2025-03-06 17:45:00`) and a window; leave it empty to see the time before acquisition.
Volatility timestamps have whole-second precision and are UTC. The `timeliner` plugin is not used here: in Volatility 2.28 it repeats rows from earlier plugins.
