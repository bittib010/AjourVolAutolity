"""Stand-in for the `vol` CLI used by the pipeline tests. Mimics the options VolatilityCli passes."""

import argparse
import csv
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
for flag in ("-f", "-r", "--cache-path", "-p", "-s", "--log", "-o", "--save-config", "-c"):
    parser.add_argument(flag)
parser.add_argument("-q", action="store_true")
parser.add_argument("plugin")
args, rest = parser.parse_known_args()

print("Volatility 3 Framework 9.9.9")  # the real CLI prints a banner to stdout too
plugin = args.plugin

if args.save_config:
    if Path(args.save_config).exists():
        sys.exit("Cannot write configuration: file already exists")
    Path(args.save_config).write_text(json.dumps({"kernel": "kernel"}))

if "Fail" in plugin:
    # With the saved config: pretend the config was rejected (triggers a retry); without: a real failure.
    print("Unsatisfied requirement plugins.Fail.kernel" if args.c else "boom", file=sys.stderr)
    sys.exit(1)

if plugin == "windows.info.Info":
    print("TreeDepth,Variable,Value")
    print("0,Kernel Base,0xf80000000000")
    print("0,SystemTime,2024-02-13 10:11:12.000000 UTC")
elif plugin == "windows.registry.hivelist.HiveList":
    # Same writer settings as Volatility's CSV renderer, which doubles backslashes.
    writer = csv.writer(sys.stdout, lineterminator="\n", escapechar="\\")
    writer.writerow(["TreeDepth", "Offset", "FileFullPath", "File output"])
    writer.writerow(["0", "0x87c104c8", "", "Disabled"])
    writer.writerow(["0", "0x87c1a248", r"\REGISTRY\MACHINE\SYSTEM", "Disabled"])
    writer.writerow(["0", "0x8b0c2008", r"\??\C:\Users\a\ntuser.dat", "Disabled"])
    writer.writerow(["0", "0x8b0c3008", r"\??\C:\Users\b\ntuser.dat", "Disabled"])
elif plugin == "windows.registry.printkey.PrintKey":
    offset = rest[rest.index("--offset") + 1] if "--offset" in rest else "all"
    print("TreeDepth,Last Write Time,Hive Offset,Type,Key,Name,Data,Volatile")
    print(f"0,2024-01-01 00:00:00.000000 ,{offset},Key,\\Root,Run,N/A,False")
elif plugin == "windows.config.Probe":
    # Reports whether the saved bootstrap config was passed, so tests can assert reuse.
    print("TreeDepth,UsedConfig")
    print(f"0,{bool(args.c)}")
else:
    print("TreeDepth,PID,Process,Offset(V),Create Time")
    print("0,4,System,0x8413a920,2023-04-24 14:41:32.000000 ")
    print("1,268,smss.exe,0x8adb0330,N/A")
