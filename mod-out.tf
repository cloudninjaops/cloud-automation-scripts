output "index_id" {
  description = "ID of the created Kendra index"
  value       = aws_kendra_index.this.id
}

output "index_arn" {
  description = "ARN of the created Kendra index"
  value       = aws_kendra_index.this.arn
}

output "role_name" {
  description = "Name of the IAM role used by the Kendra index"
  value       = aws_iam_role.kendra_role.name
}
