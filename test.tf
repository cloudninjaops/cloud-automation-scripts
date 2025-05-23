/* main.tf */

locals {
  is_serverless = var.enable_serverless
  redshift_cluster_identifier = join("-", compact([
    var.organization,
    lookup(var.region_short, var.region),
    var.env_type,
    var.env_name,
    var.app_name,
    lookup(var.optional_tags, "ordinal", null)
  ]))
  tags = merge(var.optional_tags, {
    Environment = var.env_name
    Application = var.app_name
  })
}

# Redshift Serverless Resources
resource "aws_redshiftserverless_namespace" "this" {
  count                = local.is_serverless ? 1 : 0
  namespace_name       = var.redshift_namespace
  admin_user_password  = data.external.get_redshift_password.result.password
  admin_user_name      = var.redshift_admin_username
  kms_key_id           = aws_kms_key.redshift_kms.arn
  log_exports          = ["userlog", "connectionlog", "useractivitylog"]
  final_snapshot_name  = null
  tags                 = local.tags
}

resource "aws_redshiftserverless_workgroup" "this" {
  count                  = local.is_serverless ? 1 : 0
  workgroup_name         = var.redshift_workgroup
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

/* variables.tf */

variable "enable_serverless" {
  description = "Flag to enable Redshift Serverless"
  type        = bool
}

variable "redshift_namespace" {
  description = "Name of the Redshift serverless namespace"
  type        = string
  default     = null
}

variable "redshift_workgroup" {
  description = "Name of the Redshift serverless workgroup"
  type        = string
  default     = null
}

variable "redshift_base_capacity" {
  description = "Base capacity for Redshift serverless"
  type        = number
  default     = 32
}

variable "redshift_db_name" {
  description = "Database name for Redshift cluster"
  type        = string
}

variable "redshift_admin_username" {
  description = "Admin username for Redshift"
  type        = string
}

variable "redshift_node_type" {
  description = "Redshift node type (for classic only)"
  type        = string
}

variable "redshift_cluster_type" {
  description = "Cluster type: single-node or multi-node"
  type        = string
}

variable "redshift_number_of_nodes" {
  description = "Number of nodes for Redshift classic"
  type        = number
}

variable "redshift_publicly_accessible" {
  description = "If the Redshift cluster should be publicly accessible"
  type        = bool
  default     = false
}

variable "redshift_encrypted" {
  description = "Whether Redshift classic is encrypted"
  type        = bool
  default     = true
}

variable "skip_final_snapshot" {
  description = "Skip final snapshot on deletion"
  type        = bool
  default     = false
}

variable "redshift_port" {
  description = "Port for Redshift access"
  type        = number
  default     = 5439
}

variable "subnet_ids" {
  description = "List of subnet IDs"
  type        = list(string)
}

variable "organization" {
  description = "Organization name"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "region_short" {
  description = "Map of region to short code"
  type        = map(string)
}

variable "env_type" {
  description = "Environment type (e.g., dev, prod)"
  type        = string
}

variable "env_name" {
  description = "Environment name"
  type        = string
}

variable "app_name" {
  description = "Application name"
  type        = string
}

variable "optional_tags" {
  description = "Optional tags map"
  type        = map(string)
  default     = {}
}

/* outputs.tf */

output "redshift_endpoint" {
  value = local.is_serverless ? aws_redshiftserverless_workgroup.this[0].endpoint[0].address : aws_redshift_cluster.this[0].endpoint
  description = "Redshift endpoint"
}

output "redshift_type" {
  value = local.is_serverless ? "serverless" : "classic"
  description = "Redshift deployment type"
}
