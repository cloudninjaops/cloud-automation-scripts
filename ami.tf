# -------------------------
# VARIABLES
# -------------------------
variable "new_account_id" {
  description = "New AWS account ID to share AMI, snapshots, and update KMS policy."
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "kms_key_alias" {
  description = "Alias name of KMS Key used for golden AMIs (example: alias/aws-packer-key)"
  type        = string
}

# -------------------------
# PROVIDER
# -------------------------
provider "aws" {
  region = var.region
}

# -------------------------
# DATA SOURCES
# -------------------------
data "aws_ami" "latest_golden_ami" {
  most_recent = true
  owners      = ["self"]

  filter {
    name   = "name"
    values = ["aws-rhel-golden*"]
  }
}

data "aws_kms_alias" "packer_key" {
  name = var.kms_key_alias
}

# -------------------------
# RESOURCES - SHARE AMI
# -------------------------
resource "aws_ami_launch_permission" "share_ami" {
  image_id   = data.aws_ami.latest_golden_ami.id
  account_id = var.new_account_id
}

# -------------------------
# RESOURCES - SHARE SNAPSHOTS
# -------------------------
resource "aws_ebs_snapshot_create_volume_permission" "share_snapshots" {
  for_each = toset([
    for bdm in data.aws_ami.latest_golden_ami.block_device_mappings : bdm.ebs.snapshot_id
    if bdm.ebs.snapshot_id != null
  ])

  snapshot_id = each.value
  account_id  = var.new_account_id
}

# -------------------------
# RESOURCE - UPDATE KMS POLICY
# -------------------------
resource "aws_kms_key_policy" "update_kms_policy" {
  key_id = data.aws_kms_alias.packer_key.target_key_id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "AllowAccountAdminFullAccess",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "arn:aws:iam::${data.aws_kms_alias.packer_key.target_key_arn_split[4]}:root"
        },
        "Action" : "kms:*",
        "Resource" : "*"
      },
      {
        "Sid" : "AllowUseOfKeyForNewAccount",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "arn:aws:iam::${var.new_account_id}:role/test-tf-role"
        },
        "Action" : [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:CreateGrant"
        ],
        "Resource" : "*"
      }
    ]
  })
}

# -------------------------
# LOCAL SPLIT to extract account_id from KMS Key ARN
# -------------------------
locals {
  # Example Key ARN: arn:aws:kms:us-east-1:111111111111:key/uuid
  kms_key_arn_parts = split(":", data.aws_kms_alias.packer_key.target_key_arn)
}

data "aws_kms_alias" "packer_key_full" {
  depends_on = [data.aws_kms_alias.packer_key]
  name       = var.kms_key_alias
}

output "kms_key_id" {
  value = data.aws_kms_alias.packer_key.target_key_id
}
