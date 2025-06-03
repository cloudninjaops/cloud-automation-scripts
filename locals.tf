locals {
  # Prefix for naming the Kendra index consistently across environments
  kendra_index_name = lower(join("-", [
    "${lookup(var.env_type_short, var.env_type)}${var.env_name}${lookup(var.region_short, var.region)}",
    var.app_name,
    var.name
  ]))

  # IAM role name derived from the index name
  kendra_iam_role_name = "${local.kendra_index_name}-kendra-role"
}
