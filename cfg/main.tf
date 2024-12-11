# Create a random ID for unique resource names
resource "random_id" "randomId" {
  byte_length = 4
}

# Create a resource group
resource "azurerm_resource_group" "myrg" {
  name     = "${var.investigator_initials}-${random_id.randomId.hex}-rg"
  location = var.resource_group_location
  tags = {
    "deletiondate" = local.deletion_date
  }
}

resource "local_file" "ansible_vars" {
  content  = <<-EOF
    azure_storage_account_name: "${azurerm_storage_account.sa.name}"
    azure_storage_account_key: "${azurerm_storage_account.sa.primary_access_key}"
    azure_storage_container_name: "${azurerm_storage_container.sc.name}"
    linux_username: "${var.linux-username}"
    dump_path: "${var.mounting_point}"
    project_path: "/home/${var.linux-username}/${var.project_path}"
  EOF
  filename = "${path.module}/Ansible/ansible_vars.yml"
}

data "azuread_client_config" "current" {}

resource "azuread_application" "aad_app" {
  display_name = "AzApp"
  owners       = [data.azuread_client_config.current.object_id]
}

resource "azuread_group" "example" {
  display_name     = "AzGrp"
  security_enabled = true
}

resource "azuread_service_principal" "aad_sp" {
  client_id                    = azuread_application.aad_app.client_id
  app_role_assignment_required = false
  owners                       = [data.azuread_client_config.current.object_id]
}

resource "azuread_service_principal_password" "aad_sp_pass" {
  service_principal_id = azuread_service_principal.aad_sp.object_id
}

resource "azurerm_role_assignment" "sprole" {
  # https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
  #scope                = azurerm_kusto_cluster.adxc.id
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Owner"
  principal_id         = azurerm_linux_virtual_machine.linux_vm.identity.0.principal_id
}

data "azurerm_client_config" "current" {
}

data "azurerm_subscription" "current" {
}

resource "local_file" "adx_vars_bash" {
  content  = <<-EOF
    TENANT_ID="${data.azurerm_client_config.current.tenant_id}"
    cluster_ingestion_uri="${azurerm_kusto_cluster.adxc.data_ingestion_uri}"
    cluster_name="${azurerm_kusto_cluster.adxc.name}"
    resource_group_name="${azurerm_resource_group.myrg.name}"
    azurerm_location="${azurerm_resource_group.myrg.location}"
    CLIENT_ID="${azuread_service_principal.aad_sp.client_id}"
    CLIENT_SECRET="${azuread_service_principal_password.aad_sp_pass.value}"
    PROJECT_ROOT="/home/${var.linux-username}/${var.project_path}"
  EOF
  filename = "${path.module}/VolAutolity/adx_vars_bash.sh"
}

resource "local_file" "ip" {
  content  = azurerm_linux_virtual_machine.linux_vm.public_ip_address
  filename = "ip.txt"
}
