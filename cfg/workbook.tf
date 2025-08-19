resource "azurerm_application_insights_workbook" "triage_workbook" {
  name                = "0438eb80-6330-400c-9e7d-9679c6def38c"
  resource_group_name = azurerm_resource_group.myrg.name
  location            = var.resource_group_location
  display_name        = "Windows Triage Workbook"
  source_id           = lower(azurerm_kusto_cluster.adxc.id)
  data_json = templatefile("${path.module}/windows_triage.json", {
    cluster_url          = azurerm_kusto_cluster.adxc.uri,
    resource_group_id    = azurerm_resource_group.myrg.id,
    fallback_resource_id = "/subscriptions/${data.azurerm_subscription.current.subscription_id}/resourceGroups/${azurerm_resource_group.myrg.name}"
  })

  tags = {
    ENV = "Test"
  }
}
