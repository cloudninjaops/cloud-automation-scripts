referenced_security_groups = {
  for sg_key in distinct(flatten([
    for ep in local.cloud_components.vpc_endpoints : try(ep.security_groups, [])
  ])) :
  sg_key => local.cloud_components.security_groups[sg_key]
  if contains(keys(local.cloud_components.security_groups), sg_key)
}


referenced_security_groups = {
  for sg_key in distinct(flatten([
    for ep in local.cloud_components.vpc_endpoints : try(ep.security_groups, [])
  ])) :
  sg_key => local.cloud_components.security_groups[sg_key]
  if contains(keys(local.cloud_components.security_groups), sg_key)
}

security_groups = local.cloud_components.security_groups