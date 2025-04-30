locals {
  all_new_account_ids = flatten([
    for name, acc in module.account : acc.account_ids
  ])
}

resource "aws_ami_launch_permission" "share_ami" {
  for_each  = toset(local.all_new_account_ids)
  image_id  = data.aws_ami.latest_golden_ami.id
  account_id = each.value
}

resource "aws_snapshot_create_volume_permission" "share_snapshots" {
  for_each = {
    for pair in setproduct(
      toset([
        for bdm in data.aws_ami.latest_golden_ami.block_device_mappings : 
        bdm.ebs.snapshot_id if bdm.ebs.snapshot_id != null
      ]),
      toset(local.all_new_account_ids)
    ) : 
    "${pair[0]}-${pair[1]}" => {
      snapshot_id = pair[0]
      account_id  = pair[1]
    }
  }

  snapshot_id = each.value.snapshot_id
  account_id  = each.value.account_id
}

resource "null_resource" "append_kms_arn" {
  for_each = toset(local.all_new_account_ids)

  provisioner "local-exec" {
    command = "./scripts/update_kms_policy.sh ${each.value} ${var.kms_key_id} ${var.region}"
  }

  triggers = {
    role = each.value
  }

  depends_on = [
    aws_kms_key.packer_key
  ]
}
