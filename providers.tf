terraform {
  required_version = ">= 1.9.8"
  #https://github.com/hashicorp/terraform/releases

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.6.0"
      # https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs
    }
    random = {
      source  = "hashicorp/random"
      version = ">=3.6.3"
      # https://registry.terraform.io/providers/hashicorp/random/latest/docs
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~>3.0.2"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = "00000000-0000-0000-0000-000000000000"
}