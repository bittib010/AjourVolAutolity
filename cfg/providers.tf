terraform {
  # OpenTofu reads the `terraform` block as well; this constraint is checked against the OpenTofu version.
  # https://github.com/opentofu/opentofu/releases
  # 1.10+ is needed for `lifecycle` inside `removed` blocks (see tf-container.tf).
  required_version = ">= 1.10.0"

  # State lives in the storage account created by ./bootstrap. OpenTofu (1.8+) evaluates variables
  # here, so nothing environment-specific is committed: set the state_* values in your tfvars.
  backend "azurerm" {
    resource_group_name  = var.state_resource_group_name
    storage_account_name = var.state_storage_account_name
    container_name       = var.state_container_name
    key                  = var.state_key
    use_azuread_auth     = true
  }

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
      # https://search.opentofu.org/provider/hashicorp/azurerm/latest
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscriptionid

  # azurerm 5.x no longer registers resource providers by default; register only what this stack uses.
  resource_provider_registrations = "none"
  resource_providers_to_register = [
    "Microsoft.Compute",
    "Microsoft.Insights",
    "Microsoft.Kusto",
    "Microsoft.ManagedIdentity",
    "Microsoft.Network",
    "Microsoft.Storage",
  ]
}
