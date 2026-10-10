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
9. **Workbook.**
   - Add tabs for the new tables: consoles/cmdscan, amcache, scheduled_tasks, svcdiff, pebmasquerade,
     system-call checks, etwpatch.
   - Keep the KQL in `.kql` files in the repo and template them in. That's easier to review than
     the escaped JSON.
   - A `volautolity_runs` health tab.
10. **YARA rules.** A single Konni backdoor rule isn't much coverage. Use a maintained pack (e.g.
    YARA Forge "core", Elastic protections-artifacts), pinned by commit and SHA-256 like now.
11. **IoC regexes.** A configurable pattern list for `windows.vadregexscan` / `regexscan` (C2
    domains, wallet addresses, ...).
12. **Data retention.**
    - A storage lifecycle policy to delete images and results after N days.
    - An ADX retention policy per database.

    Memory images contain personal data and credentials.
13. **Shipping the app.** It travels inline in cloud-init (~46 KB of the 64 KB limit; a precondition
    guards it). If it grows, publish a release artifact and download it with a pinned hash.
14. **Housekeeping:**
    - Move `sample_vol_ouput/` (typo) to `VolAutolity/tests/fixtures/`, or delete it.
    - Add Dependabot/Renovate for pip, GitHub Actions and providers.
    - Add pre-commit with `tofu fmt`, ruff and shellcheck.

---

## 3. Open questions (I continued with the defaults in brackets)

1. **Backslashes.** Volatility's CSV writer doubles them (`C:\\Windows`), and the workbook's
   registry tree query depends on that. Normalise to single backslashes and update the workbook?
   [kept doubled]
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
11. **Workbook:** should I extend it with the new tables (suggestion 9)?
12. **The work is on a local branch** `refactor/opentofu-python-pipeline` with conventional, atomic
    commits. Nothing is pushed. Want a PR?
13. **Community plugin:** the Immersive Labs `cobaltstrike.py` no longer loads on Volatility 2.28
    (it needs `pslist` 2.x). Port it, find a maintained alternative, or drop it? [dropped from the
    defaults; the install mechanism stays]

---

## Verification
- `tofu validate` passes for `cfg` and `cfg/bootstrap` with azurerm 5.x. `tofu fmt` is clean.
- The cloud-init template was rendered and parsed as YAML (45.7 KB decoded; limit 64 KB), and the
  embedded files decode back intact.
- There are 27 Python tests, including:
  - an end-to-end pipeline run against a fake `vol` binary: saved-config reuse, hive fan-out,
    retry, status tables, SHA-256;
  - watcher behaviour on hash mismatch, interruption and crashes;
  - the catalog check against the real Volatility 2.28.2, with `[full]` extras.

  They pass with and without the Azure SDKs installed.
- **Not done:**
  - no `tofu plan`/`apply` against Azure,
  - no run against a real memory image,
  - no shellcheck locally (CI runs it).

  The first real deployment should be watched with `journalctl -u volautolity -f`.
