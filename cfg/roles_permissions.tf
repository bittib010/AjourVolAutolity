resource "azurerm_user_assigned_identity" "mi" {
  resource_group_name = azurerm_resource_group.myrg.name
  location            = azurerm_resource_group.myrg.location
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-identity"
}

resource "azurerm_role_assignment" "name" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.mi.principal_id

}

resource "azurerm_role_assignment" "vm_role" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_linux_virtual_machine.linux_vm.identity[0].principal_id
  depends_on           = [azurerm_linux_virtual_machine.linux_vm]
}


resource "azurerm_role_assignment" "example" {
  scope                = azurerm_resource_group.myrg.id
  role_definition_name = "Contributor"
  principal_id         = data.azurerm_client_config.current.client_id
  principal_type       = "User"
}


resource "azurerm_kusto_cluster_principal_assignment" "adx_vm_viewer" {
  #https://learn.microsoft.com/en-us/azure/data-explorer/kusto/access-control/role-based-access-control
  resource_group_name = azurerm_resource_group.myrg.name
  cluster_name        = azurerm_kusto_cluster.adxc.name
  name                = "principalAssignmentName"
  principal_id        = azurerm_linux_virtual_machine.linux_vm.identity[0].principal_id
  principal_type      = "App"
  role                = "AllDatabasesAdmin"
  tenant_id           = data.azurerm_client_config.current.tenant_id
}


resource "azurerm_kusto_cluster_principal_assignment" "adx_user_admin" {
  resource_group_name = azurerm_resource_group.myrg.name
  cluster_name        = azurerm_kusto_cluster.adxc.name
  name                = "UserAdminRoleADX"
  principal_id        = data.azurerm_client_config.current.object_id
  principal_type      = "User"
  role                = "AllDatabasesAdmin"
  tenant_id           = data.azurerm_client_config.current.tenant_id
}



resource "azurerm_kusto_cluster_principal_assignment" "adx_sp" {
  resource_group_name = azurerm_resource_group.myrg.name
  cluster_name        = azurerm_kusto_cluster.adxc.name
  name                = "UserAdsdffdminRoleADX"
  principal_id        = azuread_service_principal.aad_sp.application_id
  principal_type      = "App"
  role                = "AllDatabasesAdmin"
  tenant_id           = data.azurerm_client_config.current.tenant_id
}