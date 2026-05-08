def parse_extra_resources():
    """
    Reads RESOURCES_LIST env var — JSON encoded from YAML via Terraform jsonencode().
    Structure:
      {
        "arns":         [...],
        "instance_ids": [...],
        "s3_buckets":   [...],
        "iam_arns":     [...]
      }
    """
    extra = []

    raw = os.environ.get("RESOURCES_LIST", "").strip()

    # Guard — if not set or empty skip gracefully
    if not raw:
        log.info("RESOURCES_LIST not set or empty — skipping extra resources")
        return extra

    try:
        cleaned = re.sub(r'\s+', ' ', raw).strip()
        cleaned = cleaned.strip("'").strip('"')
        data    = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.error("Failed to parse RESOURCES_LIST JSON: %s", e)
        return extra

    # ── Safe list getter ──────────────────────────────────────────────────
    def safe_list(key):
        val = data.get(key)
        if not val:
            return []
        if not isinstance(val, list):
            log.warning("RESOURCES_LIST.%s is not a list — skipping", key)
            return []
        return [x.strip() for x in val if x and str(x).strip()]

    # ── ARNs — any service except IAM and S3 ──────────────────────────────
    for arn in safe_list("arns"):
        extra.append({
            "type":   "extra_arn",
            "name":   arn.split(":")[-1],
            "module": "extra",
            "id":     None,
            "arn":    arn,
            "bucket": None,
            "tags":   {}
        })

    # ── EC2 family IDs ────────────────────────────────────────────────────
    for instance_id in safe_list("instance_ids"):
        constructed_arn = f"arn:aws:ec2:{AWS_REGION}:{ACCOUNT_ID}:instance/{instance_id}"
        extra.append({
            "type":   "aws_instance",
            "name":   instance_id,
            "module": "extra",
            "id":     instance_id,
            "arn":    constructed_arn,
            "bucket": None,
            "tags":   {}
        })

    # ── S3 buckets ────────────────────────────────────────────────────────
    for bucket in safe_list("s3_buckets"):
        extra.append({
            "type":   "aws_s3_bucket",
            "name":   bucket,
            "module": "extra",
            "id":     bucket,
            "arn":    f"arn:aws:s3:::{bucket}",
            "bucket": bucket,
            "tags":   {}
        })

    # ── IAM ARNs ──────────────────────────────────────────────────────────
    for arn in safe_list("iam_arns"):
        rtype = "aws_iam_role" if ":role/" in arn else "aws_iam_policy"
        extra.append({
            "type":   rtype,
            "name":   arn.split("/")[-1],
            "module": "extra",
            "id":     arn.split("/")[-1],
            "arn":    arn,
            "bucket": None,
            "tags":   {}
        })

    log.info("Extra resources loaded from RESOURCES_LIST: %d total", len(extra))
    return extra