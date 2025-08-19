################################################
#  Deploy resource group
################################################
resource "azurerm_resource_group" "terraform" {
  name     = "${var.subscriptionname}-terraform"
  location = var.resource_group_location

  lifecycle {
    ignore_changes = [
      tags
    ]
  }
}


################################################
#  Deploy Terraform state file container
################################################
resource "azurerm_storage_account" "terraform" {
  name                     = "${local.subshort}tfstate${random_string.random.result}"
  resource_group_name      = azurerm_resource_group.terraform.name
  location                 = azurerm_resource_group.terraform.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "p-terra" {
  name                  = "p-terra"
  storage_account_id    = azurerm_storage_account.terraform.id
  container_access_type = "private"
}


############################################################################################################################################
# Create "Random string" to assist creation of resource unique names
############################################################################################################################################
resource "random_string" "random" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}