locals {
  vpc_endpoint_exists = try(length(local.cloud_components.vpc_endpoints) > 0, false)

  vpc_endpoint_raw = local.vpc_endpoint_exists ? local.cloud_components.vpc_endpoints : {}

  vpc_endpoint_ordinals = {
    for k, v in local.vpc_endpoint_raw :
    k => merge(v, {
      endpoint_key = k
      ordinal      = format("%03d", index(keys(local.vpc_endpoint_raw), k) + 1)
      category     = try(v.category, "default")
    })
  }

  vpc_endpoint_final_list = local.vpc_endpoint_exists ? {
    for k, v in local.vpc_endpoint_ordinals :
    "${v.category}_${v.ordinal}" => v
  } : {}

  vpc_endpoint_name_map = {
    for k, v in local.vpc_endpoint_final_list :
    v.endpoint_key => k
  }
}

