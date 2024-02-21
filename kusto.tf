# create a managed data explorer cluster # wait to deploy
resource "azurerm_kusto_cluster" "adxc" {
  name                = "${var.investigator_initials}-${random_id.randomId.hex}clstr"
  location            = azurerm_resource_group.myrg.location
  resource_group_name = azurerm_resource_group.myrg.name
  sku {
    # https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/kusto_cluster#name
    name     = "Standard_D11_v2"
    capacity = 4
  }
}

# ADd python extension?
