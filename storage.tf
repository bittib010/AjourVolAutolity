# Create a storage account
resource "azurerm_storage_account" "sa" {
  name                     = "${var.investigator_initials}${random_id.randomId.hex}sa"
  resource_group_name      = azurerm_resource_group.myrg.name
  location                 = azurerm_resource_group.myrg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  large_file_share_enabled = true
}

# Define the necessary permissions for the SAS token (used to upload memory dump for non-tenant-members)
# Work in progress to use SAS token for upload
data "azurerm_storage_account_sas" "sasas" {
  # https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/storage_account_sas
  connection_string = azurerm_storage_account.sa.primary_connection_string
  https_only        = true
  resource_types {
    service   = false
    container = true
    object    = true
  }
  services {
    blob  = true
    queue = false
    table = false
    file  = false
  }
  start  = "2024-01-01"
  expiry = "2025-01-01" # maybe add as variables for limitations?

  permissions {
    read    = true
    write   = true
    delete  = false
    list    = false
    add     = true
    create  = true
    update  = false
    process = false
    tag     = false
    filter  = false
  }
}

data "azurerm_storage_account" "data_sa" {
  name                = azurerm_storage_account.sa.name
  resource_group_name = azurerm_resource_group.myrg.name
}

# Create a blob container
resource "azurerm_storage_container" "sc" {
  name                  = "${var.investigator_initials}${random_id.randomId.hex}-bc"
  storage_account_name  = azurerm_storage_account.sa.name
  container_access_type = "blob"
}