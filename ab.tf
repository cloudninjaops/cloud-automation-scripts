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
