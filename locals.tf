
########################################################################
# Locals below shall not be edited
########################################################################
locals {
  subshort = replace(var.subscriptionname, "-", "")
  unique   = substr("${var.subscriptionid}", -5, -1)
}