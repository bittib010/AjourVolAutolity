variable "investigator_initials" {
  type        = string
  default     = "test"
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
  description = "Account on the analyzing machin."
  default     = "AzVolAutolity"
}

variable "linux-size" {
  type        = string
  description = "The machine size of VM. Too big size might not be feasible and generate errors based on tenant limitations."
  #default     = "Standard_B8ms"
  default     = "Standard_DS1_v2"
}

variable "path_to_public_key" {
  type        = string
  description = "The path to public key for SSH login"
  default     = "C:\\Users\\<USERNAME>\\.ssh\\id_rsa.pub"
}
variable "path_to_private_key" {
  type        = string
  description = "The path to private key for SSH login"
  default     = "C:\\Users\\<USERNAME>\\.ssh\\id_rsa"
}