import os
import re
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
TFC_TOKEN          = os.environ.get("TFC_TOKEN", "")
TFC_ORG            = os.environ.get("TFC_ORG", "")
AWS_REGION         = os.environ.get("AWS_REGION", "us-east-1")
DRY_RUN            = os.environ.get("DRY_RUN", "true").lower() == "true"
ACCOUNT_B_ROLE_ARN = os.environ.get("ACCOUNT_B_ROLE_ARN", "")

# ── TAGGING_CONFIG — full YAML passed as JSON from Terraform ──────────────────
TAGGING_CONFIG_RAW = os.environ.get("TAGGING_CONFIG", "").strip()

# ── Global ACCOUNT_ID — set after assume_role ─────────────────────────────────
ACCOUNT_ID = ""

# ── TFC API Headers ───────────────────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {TFC_TOKEN}",
    "Content-Type":  "application/vnd.api+json"
}
BASE_URL = "https://app.terraform.io/api/v2"

# ── Resource types that are NOT taggable ──────────────────────────────────────
SKIP_RESOURCE_TYPES = {
    "aws_cloudwatch_event_bus_policy",
    "aws_cloudwatch_log_resource_policy",
    "aws_cloudwatch_event_target",
    "aws_iam_instance_profile",
    "null_resource",
}

# ── IAM resource types — need native API ─────────────────────────────────────
IAM_RESOURCE_TYPES = {
    "aws_iam_role",
    "aws_iam_policy",
    "aws_iam_user",
}

# ── Summary counters ──────────────────────────────────────────────────────────
summary = {
    "total":     0,
    "tagged":    0,
    "skipped":   0,
    "no_change": 0,
    "failed":    0,
}


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PARSE TAGGING CONFIG FROM YAML
# ══════════════════════════════════════════════════════════════════════════════

def parse_tagging_config():
    """
    Parse TAGGING_CONFIG env var — full YAML passed as JSON by Terraform.
    Returns parsed tagging config dict.
    """
    if not TAGGING_CONFIG_RAW:
        log.error("TAGGING_CONFIG env var is not set or empty — exiting.")
        exit(1)

    try:
        cleaned = re.sub(r'\s+', ' ', TAGGING_CONFIG_RAW).strip()
        cleaned = cleaned.strip("'").strip('"')
        data    = json.loads(cleaned)
        return data.get("tagging", data)
    except json.JSONDecodeError as e:
        log.error("Failed to parse TAGGING_CONFIG JSON: %s", e)
        exit(1)


def validate_tagging_config(tagging):
    """
    Basic validation — must have config and at least workspace or tagsets.
    """
    errors = []

    if not tagging.get("config"):
        errors.append("'config' block is missing")

    has_workspace = bool(tagging.get("workspace", {}).get("name"))
    has_tagsets   = bool(tagging.get("tagsets"))

    if not has_workspace and not has_tagsets:
        errors.append(
            "Must provide at least one of: "
            "'workspace.name' OR 'tagsets' with resources_list OR both"
        )

    if errors:
        log.error("=" * 60)
        log.error("YAML VALIDATION FAILED:")
        for err in errors:
            log.error("  - %s", err)
        log.error("=" * 60)
        exit(1)

    log.info("YAML validation passed")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TFC STATE FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def get_workspace_id(workspace_name):
    url = f"{BASE_URL}/organizations/{TFC_ORG}/workspaces/{workspace_name}"
    log.info("Fetching workspace ID for: %s", workspace_name)
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    ws_id = r.json()["data"]["id"]
    log.info("Workspace ID          : %s", ws_id)
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
    log.info("State Serial          : %s", serial)
    log.info("State Created         : %s", created_at)
    return dl_url


def download_state(download_url):
    log.info("Downloading state file...")
    r = requests.get(download_url, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def parse_state_resources(state):
    """
    Parse state file — return list of managed resources.
    Skips data sources and non-taggable types.
    """
    resources = state.get("resources", [])
    managed   = [r for r in resources if r.get("mode") == "managed"]
    parsed    = []

    for res in managed:
        rtype  = res.get("type", "")
        rname  = res.get("name", "")
        module = res.get("module", "root")

        for instance in res.get("instances", []):
            attrs  = instance.get("attributes", {})
            res_id = attrs.get("id")
            arn    = attrs.get("arn")

            # Construct EC2 ARN if missing
            if rtype == "aws_instance" and not arn and res_id:
                arn = f"arn:aws:ec2:{AWS_REGION}:{ACCOUNT_ID}:instance/{res_id}"

            parsed.append({
                "type":   rtype,
                "name":   rname,
                "module": module,
                "id":     res_id,
                "arn":    arn,
                "bucket": attrs.get("bucket"),
                "tags":   attrs.get("tags") or {},
            })

    log.info("State file resources  : %d", len(parsed))
    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PARSE TAGSET RESOURCES
# ══════════════════════════════════════════════════════════════════════════════

def parse_tagset_resources(resources_list):
    """
    Parse resources_list from a tagset.
    Returns list of resource dicts in same format as state resources.
    """
    parsed = []

    if not resources_list:
        return parsed

    # ── Safe list getter ──────────────────────────────────────────────────
    def safe_list(key):
        val = resources_list.get(key)
        if not val:
            return []
        if not isinstance(val, list):
            log.warning("resources_list.%s is not a list — skipping", key)
            return []
        return [x.strip() for x in val if x and str(x).strip()]

    # ── ARNs ──────────────────────────────────────────────────────────────
    for arn in safe_list("arns"):
        parsed.append({
            "type":   "extra_arn",
            "name":   arn.split(":")[-1],
            "module": "tagset",
            "id":     None,
            "arn":    arn,
            "bucket": None,
            "tags":   {}
        })

    # ── EC2 family IDs ────────────────────────────────────────────────────
    for instance_id in safe_list("instance_ids"):
        constructed_arn = f"arn:aws:ec2:{AWS_REGION}:{ACCOUNT_ID}:instance/{instance_id}"
        parsed.append({
            "type":   "aws_instance",
            "name":   instance_id,
            "module": "tagset",
            "id":     instance_id,
            "arn":    constructed_arn,
            "bucket": None,
            "tags":   {}
        })

    # ── S3 buckets ────────────────────────────────────────────────────────
    for bucket in safe_list("s3_buckets"):
        parsed.append({
            "type":   "aws_s3_bucket",
            "name":   bucket,
            "module": "tagset",
            "id":     bucket,
            "arn":    f"arn:aws:s3:::{bucket}",
            "bucket": bucket,
            "tags":   {}
        })

    # ── IAM ARNs ──────────────────────────────────────────────────────────
    for arn in safe_list("iam_arns"):
        rtype = "aws_iam_role" if ":role/" in arn else "aws_iam_policy"
        parsed.append({
            "type":   rtype,
            "name":   arn.split("/")[-1],
            "module": "tagset",
            "id":     arn.split("/")[-1],
            "arn":    arn,
            "bucket": None,
            "tags":   {}
        })

    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate(resources):
    seen   = set()
    unique = []
    for res in resources:
        key = res.get("arn") or f"{res['type']}:{res.get('id')}"
        if key and key not in seen:
            seen.add(key)
            unique.append(res)
        elif not key:
            unique.append(res)
    return unique


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — TAG MERGE LOGIC
# ══════════════════════════════════════════════════════════════════════════════

def compute_tag_changes(existing_tags, new_tags):
    """
    Scenario 1 — key absent        → ADD
    Scenario 2 — same value        → skip
    Scenario 3 — different value   → OVERWRITE
    Scenario 4 — no existing tags  → ADD all
    """
    changes = {}
    for key, value in new_tags.items():
        value = str(value)  # force string — AWS API requires strings
        if key not in existing_tags:
            changes[key] = {"action": "ADD",       "new_value": value, "old_value": None}
        elif existing_tags[key] != value:
            changes[key] = {"action": "OVERWRITE", "new_value": value, "old_value": existing_tags[key]}
    return changes


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — RESOURCE GROUPS TAGGING API (Tier 1)
# ══════════════════════════════════════════════════════════════════════════════

def get_existing_tags_rg(rg_client, arn):
    try:
        response      = rg_client.get_resources(ResourceARNList=[arn])
        resource_list = response.get("ResourceTagMappingList", [])
        if not resource_list:
            return {}
        return {t["Key"]: t["Value"] for t in resource_list[0].get("Tags", [])}
    except ClientError as e:
        log.warning("Could not read tags for %s: %s", arn, e)
        return {}


def apply_tags_rg(rg_client, arn, tags_to_apply):
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


def process_resource_rg(rg_client, resource, new_tags):
    arn   = resource.get("arn")
    rtype = resource["type"]
    rname = resource["name"]
    label = f"{rtype}/{rname}"

    if not arn or arn == "N/A":
        log.warning("[SKIP] %s — no ARN available", label)
        summary["skipped"] += 1
        return

    existing_tags = get_existing_tags_rg(rg_client, arn)
    changes       = compute_tag_changes(existing_tags, new_tags)

    if not changes:
        log.info("[NO CHANGE] %s — all tags up to date", label)
        summary["no_change"] += 1
        return

    for key, info in changes.items():
        log.info("  [%s] %s — %s %s: %s → %s",
                 "DRY-RUN" if DRY_RUN else "APPLY",
                 label, info["action"], key,
                 info["old_value"], info["new_value"])

    if DRY_RUN:
        summary["skipped"] += 1
        return

    tags_to_apply = {k: v["new_value"] for k, v in changes.items()}
    success       = apply_tags_rg(rg_client, arn, tags_to_apply)

    if success:
        log.info("[OK] %s — tagged successfully", label)
        summary["tagged"] += 1
    else:
        summary["failed"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — IAM NATIVE API (Tier 2)
# ══════════════════════════════════════════════════════════════════════════════

def process_iam_resource(iam_client, resource, new_tags):
    rtype = resource["type"]
    rname = resource["name"]
    rid   = resource.get("id")
    arn   = resource.get("arn")
    label = f"{rtype}/{rname}"

    try:
        if rtype == "aws_iam_role":
            if not rid:
                log.warning("[SKIP] %s — no role name", label)
                summary["skipped"] += 1
                return
            response      = iam_client.list_role_tags(RoleName=rid)
            existing_tags = {t["Key"]: t["Value"] for t in response.get("Tags", [])}
            changes       = compute_tag_changes(existing_tags, new_tags)

            if not changes:
                log.info("[NO CHANGE] %s — all tags up to date", label)
                summary["no_change"] += 1
                return

            for key, info in changes.items():
                log.info("  [%s] %s — %s %s: %s → %s",
                         "DRY-RUN" if DRY_RUN else "APPLY",
                         label, info["action"], key,
                         info["old_value"], info["new_value"])

            if DRY_RUN:
                summary["skipped"] += 1
                return

            iam_client.tag_role(
                RoleName=rid,
                Tags=[{"Key": k, "Value": v["new_value"]} for k, v in changes.items()]
            )
            log.info("[OK] %s — tagged successfully", label)
            summary["tagged"] += 1

        elif rtype == "aws_iam_policy":
            if not arn:
                log.warning("[SKIP] %s — no ARN", label)
                summary["skipped"] += 1
                return
            response      = iam_client.list_policy_tags(PolicyArn=arn)
            existing_tags = {t["Key"]: t["Value"] for t in response.get("Tags", [])}
            changes       = compute_tag_changes(existing_tags, new_tags)

            if not changes:
                log.info("[NO CHANGE] %s — all tags up to date", label)
                summary["no_change"] += 1
                return

            for key, info in changes.items():
                log.info("  [%s] %s — %s %s: %s → %s",
                         "DRY-RUN" if DRY_RUN else "APPLY",
                         label, info["action"], key,
                         info["old_value"], info["new_value"])

            if DRY_RUN:
                summary["skipped"] += 1
                return

            iam_client.tag_policy(
                PolicyArn=arn,
                Tags=[{"Key": k, "Value": v["new_value"]} for k, v in changes.items()]
            )
            log.info("[OK] %s — tagged successfully", label)
            summary["tagged"] += 1

    except ClientError as e:
        log.error("[FAILED] %s: %s", label, e)
        summary["failed"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — EC2 NATIVE API (Tier 3)
# ══════════════════════════════════════════════════════════════════════════════

def process_ec2_id(ec2_client, resource, new_tags):
    resource_id = resource.get("id")
    label       = f"ec2_instance/{resource_id}"

    if not resource_id:
        log.warning("[SKIP] %s — no ID available", label)
        summary["skipped"] += 1
        return

    try:
        response      = ec2_client.describe_tags(
            Filters=[{"Name": "resource-id", "Values": [resource_id]}]
        )
        existing_tags = {t["Key"]: t["Value"] for t in response.get("Tags", [])}
    except ClientError as e:
        log.warning("Could not read tags for %s: %s", resource_id, e)
        existing_tags = {}

    changes = compute_tag_changes(existing_tags, new_tags)

    if not changes:
        log.info("[NO CHANGE] %s — all tags up to date", label)
        summary["no_change"] += 1
        return

    for key, info in changes.items():
        log.info("  [%s] %s — %s %s: %s → %s",
                 "DRY-RUN" if DRY_RUN else "APPLY",
                 label, info["action"], key,
                 info["old_value"], info["new_value"])

    if DRY_RUN:
        summary["skipped"] += 1
        return

    try:
        ec2_client.create_tags(
            Resources=[resource_id],
            Tags=[{"Key": k, "Value": v["new_value"]} for k, v in changes.items()]
        )
        log.info("[OK] %s — tagged successfully", label)
        summary["tagged"] += 1
    except ClientError as e:
        log.error("[FAILED] %s: %s", resource_id, e)
        summary["failed"] += 1


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — PROCESS RESOURCES
# ══════════════════════════════════════════════════════════════════════════════

def process_resources(resources, new_tags, rg_client, iam_client, ec2_client):
    """
    Route each resource to correct tagging handler.
    """
    for resource in resources:
        rtype = resource["type"]

        if rtype in SKIP_RESOURCE_TYPES:
            log.info("[SKIP] %s/%s — not taggable", rtype, resource["name"])
            summary["skipped"] += 1

        elif rtype in IAM_RESOURCE_TYPES:
            process_iam_resource(iam_client, resource, new_tags)

        elif rtype == "extra_instance_id":
            process_ec2_id(ec2_client, resource, new_tags)

        else:
            process_resource_rg(rg_client, resource, new_tags)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — ASSUME ROLE
# ══════════════════════════════════════════════════════════════════════════════

def assume_role(role_arn, session_name="tfc-tagging-session"):
    log.info("Assuming role         : %s", role_arn)
    sts_client = boto3.client("sts")
    response   = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )
    creds = response["Credentials"]
    log.info("Role assumed successfully")
    return boto3.Session(
        aws_access_key_id     = creds["AccessKeyId"],
        aws_secret_access_key = creds["SecretAccessKey"],
        aws_session_token     = creds["SessionToken"],
        region_name           = AWS_REGION
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def print_summary():
    log.info("=" * 60)
    log.info("TAGGING SUMMARY")
    log.info("=" * 60)
    log.info("Total resources       : %d", summary["total"])
    log.info("Successfully tagged   : %d", summary["tagged"])
    log.info("No change needed      : %d", summary["no_change"])
    log.info("Skipped               : %d", summary["skipped"])
    log.info("Failed                : %d", summary["failed"])
    log.info("Mode                  : %s", "DRY-RUN" if DRY_RUN else "LIVE")
    log.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():

    # ── Parse and validate YAML config ───────────────────────────────────
    tagging = parse_tagging_config()
    validate_tagging_config(tagging)

    # ── Extract config block ──────────────────────────────────────────────
    config     = tagging.get("config", {})
    account_id = config.get("account_id", "")
    region     = config.get("region", "us-east-1")
    role_arn   = config.get(
        "target_role_arn",
        f"arn:aws:iam::{account_id}:role/xyz"
    )

    # ── Extract workspace block ───────────────────────────────────────────
    workspace       = tagging.get("workspace", {})
    workspace_name  = workspace.get("name", "").strip()
    workspace_tags  = {k: str(v) for k, v in workspace.get("tags", {}).items()}

    # ── Extract tagsets ───────────────────────────────────────────────────
    tagsets = tagging.get("tagsets", [])

    log.info("=" * 60)
    log.info("Account ID            : %s", account_id)
    log.info("Region                : %s", region)
    log.info("Role ARN              : %s", role_arn)
    log.info("Workspace             : %s", workspace_name or "Not provided")
    log.info("Workspace tags        : %s", json.dumps(workspace_tags) if workspace_tags else "None")
    log.info("Tagsets count         : %d", len(tagsets))
    log.info("Mode                  : %s", "DRY-RUN" if DRY_RUN else "LIVE")
    log.info("=" * 60)

    # ── Assume role in Account B ──────────────────────────────────────────
    session = assume_role(role_arn)

    # ── Get Account ID after assuming role ────────────────────────────────
    global ACCOUNT_ID
    ACCOUNT_ID = session.client("sts").get_caller_identity()["Account"]
    log.info("Operating in Account  : %s", ACCOUNT_ID)

    # ── boto3 clients ─────────────────────────────────────────────────────
    rg_client  = session.client("resourcegroupstaggingapi")
    iam_client = session.client("iam")
    ec2_client = session.client("ec2")

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 1 — Workspace resources + workspace_tags
    # ══════════════════════════════════════════════════════════════════════
    if workspace_name and workspace_tags:
        log.info("=" * 60)
        log.info("PHASE 1 — Workspace: %s", workspace_name)
        log.info("=" * 60)

        ws_id           = get_workspace_id(workspace_name)
        dl_url          = get_state_download_url(ws_id)
        state           = download_state(dl_url)
        state_resources = parse_state_resources(state)

        summary["total"] += len(state_resources)

        # ──────────────────────────────────────────────────────────────────
        # TEST CONDITION 1 — Limit to first N resources
        # Uncomment to test with only first 4 resources
        # ──────────────────────────────────────────────────────────────────
        # MAX_RESOURCES = 4
        # if len(state_resources) > MAX_RESOURCES:
        #     log.info("[TEST MODE] Limiting to first %d resources", MAX_RESOURCES)
        #     state_resources = state_resources[:MAX_RESOURCES]

        # ──────────────────────────────────────────────────────────────────
        # TEST CONDITION 2 — Filter to specific resource types
        # Uncomment to test with specific resource types only
        # ──────────────────────────────────────────────────────────────────
        # ALLOWED_RESOURCE_TYPES = ["aws_instance", "aws_s3_bucket"]
        # state_resources = [r for r in state_resources if r["type"] in ALLOWED_RESOURCE_TYPES]
        # log.info("[TEST MODE] Filtered to %d resources", len(state_resources))

        log.info("Workspace tags        : %s", json.dumps(workspace_tags))
        log.info("Processing %d workspace resources...", len(state_resources))
        process_resources(state_resources, workspace_tags, rg_client, iam_client, ec2_client)

    elif workspace_name and not workspace_tags:
        log.info("PHASE 1 — Workspace provided but no workspace_tags — skipping workspace phase")

    else:
        log.info("PHASE 1 — No workspace provided — skipping workspace phase")

    # ══════════════════════════════════════════════════════════════════════
    # PHASE 2 — Tagsets
    # ══════════════════════════════════════════════════════════════════════
    if tagsets:
        log.info("=" * 60)
        log.info("PHASE 2 — Processing %d tagset/s", len(tagsets))
        log.info("=" * 60)

        for tagset in tagsets:
            tagset_name    = tagset.get("name", "unnamed")
            tagset_tags    = {k: str(v) for k, v in tagset.get("tags", {}).items()}
            resources_list = tagset.get("resources_list", {})

            log.info("-" * 60)
            log.info("Tagset                : %s", tagset_name)
            log.info("Tags                  : %s", json.dumps(tagset_tags))

            if not tagset_tags:
                log.warning("[SKIP] Tagset '%s' — no tags defined", tagset_name)
                continue

            if not resources_list:
                log.warning("[SKIP] Tagset '%s' — no resources_list defined", tagset_name)
                continue

            tagset_resources = parse_tagset_resources(resources_list)
            tagset_resources = deduplicate(tagset_resources)

            if not tagset_resources:
                log.warning("[SKIP] Tagset '%s' — no valid resources found", tagset_name)
                continue

            log.info("Resources to process  : %d", len(tagset_resources))
            summary["total"] += len(tagset_resources)

            process_resources(tagset_resources, tagset_tags, rg_client, iam_client, ec2_client)

    else:
        log.info("PHASE 2 — No tagsets provided — skipping tagsets phase")

    # ── Print final summary ───────────────────────────────────────────────
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.HTTPError as e:
        log.error("TFC API HTTP Error: %s - %s", e.response.status_code, e.response.text)
        raise
    except Exception as e:
        log.error("Unexpected error: %s", str(e))
        raise