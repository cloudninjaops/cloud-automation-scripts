

locals {
  sns_raw = try(local.cloud_components.sns, {})
  sns = {
    for topic_key, topic_val in local.sns_raw :
    topic_key => merge(
      topic_val,
      {
        topic_props = try(topic_val.topic_props, {})

        subscriptions = [
          for s in try(topic_val.subscriptions, []) :
          merge({ props = {} }, s)
        ]
      }
    )
  }
}

module "sns" {
  for_each = local.sns
  source   = "app.terraform.io/xyz/sns/aws"
  env_name      = var.env_name
  env_type      = var.env_type
  region        = var.region
  app_name      = local.app_name
  functionality = try(var.functionality, null)
  source_name      = try(each.value.source, null)
  destination_name = try(each.value.destination, null)
  software         = local.software
  is_fifo = try(each.value.fifo_topic, false)
  ordinal = try(index(keys(local.cloud_components.sns), each.key) + 1, 0)
  kms_key = module.kms[each.value.kms_key].key_arn
  topic_props = try(each.value.topic_props, {})
  subscriptions = try(each.value.subscriptions, [])
  tags = local.optional_tags
}
