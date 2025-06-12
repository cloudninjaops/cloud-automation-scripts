locals {
  referenced_security_groups = distinct(flatten([
    for ep_key, ep_val in local.cloud_components.vpc_endpoints : 
    try(ep_val.security_groups, [])
  ]))

  security_groups = try(local.cloud_components.security_groups, {})
}
  policy = file("${path.module}/policies/s3_policy.json") # or inline string