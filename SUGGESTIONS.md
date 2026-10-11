# Suggestions, answers and open questions

This file goes with the `refactor/opentofu-python-pipeline` branch. It contains:
1. Answers to the questions asked.
2. What was found in the old code.
3. Suggestions that were not implemented.
4. Open questions that need a decision from you.

**Nothing has been deployed.** All checks ran locally (see *Verification* at the end).

---

## 1. Your questions

### Terraform to OpenTofu
Done. The HCL barely changes, since OpenTofu reads the same `terraform {}` block and providers. What
changed:

- **OpenTofu `>= 1.10`, `azurerm ~> 5.0`.** azurerm 5.x is current, and the 5.0 breaking changes
  were applied: container/blob IDs, and explicit resource provider registration.
  - `required_version` now refers to the OpenTofu version.
  - 1.10 is needed for `lifecycle` inside `removed` blocks.
- **OpenTofu features in use:**
  - Variables in the `backend` block (early evaluation), so no environment values are committed.
  - `removed { lifecycle { destroy = false } }` blocks, so moving the state-storage resources to
    `cfg/bootstrap` forgets them without deleting them.
- **The state backend bootstrap is now its own root module** (`cfg/bootstrap`). Before, the config
  managed the storage account holding its own state, so a `destroy` would have deleted the state.
- **GitHub workflows:**
  - Switched to `opentofu/setup-opentofu@v2`.
  - Log in with OIDC, so no client secret is stored in GitHub.
  - New `ci.yml`: fmt/validate, Python tests, shellcheck.
- **Migrating a live deployment:** `tofu init`, then `tofu plan`. No state surgery is needed, because
  OpenTofu translates `registry.terraform.io` provider addresses itself. The plan removes the old
  SP/Ansible/role assignments and replaces the VM.

### The bash scripts ("outdated and not efficient")
You were right on both counts. I replaced them rather than patching them. These are the bugs and
inefficiencies I found:

| Problem in the old scripts | Effect |
|---|---|
| All ~60 `vol` commands launched with `&` per image, and several images at once | RAM/CPU thrash: the "too many images at the same time" issue in the README |
| Every `vol` run re-did layer stacking and the kernel/PDB scan | The same expensive step repeated ~60 times per image |
| blobfuse + `inotifywait` | Never fires for blobs uploaded from elsewhere: the "trigger by copying/moving the file" workaround |
| `strings ... > strings.txt && strings -el ... > strings.txt` | The UTF-16 pass overwrote the ASCII pass |
| `"echo 'Starting to run Volatility commands..."` | Unterminated quote inside `eval` |
| `--yara-rules "https://..."` | Not a Volatility option: the URL was treated as rule text, so YARA never worked (`--yara-file` is correct) |
| `windows.suspicious_threads.SupsiciousThreads` and other old names (`windows.malfind`, `windows.hashdump`, ...) | Typo, plus deprecated aliases whose removal dates have passed (2026-06/09) |
| Hand-written table schemas with wrong types (`envars.Value:int32`, `info.Value:int32`, `filescan.Size:int32`, typo `Fileoutputished`) | Silently null columns |
| DumpFiles and HiveList each run twice | Wasted passes over the image |
| `taskhost_triage` built from `pslist` while `pslist` was still running in the background | Race condition |
| Service principal secret on the `python3 file_ingestion.py` command line | Visible to anyone who can run `ps` |
| A cron job every minute, `processed.txt` on the blobfuse mount, no locking | Duplicate processing possible |
| `monitor_output_directory` (inotify) never exits | One leaked watcher per image |

### "Would this be better as a C++ project, using the API calls instead of bash?"
**No to C++, yes to "API calls instead of bash" — done in Python.**
- **Volatility 3 is a Python framework.** Its API *is* Python. C++ would still have to start Python,
  or embed CPython, to run any plugin, so there's nothing to gain.
- **The Azure SDKs are first-class in Python.** azure-kusto-ingest, azure-mgmt-kusto, azure-storage-blob
  and azure-identity are all used. There is no official C++ Kusto ingest SDK.
- **The bottlenecks were never the glue language.** They were the repeated kernel scans,
  uncontrolled parallelism, blobfuse I/O and 5-minute ingestion batching. All four are fixed:
  - The kernel config is saved once and reused.
  - A bounded worker pool runs core tables first.
  - The image is downloaded to local disk with parallel range requests.
  - The ingestion batching policy is set to 20 s.
- **Next step, if needed:** run plugins in-process through the Volatility API (as volshell does), to
  shave per-process start-up. Measure first: with the saved config, start-up is already small next to
  plugin run time, and separate processes give crash isolation and real parallelism.

The new code is object-oriented, as requested in `TEMP.suggestions.md`:
- `Task` → `VolatilityTask` / `HiveListTask` / `DumpFilesTask` / ...
- `TaskScheduler`
- `ResultSink` → `AdxSink` / `LocalSink`
- `CsvNormalizer`, `BlobInbox`, `InboxWatcher`, `DumpPipeline`

### "Update the script to take into account all the new modules from Volatility"
Done against Volatility **2.28.2** (2026-09-17), which is pinned in `requirements.txt`.
- **Windows:** 84 plugins, up from about 65 in the bash script. Linux (48) and macOS (25) are new
  altogether.
- **The full table** is in [docs/PLUGINS.md](docs/PLUGINS.md), including what is deliberately not
  run and why.
- **`tests/test_catalog.py` checks the catalog against the installed Volatility:**
  - every name exists,
  - no name is a deprecated alias,
  - no plugin has an unmet required option.

  The next Volatility upgrade therefore fails in CI instead of silently losing tables.

### "Do we need Ansible?"
**No.** It was used to run a playbook on the VM itself, over SSH, from a `null_resource` with a
`timestamp()` trigger. That combination caused the README's "run apply twice", "null_resource takes
forever" and "remote-exec provisioner error" issues. It's replaced by:
- **cloud-init** (`custom_data`): runs on first boot, with no SSH from your machine during apply.
- **`VolAutolity/deploy/setup.sh`:** idempotent, safe to re-run, and verifies the hashes of
  third-party downloads.
- **A hardened systemd unit.**

### "Do we need all we have here to make this go to ADX?"
No. What remains is the minimum for this design:

| Kept | Why |
|---|---|
| Resource group, VNet/subnet/NIC/public IP/NSG | VM networking. The public IP gives the VM explicit outbound access (packages, symbols, ADX), independent of Azure's default-outbound changes; SSH is for troubleshooting only. |
| Storage account with `inbox` + `results` containers | Uploads in, results out |
| ADX cluster | The analysis store. Databases are created per image by the worker. |
| Worker VM | Runs Volatility |
| One user-assigned identity + 3 role assignments + 1 ADX principal assignment | Least privilege |
| Workbook | Optional, but it's the UI |

| Removed | Why |
|---|---|
| App registration + service principal + client secret + `AzGrp` group | Replaced by the managed identity. The group was unused. |
| VM **Owner** *and* **Contributor** on the whole subscription | Massively over-privileged |
| `azurerm_role_assignment.example` | Assigned a *client ID* as a *User*: broken, and not needed |
| `null_resource` + Ansible, `local_file` x3 (`ansible_vars`, `adx_vars_bash.sh` with the secret, `ip.txt`) | cloud-init |
| blobfuse (v1 is retired), the 32 GB ramdisk (larger than the VM's 16 GB RAM), `regripper`/`reglookup` (installed, never used), f-block plugins (downloaded, never run) | Unused or replaced |
| NSG rule `HTTP-In` (80) | Nothing listens on port 80 |
| Account-level SAS with read, hard-coded 2024-01-01 → 2025-01-01 (expired) | Container-scoped upload-only SAS with relative validity |

To go even leaner, see suggestions 4 and 5 below.

### Security issues fixed that you didn't ask about
1. **The upload container was public** (`container_access_type = "blob"`). Anyone with the URL of a
   memory dump could download it anonymously. It's now private, and public blob access is disabled
   on the account.
2. **The VM was Owner of the subscription,** and the SP secret sat in plain text in
   `VolAutolity/adx_vars_bash.sh` on your machine and on the VM.
3. **The `cfg/` move broke the paths** to `Ansible/` and `VolAutolity/` (`${path.module}/Ansible`).
4. **The workflows couldn't have worked:** they referenced a non-existent step output, read
   `~/.ssh/id_rsa.pub` on the runner, and whitelisted the runner's IP for SSH.
5. **`variables.auto.tfvars` (subscription ID) and the backend names were committed.** Both are now
   git-ignored; there's a `.example` and backend variables. The subscription ID is still in git
   history. It isn't a credential, but rewrite history if that matters to you.

---

## 2. Suggestions (not implemented), roughly by value

1. **Turn on OpenTofu state encryption.** The state contains storage account keys and the SAS token.
   It can be enabled without code changes, through an environment variable (passphrase ≥ 16 chars,
   kept in a password manager):
   ```powershell
   $env:TF_ENCRYPTION = @'
   key_provider "pbkdf2" "main" { passphrase = "<from your vault>" }
   method "aes_gcm" "main" { keys = key_provider.pbkdf2.main }
   method "unencrypted" "migrate" {}
   state { method = method.aes_gcm.main
           fallback { method = method.unencrypted.migrate } }
   plan  { method = method.aes_gcm.main
           fallback { method = method.unencrypted.migrate } }
   '@
   ```
   After the first apply, drop the fallback and add `enforced = true` in code.
2. **Commit `.terraform.lock.hcl`.** It is in `.gitignore` today. The lock file pins provider
   checksums, which is supply-chain protection. Generate it for all platforms with
   `tofu providers lock -platform=linux_amd64 -platform=windows_amd64 -platform=darwin_arm64`.
3. **ADX cost.** For short-lived labs, `adx_sku_name = "Dev(No SLA)_Standard_E2a_v4"` with
   `adx_capacity = 1` is a fraction of 4× `Standard_D11_v2`. Microsoft's SKU guide ranks Dv2 last
   among the compute-optimized SKUs.
4. **Run the worker on demand.**
   - Options: an Azure Container Apps Job (event-driven, scale to zero) or Azure Batch instead of an
     always-on VM.
   - At minimum, add `azurerm_dev_test_global_vm_shutdown_schedule`.
   - The pipeline is already a plain CLI (`python -m volautolity process <file>`), so it can go into a
     container image.
5. **Event Grid → Storage Queue** instead of polling, if 30 s of pick-up latency matters. Polling was
   kept because it needs no extra resources and survives restarts.
6. **Tighter SAS.**
   - Test a *create-only* SAS (no `w`) with azcopy and AVML. If chunked uploads work with `c` alone,
     uploaders can no longer overwrite existing evidence.
   - Optionally IP-restrict the SAS (`sip`).
   - Long term: user-delegation SAS (signed with Entra ID), then `shared_access_key_enabled = false`
     on the account. That needs the SAS to be issued with `az` instead of the data source.
7. **Encryption extras** (some force replacement, so do them on a fresh lab):
   - Storage `infrastructure_encryption_enabled`, or a customer-managed key in Key Vault.
   - ADX `double_encryption_enabled`.
   - VM `encryption_at_host_enabled` (needs the `EncryptionAtHost` feature registered).
8. **Private endpoints** for storage and ADX, plus ADX `allowed_ip_ranges`, if the threat model
   includes the public endpoints.
9. **Workbook next steps.** The rebuild itself is done (see section 4).
   - **Materialise findings.** After ingestion, the worker could run `.set-or-replace findings <|
     AllFindings()`. The Overview would then read a small table instead of re-running every detector
     (faster to load, and a much smaller workbook: three items currently embed the full detector library).
     It also enables cross-image hunting with `union database("*").findings`.
   - **Fleet baselines.** Many rules say "a single outlier is the signal". A cross-database view (same
     value on N images vs one) would turn those into real baselines. This needs question 2 below.
   - **Execute every query against real data.** Run the
     [Kusto emulator](https://learn.microsoft.com/azure/data-explorer/kusto-emulator-overview) in CI
     with the test image's tables loaded. Docker Desktop was installed here but its engine wouldn't
     start, so the queries are validated semantically, and the main detectors were replayed in Python
     against the real image.
10. **YARA rules.** A single Konni backdoor rule isn't much coverage. Use a maintained pack (e.g.
    YARA Forge "core", Elastic protections-artifacts), pinned by commit and SHA-256 like now.
11. **IoC regexes.** A configurable pattern list for `windows.vadregexscan` / `regexscan` (C2
    domains, wallet addresses, ...).
12. **Data retention.**
    - A storage lifecycle policy to delete images and results after N days.
    - An ADX retention policy per database.

    Memory images contain personal data and credentials.
13. **Shipping the app: now a priority.**
    - It travels inline in cloud-init: about 57 KB of the 64 KB limit, with `schemas.json` added. A
      precondition guards the limit.
    - The next feature will not fit. Upload the app as a blob (an `archive_file` zip plus
      `azurerm_storage_blob`), pass its SHA-256 in the env file, and have `setup.sh` download it with
      the managed identity (IMDS token + blob GET) and verify the hash.
    - Bonus: code changes would no longer replace the VM.
14. **Housekeeping:**
    - Move `sample_vol_ouput/` (typo) to `VolAutolity/tests/fixtures/`, or delete it.
    - Add Dependabot/Renovate for pip, GitHub Actions and providers.
    - Add pre-commit with `tofu fmt`, ruff and shellcheck.

---

## 3. Open questions (I continued with the defaults in brackets)

1. **Backslashes.** *Resolved:* the worker now decodes Volatility's escaping, and the new workbook
   expects single backslashes. Databases from the old bash runner still have doubled ones.
2. **One database per image or one database overall?** A single database with a `DumpName` column
   allows cross-image queries ("which hosts ran this binary?") and the worker would need no ARM
   rights. [kept per image, as in the README]
3. **ADX SKU/capacity defaults:** keep `Standard_D11_v2` × 4? [kept, now as variables]
4. **Live deployments.** Is there one built from the old code, or are all labs short-lived? The
   `removed` blocks and the VM replacement only matter for a live one.
5. **State encryption:** enable by default (suggestion 1)? It means someone must own the passphrase.
6. **Commit the provider lock file?** [left ignored, as you had it]
7. **YARA rule sources** you trust? [kept the original Konni rule, now pinned]
8. **Uploads.** Is 7 days the right SAS validity for external uploaders? Should the SAS be
   IP-restricted?
9. **Results container retention.** It holds dumped files, which can be live malware. Who should have
   access, and for how long?
10. **macOS:** keep it in scope? Upstream has stopped maintaining it, and acquisition on modern Macs
    is impractical.
11. **Workbook:** *Done* (section 4). Open follow-ups:
    - Which detectors are too noisy or too quiet in your environment?
    - Should Info-level review lists (all Run keys, all tasks) count towards the process score?
12. **The work is on a local branch** `refactor/opentofu-python-pipeline` with conventional, atomic
    commits. Nothing is pushed. Want a PR?
13. **Community plugin:** the Immersive Labs `cobaltstrike.py` no longer loads on Volatility 2.28
    (it needs `pslist` 2.x). Port it, find a maintained alternative, or drop it? [dropped from the
    defaults; the install mechanism stays]

---

## 4. The workbook rebuild

**Research.** Two research passes went into it. They drew on these sources:
- SANS Hunt Evil, Sigma, Elastic, LOLBAS, MITRE ATT&CK, The DFIR Report;
- CISA ransomware advisories, loldrivers.io, Microsoft documentation;
- the Volatility plugin sources.

The result is 15 tabs and 67 queries, built from 15 detectors. Details are in
[README → The triage workbook](README.md#the-triage-workbook) and [workbook/README.md](workbook/README.md).

**Real-data run.** The pipeline ran end to end against the Volatility project's own Windows 10 (19041)
test image. That surfaced two production bugs, both now fixed:
- **Missing cache directory.** `--cache-path` must exist. Without it every image would have failed at
  bootstrap on the VM.
- **Doubled backslashes.** Volatility's CSV escaping was not decoded.

**False-positive calibration on that clean image.** These cases are now handled:
- **Look-alike process names.** 20 legitimate Windows binaries look like core process names under the
  similarity metric (logonui ~ winlogon, synchost ~ svchost, ...). They are now allowlisted, using a list
  measured against every `.exe` in `C:\Windows`. Similarity also only counts outside system directories,
  and an explicit typosquat list covers the 7 known typos the metric misses.
- **Early-boot parentage.** The Registry process is created 7 s *before* System's recorded CreateTime, so
  PID 4 is always accepted as a parent.
- **lsass handles.** System holds full-access handles to lsass, so it is allowlisted.
- **ldrmodules.** Processes with unreadable loader lists (SearchApp, msedgewebview2) report almost every
  DLL as unlinked; they are skipped. Resource-only DLLs are Low.
- **System calls.** All 156 direct-syscall hits came from msedge (Chromium). Browsers and JIT/AV
  processes are down-ranked.

After calibration the clean image yields **no Medium-or-higher findings** in the replayed detectors.

**Data model.**
- **Declared types.** Tables now use Volatility's declared column types (`schemas.json`, generated and
  checked against the installed Volatility in the tests).
- **Tables always exist.** They are created up front, so failed plugins never break workbook queries.
- **Row order.** Every row carries `VolRow` (Volatility's output order).

**Removed on purpose.** The old Passwords tab built links that sent NT hashes to a third-party website
(ntlm.pw). Customer credentials must not leave the investigation.

**Size.** The workbook JSON is 723 KB, because each query is self-contained. Azure's exact limit for
workbook content could not be verified (the web search budget for this session ran out). Materialising
findings (suggestion 9) would shrink it a lot.

---

## Verification
- `tofu validate` passes for `cfg` and `cfg/bootstrap` with azurerm 5.x. `tofu fmt` is clean.
- The cloud-init template was rendered and parsed as YAML, and the embedded files decode back intact.
  It is ~57 KB with schemas; the limit is 64 KB.
- There are 34 Python tests, including:
  - an end-to-end pipeline run against a fake `vol` binary;
  - watcher behaviour;
  - the catalog and `schemas.json` checks against the real Volatility 2.28.2.
- The pipeline ran against a real Windows 10 memory image. All produced tables matched the generated
  schemas.
- All 69 workbook queries (67 plus 2 parameter queries) pass Microsoft's KQL semantic analyzer against
  the table schemas. CI repeats this.
- **Not done:**
  - no `tofu plan`/`apply` against Azure;
  - the workbook queries were not *executed* (no ADX or emulator available here);
  - no shellcheck locally (CI runs it).

  Watch the first real deployment with `journalctl -u volautolity -f`, and open the workbook on the
  first processed image.
