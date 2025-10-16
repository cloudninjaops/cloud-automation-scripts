import "tfplan/v2" as tfplan

# Consider only the dedicated SSE configuration resource on create/update.
sse_cfgs = filter tfplan.resource_changes as _, r {
  r.type is "aws_s3_bucket_server_side_encryption_configuration" and
  (r.change.actions contains "create" or r.change.actions contains "update")
}

# ---- Violations for access-log buckets: encryption REQUIRED (AES256 or any KMS) ----
violations_accesslog = filter sse_cfgs as _, r {
  # access-log bucket detection (safe: default bucket to "")
  ((r.change.after.bucket else "") contains "s3-accesslog") and

  # not encrypted as required
  not (
    ((r.change.after.rule[0].apply_server_side_encryption_by_default.sse_algorithm else "") == "AES256") or
    (
      ((r.change.after.rule[0].apply_server_side_encryption_by_default.sse_algorithm else "") == "aws:kms") and
      (length(trim((r.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id else ""))) > 0)))
}

# ---- Violations for non-access-log buckets: must be KMS with a CMK (not alias/aws/s3) ----
violations_cmk = filter sse_cfgs as _, r {
  not (((r.change.after.bucket else "") contains "s3-accesslog")) and

  # not using CMK
  not (
    ((r.change.after.rule[0].apply_server_side_encryption_by_default.sse_algorithm else "") == "aws:kms") and
    (length(trim((r.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id else ""))) > 0) and
    not (((r.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id else "") contains "alias/aws/s3")))
}

# Pass only if there are zero violations in both buckets classes.
main = rule {
  length(violations_accesslog) == 0 and length(violations_cmk) == 0
}
