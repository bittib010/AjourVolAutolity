################################################################################
# Identity for the worker VM.
#
# One user-assigned managed identity with only what the worker needs. It is
# created (and its roles granted) BEFORE the VM, so the service has access as
# soon as it boots. This replaces the app registration + client secret and the
# subscription-wide Owner/Contributor roles the VM used to have.
################################################################################

resource "azurerm_user_assigned_identity" "mi" {
  resource_group_name = azurerm_resource_group.myrg.name
  location            = azurerm_resource_group.myrg.location
  name                = "${var.investigator_initials}-${random_id.randomId.hex}-identity"
  tags                = var.tags
}

# Read uploads, mark them processed (blob metadata), write results.
resource "azurerm_role_assignment" "mi_blob_contributor" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.mi.principal_id
  principal_type       = "ServicePrincipal"
}

# Create one ADX database per memory image (ARM control plane), scoped to the cluster only.
resource "azurerm_role_assignment" "mi_cluster_contributor" {
  scope                = azurerm_kusto_cluster.adxc.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.mi.principal_id
  principal_type       = "ServicePrincipal"
}

# Create tables/functions and ingest into every database (ADX data plane).
resource "azurerm_kusto_cluster_principal_assignment" "mi_admin" {
  # https://learn.microsoft.com/en-us/azure/data-explorer/kusto/access-control/role-based-access-control
  resource_group_name = azurerm_resource_group.myrg.name
  cluster_name        = azurerm_kusto_cluster.adxc.name
  name                = "VolAutolityWorker"
  principal_id        = azurerm_user_assigned_identity.mi.client_id
  principal_type      = "App"
  role                = "AllDatabasesAdmin"
  tenant_id           = data.azurerm_client_config.current.tenant_id
}

# The identity deploying gets admin on all databases to query them and use the workbook.
# ADX identifies users by object ID but applications by client ID.
resource "azurerm_kusto_cluster_principal_assignment" "adx_user_admin" {
  resource_group_name = azurerm_resource_group.myrg.name
  cluster_name        = azurerm_kusto_cluster.adxc.name
  name                = "UserAdminRoleADX"
  principal_id        = var.deployer_principal_type == "App" ? data.azurerm_client_config.current.client_id : data.azurerm_client_config.current.object_id
  principal_type      = var.deployer_principal_type
  role                = "AllDatabasesAdmin"
  tenant_id           = data.azurerm_client_config.current.tenant_id
}

moved {
  from = azurerm_role_assignment.name
  to   = azurerm_role_assignment.mi_blob_contributor
}
