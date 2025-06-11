variable "app_name" {}
variable "env_name" {}
variable "env_type" {}
variable "region" {}
variable "ordinal" {}
variable "service_type" {}
variable "endpoint_type" {}
variable "private_dns_enabled" {
  type    = bool
  default = true
}
variable "vpc_id" {}
variable "subnet_ids" {
  type    = list(string)
  default = []
}
variable "route_table_ids" {
  type    = list(string)
  default = []
}
variable "security_group_ids" {
  type    = list(string)
  default = []
}
variable "gwlb_security_group_id" {
  type    = string
  default = null
}
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  endpoint_name = lower(join("-", compact([
    "vpce",
    var.env_type,
    var.env_name,
    var.region,
    var.app_name,
    var.service_type,
    var.endpoint_type,
    format("%03d", var.ordinal)
  ])))
  service_name = "com.amazonaws.${var.region}.${var.service_type}"
}

resource "aws_vpc_endpoint" "this" {
  vpc_id             = var.vpc_id
  service_name       = local.service_name
  vpc_endpoint_type  = var.endpoint_type
  private_dns_enabled = var.endpoint_type == "Interface" ? var.private_dns_enabled : null
  subnet_ids         = var.endpoint_type == "Interface" ? var.subnet_ids : null
  route_table_ids    = var.endpoint_type == "Gateway" ? var.route_table_ids : null
  security_group_ids = var.endpoint_type == "Interface" ? var.security_group_ids : null

  tags = merge(var.tags, {
    Name = local.endpoint_name
  })
}

vpc_endpoint_final_list = length(local.vpc_endpoint_ordinals) > 0 ? merge([
  for k, v in local.vpc_endpoint_ordinals : {
    "${v.category}_${v.ordinal}" = v
  }
]) : {}
