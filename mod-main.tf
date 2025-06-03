resource "aws_iam_role" "kendra_role" {
  name = "${var.name}-kendra-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "kendra.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_kendra_index" "this" {
  name        = var.name
  edition     = var.edition
  description = var.description
  role_arn    = aws_iam_role.kendra_role.arn

  server_side_encryption_configuration {
    kms_key_id = var.kms_key_id
  }

  tags = var.tags
}
