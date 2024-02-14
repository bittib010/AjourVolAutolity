resource "azurerm_linux_virtual_machine" "linux_vm" {
  name                            = "${var.investigator_initials}-linux-vm"
  computer_name                   = var.linux-name
  resource_group_name             = azurerm_resource_group.myrg.name
  location                        = azurerm_resource_group.myrg.location
  size                            = var.linux-size
  disable_password_authentication = true
  admin_username                  = var.linux-username
  network_interface_ids           = [azurerm_network_interface.ni.id]

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 80
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  admin_ssh_key {
    username   = var.linux-username
    public_key = file(var.path_to_public_key)
  }

  identity {
    type = "SystemAssigned"
  }
  depends_on = [ 
    azurerm_kusto_cluster.adxc # Depends on this as Volatility will start running sooner than ADX is ready to ingest
    ]
}

# Provision using Ansible
resource "null_resource" "ansible_provisioning" {
  triggers = {
    always_run = "${timestamp()}"
  }
  depends_on = [azurerm_linux_virtual_machine.linux_vm]

  connection {
    type        = "ssh"
    host        = azurerm_public_ip.publicip.ip_address
    user        = var.linux-username
    private_key = file(var.path_to_private_key)
  }

  provisioner "file" {
    source      = "${path.module}/Ansible"
    destination = "/home/${var.linux-username}/"
  }

  provisioner "file" {
    source      = "ip.txt"
    destination = "/home/${var.linux-username}/ip.txt"
  }

  provisioner "file" {
    source      = "VolAutolity"
    destination = "/home/${var.linux-username}/"
  }

  provisioner "remote-exec" {
    inline = [
      "sudo apt-get -qq update >/dev/null && sudo apt-get -qq install -y ansible sshpass >/dev/null",
      "ansible-playbook -v /home/${var.linux-username}/Ansible/ansible_playbook.yml",
      "sudo cp /home/${var.linux-username}/VolAutolity/sample/* ${var.mounting_point}"
    ]
  }
}

