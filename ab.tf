data "aws_kms_key" "golden_key" {
  key_id = "alias/aws-packer-key"  # or your actual alias
}

data "aws_kms_key_policy" "existing" {
  key_id = data.aws_kms_key.golden_key.id
}

locals {
  # Decode existing KMS policy JSON
  existing_policy = jsondecode(data.aws_kms_key_policy.existing.policy)

  # New role to add
  new_role_arn = "arn:aws:iam::${var.new_account_id}:role/test-tf-role"

  # Modified statements: loop through and find matching SID
  updated_statements = [
    for s in local.existing_policy.Statement : (
      s.Sid == "Allow an external account to use this KMS key" ?
      merge(s, {
        Principal = merge(s.Principal, {
          AWS = distinct(concat(
            (s.Principal.AWS if can(s.Principal.AWS) else []),
            [local.new_role_arn]
          ))
        })
      }) : s
    )
  ]

  updated_policy = jsonencode({
    Version   = local.existing_policy.Version
    Statement = local.updated_statements
  })
}

resource "aws_kms_key_policy" "update_policy_with_append" {
  key_id = data.aws_kms_key.golden_key.key_id
  policy = local.updated_policy
}
