import "tfplan/v2" as tfplan

# Only the SSE configuration resource on create/update
sse_cfgs = filter tfplan.resource_changes as _, r {
  r.type is "aws_s3_bucket_server_side_encryption_configuration" and
  (r.change.actions contains "create" or r.change.actions contains "update")
}

# ---- Access-log buckets: encryption REQUIRED (AES256 or any KMS) ----
violations_accesslog = filter sse_cfgs as _, r {
  ((r.change.after.bucket else "") contains "s3-accesslog") and

  # Violation if NONE of the rules provide AES256 or aws:kms with a key
  not any ((r.change.after.rule else [])) as rr {
    (
      ((rr.apply_server_side_encryption_by_default.sse_algorithm else "") == "AES256")) or (
      ((rr.apply_server_side_encryption_by_default.sse_algorithm else "") == "aws:kms") and
      (length(trim((rr.apply_server_side_encryption_by_default.kms_master_key_id else ""))) > 0))
  }
}

# ---- Non-access-log buckets: must be KMS with a CMK (reject alias/aws/s3) ----
# ---- Non-access-log buckets: must be KMS with a CMK (reject alias/aws/s3) ----
violations_cmk = filter sse_cfgs as _, r {
  not (((r.change.after.bucket else "") contains "s3-accesslog")) and

  # Violation if NONE of the inner defaults specify aws:kms with a non-managed key
  not any ((r.change.after.rule else [])) as rr {
    any ((rr.apply_server_side_encryption_by_default else [])) as d {
      ((d.sse_algorithm else "") == "aws:kms") and
      (length(trim((d.kms_master_key_id else ""))) > 0) and
      not (((d.kms_master_key_id else "") contains "alias/aws/s3"))
    }
  }
}

# Pass only if there are zero violations in both classes
main = rule {
  length(violations_accesslog) == 0 and length(violations_cmk) == 0
}
