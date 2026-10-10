variable "investigator_initials" {
  type        = string
  default     = "test"
  description = "Investigators initials. Used as a prefix in resource names (lowercase letters/digits keep storage names valid)."
}

variable "resource_group_location" {
  type        = string
  default     = "norwayeast"
  description = "Location of the resource group."
}

variable "operator_ip" {
  type        = string
  default     = null
  description = "Public IP allowed to SSH to the worker VM. Detected automatically when null (set it explicitly in CI)."
}

variable "linux-name" {
  type        = string
  description = "Computer name of the Linux worker that downloads each memory image, runs Volatility and ingests the CSVs into ADX."
  default     = "analysis-worker"
}

variable "linux-username" {
  type        = string
  description = "Admin account on the analysing machine (SSH only; the service runs as its own system user)."
  default     = "AzVolAutolity"
}

variable "linux-size" {
  # https://learn.microsoft.com/en-us/azure/virtual-machines/sizes
  type        = string
  description = "The machine size of VM. Too big size might not be feasible and generate errors based on tenant limitations."
  default     = "Standard_F8s_v2"
  #default     = "Standard_B8ms"
  #default     = "Standard_DS1_v2"
  #default     = "Standard_F16s_v2"
}

variable "os_disk_size_gb" {
  type        = number
  default     = 128
  description = "OS disk size. Images are processed on the VM temp disk (work_dir) by default, see below."
}

variable "work_dir" {
  type        = string
  default     = "/mnt/volautolity"
  description = "Where images are downloaded and processed. /mnt is the Azure temp disk: fast, free, but sized by VM SKU and wiped on deallocation. Needs ~2x the largest image."
}

variable "path_to_public_key" {
  type        = string
  description = "The path to the public key for SSH login. Ignored when ssh_public_key is set."
  default     = "~/.ssh/id_rsa.pub"
}

variable "ssh_public_key" {
  type        = string
  default     = null
  description = "SSH public key content. Takes precedence over path_to_public_key (useful in CI)."
}

variable "deployer_principal_type" {
  type        = string
  default     = "User"
  description = "\"User\" when deploying with `az login` as a person, \"App\" when deploying from CI with a service principal."

  validation {
    condition     = contains(["User", "App"], var.deployer_principal_type)
    error_message = "deployer_principal_type must be \"User\" or \"App\"."
  }
}

variable "adx_sku_name" {
  type        = string
  default     = "Standard_D11_v2"
  description = "ADX cluster SKU. For short-lived labs consider \"Dev(No SLA)_Standard_E2a_v4\" (capacity 1), which is far cheaper."
}

variable "adx_capacity" {
  type        = number
  default     = 4
  description = "Number of ADX instances."
}

variable "dump_extensions" {
  type        = list(string)
  default     = ["dd", "raw", "mem", "vmem", "dmp", "dump", "lime", "bin", "img", "core", "elf"]
  description = "File extensions in the upload container that are treated as memory images."
}

variable "upload_sas_validity_hours" {
  type        = number
  default     = 168
  description = "How long the upload-only SAS token in the instructions output stays valid."
}

variable "include_slow_plugins" {
  type        = bool
  default     = true
  description = "Run slow plugins (strings, timeliner, dumpfiles, yara, ...). They are scheduled last either way."
}

# Third-party downloads are pinned to a commit and verified by SHA-256 on the VM; a mismatch aborts setup.
variable "yara_rules" {
  type = list(object({
    url    = string
    sha256 = string
  }))
  default = [
    {
      url    = "https://raw.githubusercontent.com/reversinglabs/reversinglabs-yara-rules/3cae0a5b958c965c15e3f52d9e9c168b05a224d5/yara/backdoor/Win64.Backdoor.Konni.yara"
      sha256 = "ff76606ee18d15a6de590dbdbbb55e9b75efedf38f9c1bac7c54fa3cc68e7e28"
    },
  ]
  description = "YARA rule files combined into one rules file for yarascan/vadyarascan. Empty list disables YARA."
}

variable "community_plugins" {
  type = list(object({
    url    = string
    sha256 = string
  }))
  # The Immersive Labs cobaltstrike.py plugin used previously requires pslist 2.x; Volatility 2.28 ships
  # pslist 3.x, so it no longer loads. Add plugins here once they target the current framework.
  default     = []
  description = "Third-party Windows Volatility 3 plugins installed on the VM (windows.<file>.<Class>)."
}

variable "remote_isf_url" {
  type        = string
  default     = ""
  description = "Optional ISF index for Linux/Mac kernel symbols (vol -u), e.g. a community banners.json. Empty = only local symbols in /var/lib/volautolity/symbols. Third-party data is fetched at runtime when set."
}

variable "upload_results" {
  type        = bool
  default     = true
  description = "Upload CSVs, logs and dumped files (registry hives, dumpfiles) to a 'results' container after each image."
}

# Expand logic if needed for more resources. This is based on autodeletion, to prevent it from happening if present in your subscription.
# Use these variables if you have an auto deletion for a test lab setup
variable "deletion_days" {
  type        = number
  description = "Number of days before the resource group should be deleted"
  default     = 14
}

#######################
# Subscription and remote state (values go in variables.auto.tfvars, which is git-ignored;
# see variables.auto.tfvars.example)
########################
variable "subscriptionname" {
  type = string
}

variable "subscriptionid" {
  type = string
}

variable "state_resource_group_name" {
  type        = string
  description = "Resource group of the state storage account (output of ./bootstrap)."
}

variable "state_storage_account_name" {
  type        = string
  description = "State storage account (output of ./bootstrap)."
}

variable "state_container_name" {
  type    = string
  default = "p-terra"
}

variable "state_key" {
  type    = string
  default = "terraform.tfstate"
}

variable "tags" {
  description = "Tags to be applied to resources."
  type        = map(string)
  default = {
    environment = "dev"
    project     = "AzVolAutolity"
  }
}
