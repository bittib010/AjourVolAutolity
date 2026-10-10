################################################################################
# One-time bootstrap of the remote state backend used by ../providers.tf.
#
# This is a separate root module with LOCAL state on purpose: the main
# configuration stores its state in the storage account created here, so it
# must not also manage (and potentially destroy) that account.
#
#   cd cfg/bootstrap
#   tofu init
#   tofu apply -var subscriptionid=<id> -var subscriptionname=<name>
#
# Then copy the outputs into the backend block in ../providers.tf.
################################################################################

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscriptionid
}

variable "subscriptionid" {
  type = string
}

variable "subscriptionname" {
  type = string
}

variable "location" {
  type    = string
  default = "norwayeast"
}

locals {
  subshort = replace(var.subscriptionname, "-", "")
}

resource "random_string" "random" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "azurerm_resource_group" "terraform" {
  name     = "${var.subscriptionname}-terraform"
  location = var.location

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "azurerm_storage_account" "terraform" {
  name                            = "${local.subshort}tfstate${random_string.random.result}"
  resource_group_name             = azurerm_resource_group.terraform.name
  location                        = azurerm_resource_group.terraform.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true # lets you roll back a corrupted state file
  }
}

resource "azurerm_storage_container" "p-terra" {
  name                  = "p-terra"
  storage_account_id    = azurerm_storage_account.terraform.id
  container_access_type = "private"
}

output "backend_config" {
  value = {
    resource_group_name  = azurerm_resource_group.terraform.name
    storage_account_name = azurerm_storage_account.terraform.name
    container_name       = azurerm_storage_container.p-terra.name
  }
}
