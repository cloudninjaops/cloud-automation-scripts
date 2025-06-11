# vpc_endpoints.tf

locals {
  vpc_id         = data.aws_vpc.current.id
  subnet_ids     = data.aws_subnets.private.ids
  route_table_ids = data.aws_route_tables.private.ids
  region         = data.aws_region.current.name

  # Resolves service name from input (e.g., ec2 → com.amazonaws.us-east-1.ec2)
  vpc_endpoints = {
    for k, v in var.vpc_endpoints : k => merge(v, {
      service_name = format("com.amazonaws.%s.%s", local.region, v.service_type)
    })
  }
}

resource "aws_vpc_endpoint" "this" {
  for_each = local.vpc_endpoints

  vpc_id            = local.vpc_id
  service_name      = each.value.service_name
  vpc_endpoint_type = each.value.endpoint_type
  private_dns_enabled = each.value.endpoint_type == "Interface" ? each.value.private_dns_enabled : null

  subnet_ids         = each.value.endpoint_type == "Interface" ? local.subnet_ids : null
  security_group_ids = each.value.endpoint_type == "Interface" ? [module.security_group[each.value.security_groups[0]].id] : null

  route_table_ids    = each.value.endpoint_type == "Gateway" ? local.route_table_ids : null

  tags = var.tags
}

# data lookups for single VPC account

data "aws_vpc" "current" {
  default = true
}

data "aws_subnets" "private" {
  filter {
    name   = "tag:Tier"
    values = ["private"]
  }
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.current.id]
  }
}

data "aws_route_tables" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.current.id]
  }
}

data "aws_region" "current" {}

# variables.tf

variable "vpc_endpoints" {
  type = map(object({
    service_type         = string
    endpoint_type        = string # Interface | Gateway | GatewayLoadBalancer
    private_dns_enabled  = optional(bool)
    security_groups      = optional(list(string))
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}
