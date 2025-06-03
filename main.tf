resource "aws_kendra_index" "this" {
  name        = local.kendra_index_name
  role_arn    = aws_iam_role.kendra_execution.arn
  edition     = var.edition
  description = var.description

  server_side_encryption_configuration {
    kms_key_id = var.kms_key_id
  }

  tags = var.tags

  # Optional logic can be added to include document metadata sources in future
}
