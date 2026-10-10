# Acquiring memory and getting it to VolAutolity

This guide is for the person collecting memory from a suspect system and uploading it for analysis.
The analyst who deployed VolAutolity gives you an **upload link** (an upload-only SAS URL) or, if you
are in the same Entra ID tenant, access to the upload container. Nothing else is needed on your side.

> Tool versions and flags change. Always take tools from their official release page, check the
> published hash/signature, and test your procedure on a non-production system first.

- [General rules](#general-rules)
- [Windows (physical and on-prem VMs)](#windows)
- [Linux](#linux)
- [macOS](#macos)
- [Virtual machines from the hypervisor side](#hypervisor-side-acquisition)
- [Azure virtual machines](#azure-virtual-machines)
- [Upload](#upload)
- [After the upload](#after-the-upload)

## General rules

1. **Memory first.** Memory is the most volatile evidence: acquire it before disk imaging, before
   pulling the network cable (isolate with a firewall/NSG/EDR isolation instead), and never reboot
   or shut the system down first.
2. **Write the image to external or secondary storage**, not the suspect's system drive: writing
   there overwrites unallocated space that may hold evidence. On Azure VMs use the temp disk
   (`D:` on Windows, `/mnt` on Linux) when the size has one.
3. **Run tools from trusted media** (USB, a read-only share, a hash-verified download), not from
   binaries already on the suspect host.
4. **Record for chain of custody:** who, when (UTC), which host, which tool and version, the image
   SHA-256, and anything you did to the system.
5. **For Linux, also record `uname -r` and `cat /proc/version`.** The analyst needs the exact
   kernel version to prepare symbols (see [Linux](#linux)).
6. **Name the file `<os>_<case-or-host>.<ext>`**, for example `win_acme-dc01_20261010.raw`.
   - `<os>` is `win`, `linux` or `mac`.
   - Accepted extensions: `dd raw mem vmem dmp dump lime bin img core elf`, optionally compressed
     as `.gz` or `.zip`.
   - The name before the extension becomes the database name in Azure Data Explorer.

## Windows

| Tool | Notes |
|---|---|
| [WinPmem](https://github.com/Velocidex/WinPmem) (open source) | `winpmem_mini_x64_<version>.exe D:\win_host.raw`. Produces a raw image. Run as Administrator. |
| [Magnet DumpIt](https://www.magnetforensics.com/resources/magnet-dumpit-for-windows/) (free) | Produces a Microsoft crash dump (`.dmp`), which Volatility reads directly. |
| [FTK Imager](https://www.exterro.com/digital-forensics-software/ftk-imager) → *Capture Memory* | Produces a `.mem` raw image. GUI only. |
| [Velociraptor](https://docs.velociraptor.app/) `Windows.Memory.Acquisition` | Uses WinPmem. Works at fleet scale. An *offline collector* can upload straight to Azure Blob Storage with the SAS URL. |
| Microsoft Defender for Endpoint live response | `putfile` an acquisition tool from the library, then `run` a script that acquires and uploads with `azcopy`. Don't use `getfile` for memory: it has a file size limit far below typical RAM sizes. |

Notes:
- **Memory integrity (HVCI) and vulnerable-driver blocklists can block older acquisition drivers.**
  Use current tool versions.
- **With Credential Guard, LSA secrets live in an isolated process (LSAIso)** that the normal OS
  can't read. `hashdump`/`lsadump` results will be incomplete; that is expected.
- **`hiberfil.sys` and `pagefile.sys` are not memory images.** Collect them with the disk image.
  Volatility 3 (2.28) can't parse hibernation files.

## Linux

| Tool | Notes |
|---|---|
| [AVML](https://github.com/microsoft/avml) (Microsoft, static binary) | No kernel module, no compilation. `sudo ./avml /mnt/linux_host.lime`. It can upload straight to the inbox (see [Upload](#upload)). Do **not** use `--compress`: Volatility can't read AVML's compressed format without converting it first (`avml-convert`). Use `.gz` instead if you need compression. |
| [LiME](https://github.com/504ensicsLabs/LiME) | Kernel module that must be built for the exact running kernel: `insmod lime.ko "path=/mnt/linux_host.lime format=lime"`. |
| Velociraptor `Linux.Memory.Acquisition` | Uses AVML. |

**Symbols are required.** Volatility can't analyse a Linux image without a symbol file (ISF) for the
exact kernel build. Windows symbols download automatically; Linux symbols don't. The analyst
prepares them, for example:

```bash
# On a machine with the same distro/kernel; Ubuntu ships debug kernels as linux-image-<ver>-dbgsym
dwarf2json linux --elf /usr/lib/debug/boot/vmlinux-<uname -r> | xz > <uname -r>.json.xz
scp <uname -r>.json.xz <worker>:/tmp/ && ssh <worker> 'sudo install -o volautolity -m 0640 /tmp/<uname -r>.json.xz /var/lib/volautolity/symbols/'
```

Alternatively, set `remote_isf_url` to a community symbol index. That fetches third-party data at
analysis time.

If no symbols match, the run still finishes. The `banners` table then shows which kernel the image is
from, and the `volautolity_runs` table records the failure.

## macOS

Modern Macs effectively can't be memory-imaged:
- Apple Silicon has no supported full physical-memory acquisition path for third parties.
- On Intel Macs it needs security features disabled.
- Upstream Volatility no longer actively maintains macOS support, and analysis needs symbols built
  from Apple's Kernel Debug Kit.

For macOS incidents, prioritise live-response triage (unified logs, process listings, persistence
locations) over memory images.

## Hypervisor-side acquisition

Taking memory from the hypervisor doesn't touch the guest, which is often the cleanest option.

| Platform | How | Upload |
|---|---|---|
| VMware ESXi / Workstation | Suspend the VM, or take a snapshot *including memory*. | The `.vmem` file (rename to `win_host.vmem`). |
| Hyper-V | Take a *standard* checkpoint; production checkpoints don't include memory. | The saved state (`.vmrs`/`.bin`) is not a format Volatility reads directly. Convert it to a raw image or crash dump with a tool that supports your Hyper-V version, and check the result locally with `vol -f <file> windows.info` before uploading. |
| KVM / libvirt / Proxmox | `virsh dump <domain> /path/linux_host.elf --memory-only --live` | The `.elf` core file. |
| VirtualBox | `VBoxManage debugvm <vm> dumpvmcore --filename=/path/win_host.elf` | The `.elf` core file. |

## Azure virtual machines

Azure has no customer-facing hypervisor memory snapshot: disk snapshots don't contain RAM. The
options, in order of preference:

1. **Run Command, then acquire inside the guest and upload directly to the inbox.**
   - Needs the VM agent running and a role allowing `Microsoft.Compute/virtualMachines/runCommand/action`,
     for example *Virtual Machine Contributor*.
   - *Action* run commands (`az vm run-command invoke`) time out after about 90 minutes and return
     only a few KB of output.
   - For large VMs use a *managed* run command (`az vm run-command create --async-execution
     --timeout-in-seconds ...`).

   Windows example, assuming you staged `winpmem` and `azcopy` from a location you control, with
   known hashes:
   ```powershell
   $ErrorActionPreference = 'Stop'
   $out  = 'D:\win_' + $env:COMPUTERNAME + '_' + (Get-Date -Format yyyyMMdd) + '.raw'   # D: = temp disk
   & C:\IR\winpmem_mini_x64.exe $out
   $hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
   & C:\IR\azcopy.exe copy $out ('<container-url>/' + (Split-Path $out -Leaf) + '<sas>') --metadata "sha256=$hash"
   Remove-Item $out
   ```
   Linux example. AVML uploads by itself; check its hash first:
   ```bash
   az vm run-command invoke -g <rg> -n <vm> --command-id RunShellScript --scripts '
     set -e
     curl -sSLo /mnt/avml https://github.com/microsoft/avml/releases/download/<version>/avml
     echo "<published-sha256>  /mnt/avml" | sha256sum -c
     chmod +x /mnt/avml
     uname -r > /mnt/kernel.txt
     /mnt/avml --sas-url "<container-url>/linux_$(hostname)_$(date +%Y%m%d).lime<sas>" --delete /mnt/linux_mem.lime'
   ```
2. **Defender for Endpoint live response**, if the VM is onboarded. Same flow as on-prem Windows.
3. **Last resort for Windows: an NMI-triggered crash dump.**
   - Use `az serial-console send nmi -g <rg> -n <vm>` (boot diagnostics/serial console must be enabled).
   - It only produces a full dump if the guest was configured beforehand:
     `HKLM\SYSTEM\CurrentControlSet\Control\CrashControl` with `CrashDumpEnabled=1` and
     `NMICrashDump=1`, and a page file at least as large as RAM.
   - **It reboots the VM**, so some volatile state is lost.
   - Collect `C:\Windows\MEMORY.DMP` afterwards and upload it as `win_<host>.dmp`.

## Upload

`<container-url>` and `<sas>` come from the analyst: `tofu output -raw setup_and_instructions`.

**1. Hash the image** (the worker verifies it if you pass it along):
```powershell
(Get-FileHash .\win_host.raw -Algorithm SHA256).Hash.ToLower()     # Windows
```
```bash
sha256sum linux_host.lime                                           # Linux
```

**2. Optionally compress it.** Memory usually shrinks 3–5×, which matters on slow links.
- Linux: `pigz -k linux_host.lime` gives `linux_host.lime.gz`.
- Windows: `7z a -tgzip win_host.raw.gz win_host.raw`, or a `.zip` containing a single image.
- Avoid PowerShell `Compress-Archive` for large files: Windows PowerShell 5.1 can't handle files over 2 GB.
- The `sha256` you pass is always the hash of the **uncompressed** image.

**3. Upload with [AzCopy](https://learn.microsoft.com/azure/storage/common/storage-use-azcopy-v10).**
It's parallel and can resume (`azcopy jobs resume`):
```powershell
azcopy copy .\win_host.raw.gz "<container-url>/win_host.raw.gz<sas>" --metadata "sha256=<hash>" --put-md5
# on a shared customer link, add e.g. --cap-mbps 200
```
From Linux with AVML, acquire and upload in one go:
```bash
sudo ./avml --sas-url "<container-url>/linux_host.lime<sas>" --delete linux_host.lime
```
If you're in the analyst's tenant and have *Storage Blob Data Contributor* on the account:
```bash
az storage blob upload --auth-mode login --account-name <account> --container-name <container> \
  --file win_host.raw --name win_host.raw --metadata sha256=<hash>
```

**Treat the SAS URL like a password.**
- Share it over a secure channel, not in a ticket or email thread.
- It can create and overwrite blobs, but it can't read, list or delete them.
- It expires after the configured validity (7 days by default).
- To revoke it early, the analyst rotates the storage account key:
  `az storage account keys renew --key primary ...`.

## After the upload

The worker notices the new blob within about 30 seconds and processes images one at a time, oldest
first. It sets each blob's metadata field `volautolity_status` to `processing`, then `done` or `failed`.

In Azure Data Explorer each image gets its own database. Three tables help you check a run:
- **`volautolity_image`:** name, size, SHA-256, OS and timings.
- **`volautolity_runs`:** every plugin with its status, row count and error.
- **`banners`:** only present when no OS profile matched (e.g. missing Linux symbols).

If you supplied a `sha256` and it doesn't match the image the worker received, the blob is marked
`failed` with `volautolity_error = sha256 mismatch...`. Re-upload in that case.
