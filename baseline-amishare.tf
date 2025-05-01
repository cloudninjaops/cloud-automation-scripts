provider "aws" {
  alias = "sharedsvc"
}

variable "enable_amishare" {
  type    = bool
  default = false
}

variable "ami_name_prefix" {
  type        = string
  default     = "aws-rhel-golden"
  description = "Prefix to identify the golden AMI"
}

variable "kms_key_id" {
  type        = string
  description = "KMS key ID used for AMI encryption"
}

data "aws_ami" "latest_golden" {
  provider    = aws.sharedsvc
  most_recent = true
  owners      = ["self"]

  filter {
    name   = "name"
    values = ["${var.ami_name_prefix}*"]
  }
}

# Extract account ID from IAM role ARN
locals {
  new_account_id = split(":", aws_iam_role.terraform_role.arn)[4]
}

resource "aws_ami_launch_permission" "share_ami" {
  provider   = aws.sharedsvc
  count      = var.enable_amishare ? 1 : 0
  image_id   = data.aws_ami.latest_golden.id
  account_id = local.new_account_id

  depends_on = [
    aws_iam_role.terraform_role  # Wait for role to be created
  ]
}

resource "aws_snapshot_create_volume_permission" "share_snapshots" {
  provider = aws.sharedsvc
  for_each = toset([
    for bdm in data.aws_ami.latest_golden.block_device_mappings :
    bdm.ebs.snapshot_id
    if bdm.ebs.snapshot_id != null
  ])

  snapshot_id = each.value
  account_id  = local.new_account_id
  depends_on = [
    aws_iam_role.terraform_role
  ]
}


resource "null_resource" "update_kms_policy" {
  provider = aws.sharedsvc
  count    = var.enable_amishare ? 1 : 0

  provisioner "local-exec" {
    command = "bash scripts/update_kms_policy.sh ${local.new_account_id} ${var.kms_key_id}"
  }
  depends_on = [
    aws_ami_launch_permission.share_ami,
    aws_snapshot_create_volume_permission.share_snapshots
  ]
}
