data "http" "myip" {
  count = var.operator_ip == null ? 1 : 0
  url   = "https://ipv4.icanhazip.com"
}

locals {
  operator_ip = var.operator_ip != null ? var.operator_ip : chomp(data.http.myip[0].response_body)

  # plantimestamp() is stable for the whole plan/apply, unlike timestamp() which is unknown until apply.
  deletion_date = formatdate("YYYY-MM-DD", timeadd(plantimestamp(), format("%dh", var.deletion_days * 24)))

  ssh_public_key = var.ssh_public_key != null ? var.ssh_public_key : file(pathexpand(var.path_to_public_key))

  # Python application shipped to the VM through cloud-init (no SSH provisioning, no Ansible).
  app_root = "${path.module}/../VolAutolity"
  app_files = setunion(fileset(local.app_root, "volautolity/*.py"), fileset(local.app_root, "volautolity/*.json"),
  fileset(local.app_root, "deploy/*"), ["requirements.txt"])

  # Memory images dropped in VolAutolity/sample/ are uploaded on apply and picked up like any other upload.
  sample_dir    = "${local.app_root}/sample"
  sample_images = toset([for f in fileset(local.sample_dir, "*") : f if contains(var.dump_extensions, lower(element(split(".", f), length(split(".", f)) - 1)))])

  yara_rules_file = "/opt/volautolity/yara/rules.yar"

  app_env = {
    AZURE_CLIENT_ID       = azurerm_user_assigned_identity.mi.client_id
    AZURE_SUBSCRIPTION_ID = data.azurerm_subscription.current.subscription_id
    AZURE_RESOURCE_GROUP  = azurerm_resource_group.myrg.name
    AZURE_LOCATION        = azurerm_resource_group.myrg.location
    ADX_CLUSTER_NAME      = azurerm_kusto_cluster.adxc.name
    ADX_CLUSTER_URI       = azurerm_kusto_cluster.adxc.uri
    ADX_INGEST_URI        = azurerm_kusto_cluster.adxc.data_ingestion_uri
    STORAGE_ACCOUNT_URL   = azurerm_storage_account.sa.primary_blob_endpoint
    INBOX_CONTAINER       = azurerm_storage_container.sc.name
    RESULTS_CONTAINER     = var.upload_results ? azurerm_storage_container.results.name : ""
    WORK_DIR              = var.work_dir
    VOL_COMMAND           = "/opt/volautolity/venv/bin/vol"
    VOL_SYMBOL_DIRS       = "/var/lib/volautolity/symbols"
    VOL_REMOTE_ISF_URL    = var.remote_isf_url
    DUMP_EXTENSIONS       = join(",", var.dump_extensions)
    INCLUDE_SLOW_PLUGINS  = tostring(var.include_slow_plugins)
    YARA_RULES_FILE       = length(var.yara_rules) > 0 ? local.yara_rules_file : ""
    YARA_RULES            = join(" ", [for r in var.yara_rules : "${r.sha256}@${r.url}"])
    COMMUNITY_PLUGINS     = join(" ", [for p in var.community_plugins : "${p.sha256}@${p.url}"])
  }
}
