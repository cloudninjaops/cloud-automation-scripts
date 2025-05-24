# Namespace ARN
output "serverless_namespace_arn" {
  value       = local.is_serverless ? aws_redshiftserverless_namespace.this[0].arn : null
  description = "ARN of the Redshift Serverless namespace"
}

# Workgroup ARN
output "serverless_workgroup_arn" {
  value       = local.is_serverless ? aws_redshiftserverless_workgroup.this[0].arn : null
  description = "ARN of the Redshift Serverless workgroup"
}
