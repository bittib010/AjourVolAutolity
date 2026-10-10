## Networking Outputs
output "whitelisted-ip" {
  value       = local.operator_ip
  description = "The IP address allowed to SSH to the worker VM."
}

output "adx_cluster_uri" {
  value       = azurerm_kusto_cluster.adxc.uri
  description = "Query endpoint. Each memory image gets its own database, named after the file."
}

output "setup_and_instructions" {
  value     = <<EOS
-------------------------
Upload memory images
-------------------------
Name files <os>_<anything>.<ext>, e.g. win_mycompany_130224.raw (os: win | linux | mac).
Accepted extensions: ${join(", ", var.dump_extensions)}

Tenant users (needs "Storage Blob Data Contributor" on ${azurerm_storage_account.sa.name}):
  az login
  az account set --subscription "${data.azurerm_subscription.current.display_name}"
  az storage blob upload --auth-mode login --account-name "${azurerm_storage_account.sa.name}" --container-name "${azurerm_storage_container.sc.name}" --file <PathToLocalFile> --name <win_mycompany_DDMMYY.raw>

Anyone with this link (upload-only SAS, valid ${var.upload_sas_validity_hours}h; azcopy is much faster for large files):
  azcopy copy "<PathToLocalFile>" "${azurerm_storage_account.sa.primary_blob_endpoint}${azurerm_storage_container.sc.name}/<win_mycompany_DDMMYY.raw>${data.azurerm_storage_account_blob_container_sas.upload.sas}"

Processing status is written to each blob's metadata (volautolity_status = processing | done | failed):
  az storage blob list --auth-mode login --account-name "${azurerm_storage_account.sa.name}" --container-name "${azurerm_storage_container.sc.name}" --include m --query "[].{name:name, status:metadata.volautolity_status, db:metadata.volautolity_database}" -o table

-------------------------
Query
-------------------------
Cluster:  ${azurerm_kusto_cluster.adxc.uri}
Per image, the table volautolity_runs lists every plugin with status, row count and error.

--------------------------
Troubleshooting on the worker ${azurerm_linux_virtual_machine.linux_vm.computer_name}
--------------------------
ssh ${var.linux-username}@${azurerm_public_ip.publicip.ip_address}
  sudo tail -f /var/log/cloud-init-output.log   # first-boot setup
  journalctl -u volautolity -f                  # the worker service
EOS
  sensitive = true
}
