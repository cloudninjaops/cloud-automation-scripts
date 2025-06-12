variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_groups" {
  description = "Security group config map keyed by name"
  type        = map(any)
  default     = {}
}

variable "referenced_sg_names" {
  type = list(string)
}

variable "service_name" {
  type = string
}

variable "vpc_endpoint_type" {
  type = string
}

variable "private_dns_enabled" {
  type    = bool
  default = true
}

locals {
  filtered_sgs = {
    for sg_name, sg_conf in var.security_groups :
    sg_name => sg_conf
    if contains(var.referenced_sg_names, sg_name)
  }
}

resource "aws_security_group" "vpce_sg" {
  for_each = local.filtered_sgs

  name        = "${each.key}-vpce"
  description = "Security group for VPC endpoint - ${each.key}"
  vpc_id      = var.vpc_id

  tags = merge(
    {
      Name = "${each.key}-vpce"
    },
    each.value.tags != null ? each.value.tags : {}
  )
}

resource "aws_security_group_rule" "vpce_ingress" {
  for_each = local.filtered_sgs

  type              = "ingress"
  from_port         = each.value.rules.ingress.from_port
  to_port           = each.value.rules.ingress.to_port
  protocol          = each.value.rules.ingress.protocol
  cidr_blocks       = each.value.rules.ingress.cidr_blocks
  security_group_id = aws_security_group.vpce_sg[each.key].id
}

resource "aws_vpc_endpoint" "this" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.${var.service_name}"
  vpc_endpoint_type   = var.vpc_endpoint_type
  subnet_ids          = var.vpc_endpoint_type == "Interface" ? var.subnet_ids : null
  private_dns_enabled = var.vpc_endpoint_type == "Interface" ? var.private_dns_enabled : null

  security_group_ids = var.vpc_endpoint_type == "Interface" ? [
    for sg in var.referenced_sg_names : aws_security_group.vpce_sg[sg].id
  ] : null

  tags = {
    Name = "vpce-${var.service_name}"
  }
}

###--------

locals {
  referenced_security_group_keys = tolist(keys(var.referenced_security_groups))

  referenced_security_groups_with_ordinals = {
    for idx, key in local.referenced_security_group_keys :
    key => merge(
      var.referenced_security_groups[key],
      { sg_ordinal = idx + 1 }
    )
  }
}


resource "aws_security_group" "vpce_sg" {
  for_each = local.referenced_security_groups_with_ordinals
  sg_key   = each.key

  name = lower(join("-", compact([
    var.organization,
    lookup(var.region_short, var.region),
    var.rule_category,
    var.env_type,
    var.env_name,
    var.app_name,
    replace(each.value.additional_description, " ", "-"),
    each.value.sg_ordinal != 0 ? tostring(each.value.sg_ordinal) : ""
  ])))

  ...
}
