################################################################################
# The remote-state storage used to be created by this configuration, i.e. the
# configuration managed the storage account holding its own state (a
# `tofu destroy` would have deleted it). It now lives in ./bootstrap.
#
# These blocks make OpenTofu forget those resources WITHOUT destroying them.
# They are no-ops if the resources were never in this state. Once a plan/apply
# has run with them, this file can be deleted.
################################################################################

removed {
  from = azurerm_storage_container.p-terra

  lifecycle {
    destroy = false
  }
}

removed {
  from = azurerm_storage_account.terraform

  lifecycle {
    destroy = false
  }
}

removed {
  from = azurerm_resource_group.terraform

  lifecycle {
    destroy = false
  }
}

removed {
  from = random_string.random

  lifecycle {
    destroy = false
  }
}
