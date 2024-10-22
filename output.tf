## Networking Outputs
output "whitelisted-ip" {
  value       = data.http.myip
  description = "The IP address that can connect lab interfaces. Specified when terraforming by the user."
}

output "setup_and_instructions" {
  value     = <<EOS
-------------------------
Virtual Machine ${azurerm_linux_virtual_machine.linux_vm.computer_name}
-------------------------
Login:            az login
Set subscription: az account set --subscription "${data.azurerm_subscription.current.display_name}"
Upload:           az storage blob upload --account-name "${azurerm_storage_account.sa.name}" --container-name "${azurerm_storage_container.sc.name}" --file <PathToLocalFile> --auth-mode login --account-key "${azurerm_storage_account.sa.primary_access_key}"
Verify upload:    az storage blob list --account-name "${azurerm_storage_account.sa.name}" --container-name "${azurerm_storage_container.sc.name}" --output table --auth-mode login --account-key "${azurerm_storage_account.sa.primary_access_key}"
Storage URI   

----------------------------------------------
Upload using SAS token (still buggy - WIP):
----------------------------------------------
az storage blob upload --account-name "${azurerm_storage_account.sa.name}" --container-name "${azurerm_storage_container.sc.name}" --file <PathToYourLocalFile> --name <win_mycompany_DDMMYY.raw> --sas-token   ${data.azurerm_storage_account_sas.sasas.sas}

--------------------------
Sign into the machine:
--------------------------
"ssh -i ${local.path_to_private_key} ${var.linux-username}@${azurerm_public_ip.publicip.ip_address}"
EOS
  sensitive = true
}