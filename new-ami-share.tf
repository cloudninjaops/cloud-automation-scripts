locals {
  all_new_account_ids = flatten([
    for name, acc in module.account : acc.account_ids
  ])

  golden_snapshot_ids = [
    for bdm in data.aws_ami.latest_golden_ami.block_device_mappings :
    bdm.ebs.snapshot_id
    if bdm.ebs.snapshot_id != null
  ]

  snapshot_account_pairs = flatten([
    for snapshot_id in local.golden_snapshot_ids : [
      for account_id in local.all_new_account_ids : {
        snapshot_id = snapshot_id
        account_id  = account_id
      }
    ]
  ])
}

resource "aws_ami_launch_permission" "share_ami" {
  for_each   = toset(local.all_new_account_ids)
  image_id   = data.aws_ami.latest_golden_ami.id
  account_id = each.value
}

resource "aws_snapshot_create_volume_permission" "share_snapshots" {
  for_each = {
    for pair in local.snapshot_account_pairs : "${pair.snapshot_id}-${pair.account_id}" => pair
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

  # depends_on = [aws_kms_key.packer_key]
}
