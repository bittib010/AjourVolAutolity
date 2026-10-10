# Storage account for memory image uploads and analysis results
resource "azurerm_storage_account" "sa" {
  name                     = "${var.investigator_initials}${random_id.randomId.hex}sa"
  resource_group_name      = azurerm_resource_group.myrg.name
  location                 = azurerm_resource_group.myrg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags

  # Memory images contain credentials and secrets. They must never be anonymously readable
  # (the container used to be `container_access_type = "blob"`, i.e. public read).
  allow_nested_items_to_be_public = false

  blob_properties {
    # Evidence protection: accidentally deleted/overwritten images can be recovered for a week.
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }
}

# Uploads land here; the worker polls it and records progress in blob metadata.
resource "azurerm_storage_container" "sc" {
  name                  = "${var.investigator_initials}${random_id.randomId.hex}-bc"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

# CSVs, logs, dumped registry hives and files, per image.
resource "azurerm_storage_container" "results" {
  name                  = "results"
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

# Upload-only SAS for people outside the tenant: can create/write blobs, cannot read or list them.
data "azurerm_storage_account_blob_container_sas" "upload" {
  connection_string = azurerm_storage_account.sa.primary_connection_string
  container_name    = azurerm_storage_container.sc.name
  https_only        = true
  start             = timeadd(plantimestamp(), "-15m") # tolerate clock skew on the uploader's machine
  expiry            = timeadd(plantimestamp(), format("%dh", var.upload_sas_validity_hours))

  # Revoke early by rotating the storage account key it is signed with (az storage account keys renew).
  # `write` also allows overwriting an existing blob; blob soft delete keeps the overwritten data for 7 days.
  permissions {
    read   = false
    add    = false
    create = true
    write  = true
    delete = false
    list   = false
  }
}

# Images placed in VolAutolity/sample/ are uploaded on apply and processed like any other upload.
resource "azurerm_storage_blob" "sample" {
  for_each             = local.sample_images
  name                 = each.value
  storage_container_id = azurerm_storage_container.sc.id
  type                 = "Block"
  source               = "${local.sample_dir}/${each.value}"

  lifecycle {
    # The worker writes its processing status into the metadata; don't reset it on the next apply.
    ignore_changes = [metadata]
  }
}
