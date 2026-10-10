locals {
  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    env_file = join("\n", [for k, v in local.app_env : "${k}=\"${v}\""])
    # Normalise line endings: a CRLF checkout on Windows must not ship CRLF shell scripts to Linux.
    app_files = { for f in local.app_files : f => base64gzip(replace(file("${local.app_root}/${f}"), "\r\n", "\n")) }
  })
}

resource "azurerm_linux_virtual_machine" "linux_vm" {
  name                            = "${var.investigator_initials}-linux-vm"
  computer_name                   = var.linux-name
  resource_group_name             = azurerm_resource_group.myrg.name
  location                        = azurerm_resource_group.myrg.location
  size                            = var.linux-size
  disable_password_authentication = true
  admin_username                  = var.linux-username
  network_interface_ids           = [azurerm_network_interface.ni.id]
  tags                            = var.tags

  # cloud-init installs and starts the worker on first boot. This replaces the
  # null_resource + SSH provisioners + Ansible: no SSH from the operator's
  # machine during apply, and nothing re-runs on every apply.
  # Note: custom_data is ForceNew, so changing the app code replaces the VM.
  custom_data = base64encode(local.cloud_init)

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = var.os_disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # Trusted Launch (Gen2 image): secure boot + vTPM protect the worker's boot chain.
  secure_boot_enabled = true
  vtpm_enabled        = true

  admin_ssh_key {
    username   = var.linux-username
    public_key = local.ssh_public_key
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.mi.id]
  }

  lifecycle {
    precondition {
      condition     = length(local.cloud_init) <= 65535
      error_message = "cloud-init payload exceeds Azure's 64 KB custom_data limit; ship the app as a release artifact instead of inline."
    }
  }

  depends_on = [
    # The service starts working as soon as the VM boots, so its permissions must already exist.
    azurerm_role_assignment.mi_blob_contributor,
    azurerm_role_assignment.mi_cluster_contributor,
    azurerm_kusto_cluster_principal_assignment.mi_admin,
  ]
}
