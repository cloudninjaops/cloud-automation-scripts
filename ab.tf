locals {
  kendra_list = { for k, v in local.cloud_components.kendra : k => merge(
    v,
    {
      s3_bucket_name = try(module.s3_bucket[v.s3_bucket_key].name, null)
      s3_bucket_arn  = try(module.s3_bucket[v.s3_bucket_key].arn, null)
    }
  )}
}