locals {
  # ---- Naming recipe (same spirit as your original module) ----
  # <Org>-<EnvType>-<EnvName>-<Region>-sns-<App>-<Func>-<Source>-<Dest>-<Software>-<user_defined>-<Ordinal>
  region_token = lookup(var.region_short, var.region, var.region)

  topic_base_name = join(
    "-",
    compact([
      var.organization,
      var.env_type,
      var.env_name,
      local.region_token,
      "sns",
      var.app_name,
      var.functionality,
      var.source_name,
      var.destination_name,
      var.software,
      var.user_defined,
      tostring(var.ordinal),
    ])
  )

  sns_topic_name = var.is_fifo ? "${local.topic_base_name}.fifo" : local.topic_base_name

  tp = try(var.topic_props, {})

  # Topic-level properties
  display_name = try(local.tp.display_name, null)

  # delivery_policy can be provided as YAML map (preferred) or raw JSON string.
  topic_delivery_policy = (
    try(local.tp.delivery_policy, null) == null
    ? null
    : (
      can(keys(local.tp.delivery_policy))
      ? jsonencode(local.tp.delivery_policy)
      : tostring(local.tp.delivery_policy)
    )
  )

  # FIFO-only props live under topic_props.fifo_props
  fifo_props                    = try(local.tp.fifo_props, {})
  content_based_deduplication   = try(local.fifo_props.content_based_deduplication, null)
  deduplication_scope           = try(local.fifo_props.deduplication_scope, null)
  fifo_throughput_limit         = try(local.fifo_props.fifo_throughput_limit, null)

  # Topic ARN/name switcher
  topic_arn  = var.is_fifo ? aws_sns_topic.fifo[0].arn  : aws_sns_topic.standard[0].arn
  topic_name = var.is_fifo ? aws_sns_topic.fifo[0].name : aws_sns_topic.standard[0].name

  # Subscriptions normalized (driver already adds props={}, but module is resilient)
  subs = [
    for s in var.subscriptions : merge({ props = {} }, s)
  ]
}

# -----------------------------
# Standard topic (no FIFO args)
# -----------------------------
resource "aws_sns_topic" "standard" {
  count = var.is_fifo ? 0 : 1

  name             = local.sns_topic_name
  kms_master_key_id = var.kms_key

  # Safe to set when null (provider accepts); if you hit provider issues here later,
  # we can split again, but typically not needed.
  display_name   = local.display_name
  delivery_policy = local.topic_delivery_policy

  tags = var.tags
}

# -----------------------------
# FIFO topic (FIFO-only args)
# -----------------------------
resource "aws_sns_topic" "fifo" {
  count = var.is_fifo ? 1 : 0

  name              = local.sns_topic_name
  kms_master_key_id = var.kms_key

  fifo_topic = true

  # FIFO-only attributes
  # (set only on this resource to avoid standard topic errors)
  content_based_deduplication = local.content_based_deduplication
  deduplication_scope         = local.deduplication_scope
  fifo_throughput_limit       = local.fifo_throughput_limit

  # Still allowed on FIFO
  display_name    = local.display_name
  delivery_policy = local.topic_delivery_policy

  tags = var.tags
}

# -----------------------------
# Subscriptions
# -----------------------------
resource "aws_sns_topic_subscription" "this" {
  for_each = {
    for s in local.subs :
    "${try(s.protocol, "unknown")}::${try(s.endpoint, "unknown")}" => s
  }

  topic_arn = local.topic_arn
  protocol  = each.value.protocol
  endpoint  = each.value.endpoint

  # ---- subscription props (optional) ----
  # Only valid for http/https
  endpoint_auto_confirms = (
    contains(["http", "https"], lower(tostring(each.value.protocol)))
    ? try(each.value.props.endpoint_auto_confirms, null)
    : null
  )

  raw_message_delivery = try(each.value.props.raw_message_delivery, null)

  # filter_policy can be map or json string
  filter_policy = (
    try(each.value.props.filter_policy, null) == null
    ? null
    : (
      can(keys(each.value.props.filter_policy))
      ? jsonencode(each.value.props.filter_policy)
      : tostring(each.value.props.filter_policy)
    )
  )

  filter_policy_scope = try(each.value.props.filter_policy_scope, null)

  # redrive_policy can be map or json string
  redrive_policy = (
    try(each.value.props.redrive_policy, null) == null
    ? null
    : (
      can(keys(each.value.props.redrive_policy))
      ? jsonencode(each.value.props.redrive_policy)
      : tostring(each.value.props.redrive_policy)
    )
  )

  # delivery_policy can be map or json string (mostly for http/https)
  delivery_policy = (
    try(each.value.props.delivery_policy, null) == null
    ? null
    : (
      can(keys(each.value.props.delivery_policy))
      ? jsonencode(each.value.props.delivery_policy)
      : tostring(each.value.props.delivery_policy)
    )
  )
}
