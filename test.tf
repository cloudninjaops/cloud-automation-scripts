import "tfplan/v2" as tfplan

violations = filter(tfplan.resource_changes or []) as _, rc {
  rc.type is "aws_s3_bucket_server_side_encryption_configuration" and
  (rc.change.actions contains "create" or rc.change.actions contains "update") and

  # ---- exception: skip access-log buckets ----
  (
    not (
      (rc.change.after contains "bucket") and
      (type(rc.change.after.bucket) is string) and
      (rc.change.after.bucket contains "s3-accesslog")
    )
  ) and

  # ---- safe guards before reading fields ----
  (rc.change.after contains "rule") and
  (type(rc.change.after.rule) is list) and
  (length(rc.change.after.rule) > 0) and
  (type(rc.change.after.rule[0]) is map) and
  (rc.change.after.rule[0] contains "apply_server_side_encryption_by_default") and
  (type(rc.change.after.rule[0].apply_server_side_encryption_by_default) is map) and

  # ---- CMK must be used (NOT alias/aws/s3) ----
  not (
    (rc.change.after.rule[0].apply_server_side_encryption_by_default contains "sse_algorithm") and
    (rc.change.after.rule[0].apply_server_side_encryption_by_default.sse_algorithm == "aws:kms") and
    (rc.change.after.rule[0].apply_server_side_encryption_by_default contains "kms_master_key_id") and
    (type(rc.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id) is string) and
    (length(trim(rc.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id)) > 0) and
    not (rc.change.after.rule[0].apply_server_side_encryption_by_default.kms_master_key_id contains "alias/aws/s3")
  )
}

main = rule { length(violations) == 0 }
