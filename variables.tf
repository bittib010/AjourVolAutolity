variable "investigator_initials" {
  type        = string
  default     = "aks" 
  description = "Investigators initials."
}

variable "resource_group_location" {
  type        = string
  default     = "norwayeast"
  description = "Location of the resource group."
}

data "http" "myip" {
  url = "http://ipv4.icanhazip.com"
}

variable "linux-name" {
  type        = string
  description = "Name of the Linux Volatility device responsible for attaching storage, analyse each memory image and pushing all possible CSV's to ADX."
  default     = "analysis-worker"
}

variable "mounting_point" {
  type        = string
  description = "The mounting location for the memorydump upload storage blob"
  default     = "/mnt/memorydumps"
}

variable "project_path" {
  type        = string
  description = "Path to the location of python project that runs the Volatility and sends it the correct arguments. Is being concatenated in output to python_vars"
  default     = "VolAutolity"
}

variable "linux-username" {
  type        = string
  description = "AccountName on the analyzing machine."
  default     = "AzVolAutolity"
}

variable "linux-size" {
  # https://learn.microsoft.com/en-us/azure/virtual-machines/sizes
  type        = string
  description = "The machine size of VM. Too big size might not be feasible and generate errors based on tenant limitations."
  # https://learn.microsoft.com/en-us/azure/virtual-machines/linux/compute-benchmark-scores
  #default     = "Standard_F8s_v2"
  #default     = "Standard_B8ms"
  #default     = "Standard_DS1_v2"
  #default     = "Standard_F16s_v2"
  default     = "Standard_B4ms"
}

# Expand logic if needed for more resources. THis is based on autodeletion, to prevent it from happening if present in your subscription.
# Use these variables if you have an auto deletion for a test lab setup
variable "deletion_days" {
  description = "Number of days before the resource group should be deleted"
  default     = 14
}

variable "subscription_id" {
  type        = string
  description = "The Azure subscription ID to use for this deployment."
}

variable "username" {
  type        = string
  description = "The username for SSH key paths."
}

locals {
  current_timestamp = timestamp()
  deletion_date     = formatdate("YYYY-MM-DD", timeadd(local.current_timestamp, format("%dh", var.deletion_days * 24)))
  path_to_public_key = "C:\\Users\\${var.username}\\.ssh\\id_rsa.pub"
  path_to_private_key = "C:\\Users\\${var.username}\\.ssh\\id_rsa"
}