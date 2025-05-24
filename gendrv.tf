module "dss" {
  source  = "app.terraform.io/sandbox/dss/aws"
  version = "8.0.1"

  for_each = local.dss_exists == true ? local.cloud_components.dss : {}

  providers = {
    aws          = aws
    aws.network  = aws.network
  }

  # Shared parameters
  redshift_username              = each.value.username
  redshift_node_type             = each.value.node_type
  redshift_cluster_type          = each.value.cluster_type
  redshift_cluster_version       = each.value.cluster_version
  redshift_number_of_nodes       = each.value.number_of_nodes
  redshift_security_group        = each.value.security_group
  redshift_subnet_ids            = data.aws_subnets.private_vpc_subnets.ids
  redshift_enhanced_vpc_routing  = each.value.enhanced_vpc_routing
  redshift_publicly_accessible   = false
  redshift_port                  = 5439
  redshift_multi_az              = true
  redshift_az                    = local.azs
  redshift_encrypted             = true
  kms_key_id                     = local.dss_kms_key_alias
  enable_serverless              = each.value.enable_serverless

  # Serverless-only parameters (optional, guarded by `enable_serverless`)
  redshift_namespace             = lookup(each.value, "namespace", null)
  redshift_workgroup             = lookup(each.value, "workgroup_name", null)
  redshift_base_capacity         = lookup(each.value, "base_capacity", null)

  # Additional shared inputs
  account        = var.aws_account
  app_name       = var.app_name
  env_name       = var.env_name
  env_type       = var.env_type
  product_id     = "0123456799"
  vpc_name       = local.vpcs[var.env_type]
  vpc_id         = data.aws_vpc.current.id
  tags           = local.optional_tags
}
