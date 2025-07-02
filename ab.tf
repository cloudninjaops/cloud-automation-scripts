resource "aws_iam_role" "cert_reader" {
  count = var.cert_key_secret_name != null && var.acm_cert_arn != null ? 1 : 0

  name = "${var.env_name}-${var.app_name}-cert-reader-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Principal = {
          Service = "ec2.amazonaws.com"
        },
        Effect = "Allow",
      }
    ]
  })
}

resource "aws_iam_role_policy" "cert_reader_policy" {
  count = var.cert_key_secret_name != null && var.acm_cert_arn != null ? 1 : 0

  name = "cert-access"
  role = aws_iam_role.cert_reader[0].name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["secretsmanager:GetSecretValue"],
        Resource = "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:${var.cert_key_secret_name}*"
      },
      {
        Effect   = "Allow",
        Action   = ["acm:GetCertificate", "acm:DescribeCertificate"],
        Resource = var.acm_cert_arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "cert_reader_profile" {
  count = var.cert_key_secret_name != null && var.acm_cert_arn != null ? 1 : 0

  name = "${var.env_name}-${var.app_name}-cert-reader-profile"
  role = aws_iam_role.cert_reader[0].name
}


#----

resource "aws_launch_template" "this" {
  ...

  dynamic "iam_instance_profile" {
    for_each = var.cert_key_secret_name != null && var.acm_cert_arn != null ? [1] : []
    content {
      name = aws_iam_instance_profile.cert_reader_profile[0].name
    }
  }

  ...
}


data "aws_caller_identity" "current" {}
