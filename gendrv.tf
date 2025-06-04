locals {
  # Pull Kendra index definitions from input YAML
  kendra_indexes = try(local.cloud_components.kendra, {})

  # Map of KMS key names to their ARNs from the kms module output
  kms_keys = {
    for key_name, mod in module.kms : key_name => mod.key_arn
  }
}


module "kendra_indexes" {
  source = "app.terraform.io/fepoc/kendra/aws"

  for_each = local.kendra_indexes

  name        = each.value.name
  edition     = try(each.value.edition, "DEVELOPER_EDITION")
  description = try(each.value.description, "")
  kms_key_id  = local.kms_keys[each.value.encryption_key]
  tags        = local.optional_tags

  providers = {
    aws.network = aws.network
  }
}

kendra_index_name = lower(join("-", [
  "fepoc",                                                    # Fixed organization name
  var.env_type,                                               # e.g., dev
  var.env_name,                                               # e.g., dv
  lookup(var.region_short, var.region),                       # e.g., e1
  "kendra",                                                   # Resource type
  var.app_name,                                               # e.g., cmpesai
  format("%03d", each.value.grp_ordinal)                      # Ordinal padded to 3 digits
]))

