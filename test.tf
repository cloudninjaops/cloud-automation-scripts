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



resource "aws_security_group" "vpce_sg" {
  for_each = {
    for sg_key in var.referenced_security_groups :
    sg_key => var.security_groups[sg_key]
  }

  name        = "${each.key}-${var.app_name}-${var.env_type}"
  description = each.value.additional_description
  vpc_id      = var.vpc_id
  tags        = var.tags
}

#-------

resource "aws_security_group" "vpce_sg" {
  for_each = { for sg_key in var.referenced_security_groups : sg_key => var.security_groups[sg_key] }

  name        = "${each.key}-${var.app_name}-${var.env_type}"
  description = each.value.additional_description
  vpc_id      = var.vpc_id

  tags = merge(
    var.tags,
    {
      Name = "${each.key}-${var.app_name}-${var.env_type}"
    }
  )
}

resource "aws_security_group_rule" "vpce_sg_ingress" {
  for_each = {
    for sg_key in var.referenced_security_groups : sg_key => var.security_groups[sg_key].ingress
  }

  count = length(each.value)

  type              = "ingress"
  from_port         = each.value[count.index].from_port
  to_port           = each.value[count.index].to_port
  protocol          = tostring(each.value[count.index].protocol)
  cidr_blocks       = each.value[count.index].cidr_blocks
  security_group_id = aws_security_group.vpce_sg[each.key].id
}


variable "security_groups" {
  description = "All available security group configurations"
  type        = map(any)
  default     = {}
}

variable "referenced_security_groups" {
  description = "List of security group keys used by this endpoint"
  type        = list(string)
  default     = []
}


#------

resource "aws_security_group" "vpce_sg" {
  for_each = {
    for sg_key in var.referenced_security_groups :
    sg_key => var.security_groups[sg_key]
  }

  name = lower(join("-", compact([
    var.organization,
    lookup(var.region_short, var.region),
    var.rule_category,
    var.env_type,
    var.env_name,
    var.app_name,
    replace(each.value.additional_description, " ", "-"),
    var.sg_ordinal != 0 ? tostring(var.sg_ordinal) : ""
  ])))

  description         = "Security group for ${var.app_name}"
  revoke_rules_on_delete = false
  vpc_id              = var.vpc_id

  dynamic "ingress" {
    for_each = try(each.value.ingress, {})

    content {
      description      = try(ingress.value.description, "ingress for ${var.app_name}")
      from_port        = try(ingress.value.protocol, null) == "-1" ? 0 : try(ingress.value.from_port, null)
      to_port          = try(ingress.value.protocol, null) == "-1" ? 0 : try(ingress.value.to_port, null)
      protocol         = try(ingress.value.protocol, null)
      cidr_blocks      = try(ingress.value.cidr_blocks, null)
      self             = try(ingress.value.self_referencing, false)
    }
  }

  dynamic "egress" {
    for_each = try(each.value.egress, {})

    content {
      description      = try(egress.value.description, "egress for ${var.app_name}")
      from_port        = try(egress.value.protocol, null) == "-1" ? 0 : try(egress.value.from_port, null)
      to_port          = try(egress.value.protocol, null) == "-1" ? 0 : try(egress.value.to_port, null)
      protocol         = try(egress.value.protocol, null)
      cidr_blocks      = try(egress.value.cidr_blocks, null)
      self             = try(egress.value.self_referencing, false)
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      tags["tfc_run_id"]
    ]
  }
}
