environment = {
  TFC_ORG            = var.tfc_org
  AWS_REGION         = local.region
  ACCOUNT_B_ROLE_ARN = local.target_role_arn
  DRY_RUN            = var.dry_run

  # Full YAML passed as JSON — replaces RESOURCES_LIST and TAGS
  TAGGING_CONFIG     = jsonencode(local.tagging_resources)
}