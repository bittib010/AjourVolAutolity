# Managed Azure Data Explorer cluster (takes ~15 minutes to create).
# Databases are created per memory image by the worker VM, not here.
resource "azurerm_kusto_cluster" "adxc" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}clstr"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name
  tags                = var.tags

  # Forensic data at rest: encrypt the cluster's disks.
  disk_encryption_enabled = true

  sku {
    # https://search.opentofu.org/provider/hashicorp/azurerm/latest/docs/resources/kusto_cluster
    name     = var.adx_sku_name
    capacity = var.adx_capacity
  }
}
