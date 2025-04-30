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
            can(s.Principal.AWS) ? s.Principal.AWS : [],
            [local.new_role_arn]
          ))
        })
      }) : s
    )
  ]

  # Encode final updated policy back to JSON
  updated_policy = jsonencode({
    Version   = local.existing_policy.Version
    Statement = local.updated_statements
  })
}


resource "aws_kms_key_policy" "update_policy_with_append" {
  key_id = data.aws_kms_key.golden_key.key_id
  policy = local.updated_policy
}


resource "null_resource" "append_kms_arn" {
  provisioner "local-exec" {
    command = <<EOT
    set -e

    ROLE_ARN="arn:aws:iam::${var.new_account_id}:role/test-tf-role"
    POLICY_FILE="current_policy.json"

    # Fetch current policy
    aws kms get-key-policy \
      --key-id "${var.kms_key_id}" \
      --policy-name default \
      --region "${var.region}" > ${POLICY_FILE}

    # Append new role if not present (using jq)
    jq --arg role "$ROLE_ARN" '
      .Statement |= map(
        if .Sid == "AllowExternalAccountUse" then
          .Principal.AWS |= (
            if type == "array" then
              if index($role) == null then . + [$role] else . end
            else
              if . == $role then . else [$role, .] end
            end
          )
        else .
        end
      )
    ' ${POLICY_FILE} > updated_policy.json

    # Apply updated policy
    aws kms put-key-policy \
      --key-id "${var.kms_key_id}" \
      --policy-name default \
      --policy file://updated_policy.json \
      --region "${var.region}"
    EOT
  }

  triggers = {
    new_arn = var.new_account_id
  }
}
