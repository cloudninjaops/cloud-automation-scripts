resource "aws_iam_role" "kendra_execution" {
  name = "${local.kendra_index_name}-kendra-role"

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

resource "aws_iam_role_policy" "kendra_permissions" {
  name   = "${local.kendra_index_name}-kendra-policy"
  role   = aws_iam_role.kendra_execution.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["s3:GetObject", "s3:ListBucket"],
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_name}",
          "arn:aws:s3:::${var.s3_bucket_name}/*"
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"],
        Resource = var.kms_key_id
      }
    ]
  })
}
