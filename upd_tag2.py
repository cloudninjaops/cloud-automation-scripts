def main():
    # ── Fetch state from TFC ──────────────────────────────────────────────
    ws_id     = get_workspace_id()
    dl_url    = get_state_download_url(ws_id)
    state     = download_state(dl_url)
    resources = parse_resources(state)

    # ── Assume role in Account B ──────────────────────────────────────────
    session  = assume_role(ACCOUNT_B_ROLE_ARN)

    # ── Get Account B ID — needed for EC2 ARN construction ───────────────
    global ACCOUNT_ID
    ACCOUNT_ID = session.client("sts").get_caller_identity()["Account"]
    log.info("Operating in Account : %s", ACCOUNT_ID)
    log.info("Region               : %s", AWS_REGION)

    # ── boto3 clients — all using Account B session ───────────────────────
    rg_client  = session.client("resourcegroupstaggingapi")
    iam_client = session.client("iam")
    ec2_client = session.client("ec2")

    # ── Extra resources from YAML via RESOURCES_LIST ──────────────────────
    extra_resources = parse_extra_resources()

    # ── Merge + deduplicate ───────────────────────────────────────────────
    all_resources = deduplicate(resources + extra_resources)

    log.info("State file resources : %d", len(resources))
    log.info("Extra resources      : %d", len(extra_resources))
    log.info("Total after dedup    : %d", len(all_resources))
    log.info("New tags to apply    : %s", json.dumps(NEW_TAGS))

    summary["total"] = len(all_resources)

    if DRY_RUN:
        log.info("*** DRY-RUN MODE — no changes will be applied ***")

    # ── Process each resource ─────────────────────────────────────────────
    for resource in all_resources:
        rtype = resource["type"]

        if rtype in SKIP_RESOURCE_TYPES:
            log.info("[SKIP] %s/%s — not taggable", rtype, resource["name"])
            summary["skipped"] += 1

        elif rtype in IAM_RESOURCE_TYPES:
            process_iam_resource(iam_client, resource)

        elif rtype == "extra_instance_id":
            process_ec2_id(ec2_client, resource)

        else:
            process_resource_rg(rg_client, resource)

    print_summary(all_resources)