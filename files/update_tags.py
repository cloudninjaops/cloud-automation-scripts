import os
import json
import logging
import requests
import boto3
from botocore.exceptions import ClientError

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── Environment Variables ─────────────────────────────────────────────────────
TFC_TOKEN      = os.environ["TFC_TOKEN"]
TFC_ORG        = os.environ["TFC_ORG"]
WORKSPACE_NAME = os.environ["WORKSPACE_NAME"]
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")
DRY_RUN        = os.environ.get("DRY_RUN", "false").lower() == "true"

# ── New Tags to Apply ─────────────────────────────────────────────────────────
NEW_TAGS = {
    "costcenter":  os.environ.get("TAG_COSTCENTER", "100"),
    "BillingCode": os.environ.get("TAG_BILLINGCODE", "xyz"),
}

# ── TFC API Headers ───────────────────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {TFC_TOKEN}",
    "Content-Type":  "application/vnd.api+json"
}
BASE_URL = "https://app.terraform.io/api/v2"

# ── Resource types that are NOT taggable (skip list) ─────────────────────────
SKIP_RESOURCE_TYPES = {
    "aws_cloudwatch_event_bus_policy",   # policy attachment, no ARN
    "aws_cloudwatch_log_resource_policy",# policy attachment, no ARN
    "aws_cloudwatch_event_target",       # not independently taggable
    "aws_iam_instance_profile",          # not directly taggable via either API
}

# ── IAM resource types — need native API (get_resources doesn't support them) -
IAM_RESOURCE_TYPES = {
    "aws_iam_role",
    "aws_iam_policy",
    "aws_iam_user",
}

# ── Counters for final summary ────────────────────────────────────────────────
summary = {
    "total":   0,
    "tagged":  0,
    "skipped": 0,
    "no_change": 0,
    "failed":  0,
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — TFC STATE FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def get_workspace_id():
    url = f"{BASE_URL}/organizations/{TFC_ORG}/workspaces/{WORKSPACE_NAME}"
    log.info("Fetching workspace ID for: %s", WORKSPACE_NAME)
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    ws_id = r.json()["data"]["id"]
    log.info("Workspace ID: %s", ws_id)
    return ws_id


def get_state_download_url(workspace_id):
    url = f"{BASE_URL}/workspaces/{workspace_id}/current-state-version"
    log.info("Fetching latest state version...")
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    data       = r.json()["data"]
    serial     = data["attributes"]["serial"]
    created_at = data["attributes"]["created-at"]
    dl_url     = data["attributes"]["hosted-state-download-url"]
    log.info("State Serial  : %s", serial)
    log.info("State Created : %s", created_at)
    return dl_url


def download_state(download_url):
    log.info("Downloading state file...")
    r = requests.get(download_url, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def parse_resources(state):
    """
    Parse state file and return list of managed resources with their
    type, name, id, arn, and existing tags.
    """
    resources  = state.get("resources", [])
    managed    = [r for r in resources if r.get("mode") == "managed"]
    parsed     = []

    for res in managed:
        rtype  = res.get("type", "")
        rname  = res.get("name", "")
        module = res.get("module", "root")

        for instance in res.get("instances", []):
            attrs = instance.get("attributes", {})
            parsed.append({
                "type":   rtype,
                "name":   rname,
                "module": module,
                "id":     attrs.get("id"),
                "arn":    attrs.get("arn"),
                "bucket": attrs.get("bucket"),   # S3 specific
                "tags":   attrs.get("tags") or {},
            })

    log.info("Total managed resources found in state: %d", len(parsed))
    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TAG MERGE LOGIC (core of the script)
# ══════════════════════════════════════════════════════════════════════════════

def compute_tag_changes(existing_tags, new_tags):
    """
    Compare existing tags with new tags and return only what needs to change.

    Scenarios:
      1. Key absent in existing       → ADD
      2. Key present, same value      → SKIP (no change)
      3. Key present, different value → OVERWRITE
      4. No existing tags at all      → ADD all new tags
    """
    changes = {}
    for key, value in new_tags.items():
        if key not in existing_tags:
            changes[key] = {"action": "ADD",       "new_value": value, "old_value": None}
        elif existing_tags[key] != value:
            changes[key] = {"action": "OVERWRITE", "new_value": value, "old_value": existing_tags[key]}
        # else: same value — no change needed

    return changes


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — RESOURCE GROUPS TAGGING API (Tier 1 — covers most resources)
# ══════════════════════════════════════════════════════════════════════════════

def get_existing_tags_rg(rg_client, arn):
    """
    Read existing tags for a resource via Resource Groups Tagging API.
    Returns empty dict if resource has no tags or is not found.
    """
    try:
        response = rg_client.get_resources(
            ResourceARNList=[arn],
            ResourcesPerPage=1
        )
        resource_list = response.get("ResourceTagMappingList", [])
        if not resource_list:
            return {}  # resource exists but has no tags
        tag_list = resource_list[0].get("Tags", [])
        return {t["Key"]: t["Value"] for t in tag_list}
    except ClientError as e:
        log.warning("Could not read tags for %s: %s", arn, e)
        return {}


def apply_tags_rg(rg_client, arn, tags_to_apply):
    """
    Apply tags to a resource via Resource Groups Tagging API.
    tags_to_apply is a flat dict of {key: value}.
    """
    try:
        response = rg_client.tag_resources(
            ResourceARNList=[arn],
            Tags=tags_to_apply
        )
        failed = response.get("FailedResourcesMap", {})
        if failed:
            log.error("Tagging failed for %s: %s", arn, failed)
            return False
        return True
    except ClientError as e:
        log.error("Error tagging %s: %s", arn, e)
        return False


def process_resource_rg(rg_client, resource):
    """
    Full process for a single resource via Resource Groups Tagging API:
    read → compare → write (if needed).
    """
    arn   = resource.get("arn")
    rtype = resource["type"]
    rname = resource["name"]
    label = f"{rtype}/{rname}"

    if not arn or arn == "N/A":
        log.warning("[SKIP] %s — no ARN available", label)
        summary["skipped"] += 1
        return

    # Read existing tags
    existing_tags = get_existing_tags_rg(rg_client, arn)

    # Compute what needs to change
    changes = compute_tag_changes(existing_tags, NEW_TAGS)

    if not changes:
        log.info("[NO CHANGE] %s — all tags already up to date", label)
        summary["no_change"] += 1
        return

    # Log what will change
    for key, info in changes.items():
        if info["action"] == "ADD":
            log.info("  [%s] %s — ADD    %s = %s", "DRY-RUN" if DRY_RUN else "APPLY", label, key, info["new_value"])
        else:
            log.info("  [%s] %s — OVERWRITE %s: '%s' → '%s'",
                     "DRY-RUN" if DRY_RUN else "APPLY",
                     label, key, info["old_value"], info["new_value"])

    if DRY_RUN:
        summary["skipped"] += 1
        return

    # Apply only the changed tags
    tags_to_apply = {k: v["new_value"] for k, v in changes.items()}
    success = apply_tags_rg(rg_client, arn, tags_to_apply)

    if success:
        log.info("[OK] %s — tagged successfully", label)
        summary["tagged"] += 1
    else:
        summary["failed"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — IAM NATIVE API (Tier 2 — IAM roles and policies)
# ══════════════════════════════════════════════════════════════════════════════

def get_existing_tags_iam_role(iam_client, role_name):
    try:
        response  = iam_client.list_role_tags(RoleName=role_name)
        tag_list  = response.get("Tags", [])
        return {t["Key"]: t["Value"] for t in tag_list}
    except ClientError as e:
        log.warning("Could not read tags for IAM role %s: %s", role_name, e)
        return {}


def get_existing_tags_iam_policy(iam_client, policy_arn):
    try:
        response  = iam_client.list_policy_tags(PolicyArn=policy_arn)
        tag_list  = response.get("Tags", [])
        return {t["Key"]: t["Value"] for t in tag_list}
    except ClientError as e:
        log.warning("Could not read tags for IAM policy %s: %s", policy_arn, e)
        return {}


def process_iam_resource(iam_client, resource):
    """
    Full process for IAM roles and policies:
    native read → compare → native write (if needed).
    """
    rtype = resource["type"]
    rname = resource["name"]
    rid   = resource.get("id")
    arn   = resource.get("arn")
    label = f"{rtype}/{rname}"

    if rtype == "aws_iam_role":
        if not rid:
            log.warning("[SKIP] %s — no role name available", label)
            summary["skipped"] += 1
            return
        existing_tags = get_existing_tags_iam_role(iam_client, rid)
        changes       = compute_tag_changes(existing_tags, NEW_TAGS)

        if not changes:
            log.info("[NO CHANGE] %s — all tags already up to date", label)
            summary["no_change"] += 1
            return

        for key, info in changes.items():
            log.info("  [%s] %s — %s %s = %s",
                     "DRY-RUN" if DRY_RUN else "APPLY",
                     label, info["action"], key, info["new_value"])

        if DRY_RUN:
            summary["skipped"] += 1
            return

        try:
            tags_to_apply = [{"Key": k, "Value": v["new_value"]} for k, v in changes.items()]
            iam_client.tag_role(RoleName=rid, Tags=tags_to_apply)
            log.info("[OK] IAM Role %s — tagged successfully", rid)
            summary["tagged"] += 1
        except ClientError as e:
            log.error("[FAILED] IAM Role %s: %s", rid, e)
            summary["failed"] += 1

    elif rtype == "aws_iam_policy":
        if not arn:
            log.warning("[SKIP] %s — no ARN available", label)
            summary["skipped"] += 1
            return
        existing_tags = get_existing_tags_iam_policy(iam_client, arn)
        changes       = compute_tag_changes(existing_tags, NEW_TAGS)

        if not changes:
            log.info("[NO CHANGE] %s — all tags already up to date", label)
            summary["no_change"] += 1
            return

        for key, info in changes.items():
            log.info("  [%s] %s — %s %s = %s",
                     "DRY-RUN" if DRY_RUN else "APPLY",
                     label, info["action"], key, info["new_value"])

        if DRY_RUN:
            summary["skipped"] += 1
            return

        try:
            tags_to_apply = [{"Key": k, "Value": v["new_value"]} for k, v in changes.items()]
            iam_client.tag_policy(PolicyArn=arn, Tags=tags_to_apply)
            log.info("[OK] IAM Policy %s — tagged successfully", arn)
            summary["tagged"] += 1
        except ClientError as e:
            log.error("[FAILED] IAM Policy %s: %s", arn, e)
            summary["failed"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(resources):
    log.info("=" * 60)
    log.info("TAGGING SUMMARY")
    log.info("=" * 60)
    log.info("Total resources in state : %d", summary["total"])
    log.info("Successfully tagged      : %d", summary["tagged"])
    log.info("No change needed         : %d", summary["no_change"])
    log.info("Skipped                  : %d", summary["skipped"])
    log.info("Failed                   : %d", summary["failed"])
    log.info("Mode                     : %s", "DRY-RUN" if DRY_RUN else "LIVE")
    log.info("=" * 60)


def main():
    # ── Fetch state from TFC ──────────────────────────────────────────────────
    ws_id     = get_workspace_id()
    dl_url    = get_state_download_url(ws_id)
    state     = download_state(dl_url)
    resources = parse_resources(state)

    summary["total"] = len(resources)

    if DRY_RUN:
        log.info("*** DRY-RUN MODE — no changes will be applied ***")

    log.info("New tags to apply: %s", json.dumps(NEW_TAGS))

    # ── boto3 clients ─────────────────────────────────────────────────────────
    session    = boto3.Session(region_name=AWS_REGION)
    rg_client  = session.client("resourcegroupstaggingapi")
    iam_client = session.client("iam")

    # ──────────────────────────────────────────────────────────────────────────
    # TEST CONDITION 1 — Limit to first N resources (for testing)
    # Uncomment the block below to process only the first 4 resources
    # ──────────────────────────────────────────────────────────────────────────
    # MAX_RESOURCES = 4
    # if len(resources) > MAX_RESOURCES:
    #     log.info("[TEST MODE] Limiting to first %d resources", MAX_RESOURCES)
    #     resources = resources[:MAX_RESOURCES]

    # ──────────────────────────────────────────────────────────────────────────
    # TEST CONDITION 2 — Filter to specific resource types only (for testing)
    # Uncomment the block below to process only specific resource types
    # ──────────────────────────────────────────────────────────────────────────
    # ALLOWED_RESOURCE_TYPES = ["aws_instance", "aws_s3_bucket"]
    # resources = [r for r in resources if r["type"] in ALLOWED_RESOURCE_TYPES]
    # if resources:
    #     log.info("[TEST MODE] Filtering to resource types: %s — %d resources found",
    #              ALLOWED_RESOURCE_TYPES, len(resources))
    # else:
    #     log.warning("[TEST MODE] No resources found matching types: %s", ALLOWED_RESOURCE_TYPES)

    # ── Process each resource ─────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Processing %d resources...", len(resources))
    log.info("=" * 60)

    for resource in resources:
        rtype = resource["type"]

        # Skip non-taggable resource types
        if rtype in SKIP_RESOURCE_TYPES:
            log.info("[SKIP] %s/%s — resource type not taggable", rtype, resource["name"])
            summary["skipped"] += 1
            continue

        # Route IAM resources to native IAM API (Tier 2)
        if rtype in IAM_RESOURCE_TYPES:
            process_iam_resource(iam_client, resource)

        # All other resources via Resource Groups Tagging API (Tier 1)
        else:
            process_resource_rg(rg_client, resource)

    # ── Print final summary ───────────────────────────────────────────────────
    print_summary(resources)


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.HTTPError as e:
        log.error("TFC API HTTP Error: %s - %s", e.response.status_code, e.response.text)
        raise
    except Exception as e:
        log.error("Unexpected error: %s", str(e))
        raise
