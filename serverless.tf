/* main.tf */

locals {
  is_serverless = var.enable_serverless
}

# Redshift Serverless Resources
resource "aws_redshiftserverless_namespace" "this" {
  count                = local.is_serverless ? 1 : 0
  namespace_name       = local.redshift_namespace
  admin_user_password  = data.external.get_redshift_password.result.password
  admin_user_name      = var.redshift_admin_username
  kms_key_id           = aws_kms_key.redshift_kms.arn
  log_exports          = ["userlog", "connectionlog", "useractivitylog"]
  final_snapshot_name  = null
  tags                 = local.tags
}

resource "aws_redshiftserverless_workgroup" "this" {
  count                  = local.is_serverless ? 1 : 0
  workgroup_name         = local.redshift_workgroup
  namespace_name         = aws_redshiftserverless_namespace.this[0].namespace_name
  base_capacity          = var.redshift_base_capacity
  enhanced_vpc_routing   = true
  subnet_ids             = var.subnet_ids
  security_group_ids     = [aws_security_group.redshift_sg.id]
  publicly_accessible    = false
  config_parameters {
    parameter_key   = "enable_user_activity_logging"
    parameter_value = "true"
  }
  tags = local.tags
}

resource "aws_redshiftserverless_usage_limit" "concurrency_scaling" {
  count           = local.is_serverless ? 1 : 0
  usage_limit_type = "concurrency-scaling"
  amount           = 10
  breach_action    = "log"
  resource_arn     = aws_redshiftserverless_workgroup.this[0].arn
}

# Classic Redshift Cluster Resources
resource "aws_redshift_cluster" "this" {
  count                         = local.is_serverless ? 0 : 1
  cluster_identifier            = local.redshift_cluster_identifier
  database_name                 = var.redshift_db_name
  master_username               = var.redshift_admin_username
  master_password               = data.external.get_redshift_password.result.password
  node_type                     = var.redshift_node_type
  cluster_type                  = var.redshift_cluster_type
  number_of_nodes               = var.redshift_number_of_nodes
  iam_roles                     = [aws_iam_role.redshift_exec.arn]
  publicly_accessible           = var.redshift_publicly_accessible
  port                          = var.redshift_port
  vpc_security_group_ids        = [aws_security_group.redshift_sg.id]
  cluster_subnet_group_name     = aws_redshift_subnet_group.this.name
  encrypted                     = var.redshift_encrypted
  kms_key_id                    = aws_kms_key.redshift_kms.arn
  final_snapshot_identifier     = var.skip_final_snapshot ? null : "${local.redshift_cluster_identifier}-final"
  skip_final_snapshot           = var.skip_final_snapshot
  tags                          = local.tags
}

resource "aws_redshift_subnet_group" "this" {
  count       = local.is_serverless ? 0 : 1
  name        = "${local.redshift_cluster_identifier}-subnet-group"
  subnet_ids  = var.subnet_ids
  tags        = local.tags
}

resource "aws_iam_role" "redshift_exec" {
  name = "${local.redshift_cluster_identifier}-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "redshift.amazonaws.com"
        }
      }
    ]
  })
  tags = local.tags
}
