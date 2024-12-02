terraform {
  required_version = ">= 1.6.6"
  #https://github.com/hashicorp/terraform/releases

  # backend "azurerm" {
  #   resource_group_name  = "p-terra"
  #   storage_account_name = ""
  #   container_name       = "p-terra"
  #   key                  = "terraform.tfstate"
  #   use_azuread_auth     = true
  # }

  required_providers {


    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.88.0"
      # https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs
    }
    random = {
      source  = "hashicorp/random"
      version = ">=3.6.0"
      # https://registry.terraform.io/providers/hashicorp/random/latest/docs
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~>2.47.0"
    }
  }
}

provider "azurerm" {
  features {}
}