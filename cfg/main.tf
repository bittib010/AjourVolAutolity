# Create a random ID for unique resource names
resource "random_id" "randomId" {
  byte_length = 4
}

# Create a resource group
resource "azurerm_resource_group" "myrg" {
  name     = "${var.investigator_initials}-${random_id.randomId.hex}-rg"
  location = var.resource_group_location
  tags = merge(var.tags, {
    "deletiondate" = local.deletion_date
  })

  lifecycle {
    # Set once at creation; re-applying should not push the deletion date forward.
    ignore_changes = [tags["deletiondate"]]
  }
}

data "azurerm_client_config" "current" {}

data "azurerm_subscription" "current" {}
