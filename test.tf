resource "null_resource" "share_golden_ami_to_new_account" {
  provisioner "local-exec" {
    command = <<EOT
      python3 scripts/share_golden_ami.py \
      --new_account_id ${module.account.new_account_id} \
      --new_account_role_name "test-packer-role" \
      --region "us-east-1"
    EOT
  }

  triggers = {
    run_id = timestamp()
  }

  depends_on = [
    module.account   # wait until account creation finishes
  ]
}
