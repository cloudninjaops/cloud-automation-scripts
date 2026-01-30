output "topic_arn" {
  value = local.topic_arn
}

output "topic_name" {
  value = local.topic_name
}

output "subscriptions" {
  description = "Map of created subscriptions keyed by protocol::endpoint"
  value = {
    for k, v in aws_sns_topic_subscription.this :
    k => {
      arn      = v.arn
      protocol = v.protocol
      endpoint = v.endpoint
    }
  }
}
