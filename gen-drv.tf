locals {
  vpc_endpoint_exists = try(contains(keys(local.cloud_components), "vpc_endpoints"), false)

  vpc_endpoint_grouping = local.vpc_endpoint_exists ? {
    for key, value in local.cloud_components.vpc_endpoints :
    key => merge(value, { endpoint_key = key })
  } : {}

  vpc_endpoint_ordinals = flatten([
    for key, value in local.vpc_endpoint_grouping : [
      for idx in range(length([value])) : {
        "${key}_${format("%03d", idx + 1)}" = merge(value, {
          ordinal      = format("%03d", idx + 1),
          endpoint_key = key
        })
      }
    ]
  ])

  vpc_endpoint_final_list = merge([
    for k, v in local.vpc_endpoint_ordinals : {
      "${try(v.category, "default")}_${v.ordinal}" => v
    }
  ]...)

  vpc_endpoint_name_map = {
    for key, value in local.vpc_endpoint_final_list : value.endpoint_key => key
  }

  vpc_endpoint_final_list = length(local.vpc_endpoint_ordinals) > 0 ? merge([
  for k, v in local.vpc_endpoint_ordinals : {
    "${v.category}_${v.ordinal}" = v
  }
]) : {}
}

module "vpc_endpoint" {
  source  = "app.terraform.io/sss/vpc-endpoint/aws"
  version = "1.0.0"

  for_each = local.vpc_endpoint_final_list

  app_name       = local.app_name
  env_name       = var.env_name
  env_type       = var.env_type
  region         = var.region
  ordinal        = each.value.ordinal
  service_type   = each.value.service_type # like "s3", "ec2", "dynamodb"
  endpoint_type  = each.value.endpoint_type # "Interface", "Gateway", or "GatewayLoadBalancer"
  private_dns_enabled = try(each.value.private_dns_enabled, true)

  vpc_id         = data.aws_vpc.default.id
  subnet_ids     = try(data.aws_subnets.all_vpc_subnets.ids, [])
  route_table_ids = try(data.aws_route_tables.default.ids, [])

  security_group_ids = try([
    for sg in try(each.value.security_groups, []) :
    module.security_group[sg].id
  ], [])

  gwlb_security_group_id = try(module.security_group[each.value.gwlb_sg].id, null)

  tags = local.optional_tags
}


vpc_endpoint_ordinals = flatten([
  for k, grp in local.cloud_components.vpc_endpoints : [
    for idx, v in enumerate(grp) : {
      category = try(v.category, "default")
      ordinal  = format("%03d", idx + 1)
      endpoint_key = k
      # Include other needed fields
    }
  ]
])


vpc_endpoint_ordinals = flatten([
  for key, list in local.cloud_components.vpc_endpoints : [
    for idx in range(length(list)) : merge(
      list[idx],
      {
        endpoint_key = key
        category     = try(list[idx].category, "default")
        ordinal      = format("%03d", idx + 1)
      }
    )
  ]
])
