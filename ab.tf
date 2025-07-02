locals {
  cert_lookup_map = {
    for cert_key, cert_data in module.acm :
    cert_key => {
      acm_cert_arn         = try(cert_data.acm_cert_arn, null)
      cert_key_secret_name = try(cert_data.cert_key_secret_name, null)
    }
  }
}


local.cert_lookup_map["ec2_cert_ig1"].acm_cert_arn

module "launch_template" {
  for_each = { for lt in local.launch_templates : lt.launch_template_name => lt }

  ...
  acm_cert_arn         = try(local.cert_lookup_map[each.value.cert_key].acm_cert_arn, null)
  cert_key_secret_name = try(local.cert_lookup_map[each.value.cert_key].cert_key_secret_name, null)
}

locals {
  debug_cert_arn  = var.acm_cert_arn != null ? var.acm_cert_arn : "NOT SET"
  debug_secret    = var.cert_key_secret_name != null ? var.cert_key_secret_name : "NOT SET"
}


resource "null_resource" "debug_cert_vars" {
  provisioner "local-exec" {
    command = <<EOT
      echo "==== DEBUG: ACM Certificate Variables ===="
      echo "ACM Cert ARN: ${local.debug_cert_arn}"
      echo "Secret Name:  ${local.debug_secret}"
      echo "=========================================="
    EOT
  }
}
