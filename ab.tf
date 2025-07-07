resource "aws_iam_role" "cert_secret_reader" {
  count = var.iam_instance_profile == null && var.cert_key_secret_name != null && var.acm_cert_arn != null ? 1 : 0

  name = "${local.asg_cert_ec2_role_name_prefix}-cert-secret-reader-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Principal = {
          Service = "ec2.amazonaws.com"
        },
        Effect = "Allow"
      }
    ]
  })
}

=-----
locals {
  iam_instance_profile_name = (
    var.iam_instance_profile != null ? var.iam_instance_profile :
    (
      var.cert_key_secret_name != null && var.acm_cert_arn != null ?
      aws_iam_instance_profile.cert_secret_reader_profile[0].name :
      null
    )
  )
}

---

dynamic "iam_instance_profile" {
  for_each = local.iam_instance_profile_name != null ? [local.iam_instance_profile_name] : []
  content {
    name = iam_instance_profile.value
  }
}

----
