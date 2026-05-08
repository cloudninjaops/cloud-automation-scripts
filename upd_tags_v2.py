Here you go:

```python
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
TFC_TOKEN      = os.environ.get("TFC_TOKEN", "")
TFC_ORG        = os.environ.get("TFC_ORG", "")
WORKSPACE_NAME = os.environ.get("WORKSPACE_NAME", "").strip()
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")
DRY_RUN        = os.environ.get("DRY_RUN", "true").lower() == "true"

ACCOUNT_B_ROLE_ARN = os.environ.get("ACCOUNT_B_ROLE_ARN", "")

# ── Dynamic tags from YAML via TAGS env var ───────────────────────────────────
try:
    raw_tags = os.environ.get("TAGS", "{}").strip()
    NEW_TAGS = json.loads(raw_tags)
    if not NEW_TAGS:
        log.error("TAGS env var is empty — no tags to apply. Exiting.")
        exit(1)
except json.JSONDecodeError as e:
    log.error("Failed to parse TAGS env var: %s", e)
    exit(1)

# ── Resources list from YAML via RESOURCES_LIST env var ──────────────────────
RESOURCES_LIST_RAW = os.environ.get("RESOURCES_LIST", "").strip()

# ── TFC API Headers ───────────────────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {TFC_TOKEN}",
    "Content-Type":  "application/vnd.api+json"
}
BASE_URL = "https://app.terraform.io/api/v2"

# ── Global ACCOUNT_ID — set after assume_role ─────────────────────────────────
ACCOUNT_ID = ""

# ── Resource types that are NOT taggable ──────────────────────────────────────
SKIP_RESOURCE_TYPES = {
    "aws_cloudwatch_event_bus_policy",
    "aws_cloudwatch_log_resource_policy",
    "aws_cloudwatch_event_target",
    "aws_iam_instance_profile",
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
# SECTION 1 — VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_inputs():
    """
    Validate that at least one of WORKSPACE_NAME or RESOURCES_LIST is provided.
    If both are missing — print clear message and exit.
    """
    has_workspace      = bool(WORKSPACE_NAME)
    has_resources_list = False

    # Check if RESOURCES_LIST has any actual resources
    if RESOURCES_LIST_RAW:
        try:
            cleaned = re.sub(r'\s+', ' ', RESOURCES_LIST_RAW).strip().strip("'").strip('"')
            data    = json.loads(cleaned)
            has_resources_list = any([
                data.get("arns"),
                data.get("instance_ids"),
                data.get("s3_buckets"),
                data.get("iam_arns"),
            ])
        except json.JSONDecodeError:
            pass

    if not has_workspace and not has_resources_list:
        log.error("=" * 60)
        log.error("MISSING INPUT — cannot proceed.")
        log.error("Please provide at least one of the following:")
        log.error("  1. WORKSPACE_NAME — to tag resources from TFC state file")
        log.error("  2. RESOURCES_LIST — to tag additional resources from YAML")
        log.error("  OR both can be provided together.")
        log.error("=" * 60)
        exit(1)

    if has_workspace:
        log.info("Workspace provided    : %s", WORKSPACE_NAME)
    else:
        log.info("Workspace provided    : None — skipping state file")

    if has_resources_list:
        log.info("Resources list        : provided via YAML")
    else:
        log.info("Resources list        : not provided or empty")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TFC STATE FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def get_workspace_id():
    url = f"{BASE_URL}/organizations/{TFC_ORG}/workspaces/{WORKSPACE_NAME}"
    log.info("Fetching workspace ID for: %s", WORKSPACE_NAME)
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


def parse_resources(state):
    """
    Parse state file and return list of managed resources.
    Skips data sources — only managed resources included.
    """
    resources = state.get("resources", [])
    managed   = [r for r in resources if r.get("mode") == "managed"]
    parsed    = []

    for res in managed:
        rtype  = res.get("type", "")
        rname  = res.get("name", "")
        module = res.get("module", "root")

        for instance in res.get("instances", []):
            attrs = instance.get("attributes", {})

            # Construct EC2 ARN if missing
            res_id = attrs.get("id")
            arn    = attrs.get("arn")
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
# SECTION 3 — EXTRA RESOURCES FROM YAML
# ══════════════════════════════════════════════════════════════════════════════

def parse_extra_resources():
    """
    Reads RESOURCES_LIST env var — JSON encoded by Terraform from YAML.
    Handles missing keys, null values, empty lists gracefully.
    """
    extra = []

    if not RESOURCES_LIST_RAW:
        log.info("RESOURCES_LIST not set or empty — skipping extra resources")
        return extra

    try:
        cleaned = re.sub(r'\s+', ' ', RESOURCES_LIST_RAW).strip()
        cleaned = cleaned.strip("'").strip('"')
        data    = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.error("Failed to parse RESOURCES_LIST JSON: %s", e)
        return extra

    # ── Safe list getter — handles null, missing, non-list ────────────────
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

    # ── EC2 family IDs — construct ARN ────────────────────────────────────
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

    log.info("Extra resources       : %d", len(extra))
    return extra


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate(resources):
    """
    Remove duplicates based on ARN if available,
    otherwise fall back to type + id combination.
    """
    seen   = set()
    unique = []

    for res in resources:
        key = res.get("arn") or f"{res['type']}:{res.get('id')}"
        if key and key not in seen:
            seen.add(key)
            unique.append(res)
        elif not key:
            unique.append(res)

    log.info("After deduplication   : %d", len(unique))
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
        response      = rg_client.get_resources(ResourceARNList=[arn], ResourcesPerPage=1)
        resource_list = response.get("ResourceTagMappingList", [])
        if not resource_list:
            return {}
        return {t["Key"]: t["Value"] for t in resource_list[0].get("Tags", [])}
    except ClientError as e:
        log.warning("Could not read tags for %s: %s", arn, e)
        return {}


def apply_tags_rg(rg_client, arn, tags_to_apply):
    try:
        response = rg_client.tag_resources(ResourceARNList=[arn], Tags=tags_to_apply)
        failed   = response.get("FailedResourcesMap", {})
        if failed:
            log.error("Tagging failed for %s: %s", arn, failed)
            return False
        return True
    except ClientError as e:
        log.error("Error tagging %s: %s", arn, e)
        return False


def process_resource_rg(rg_client, resource):
    arn   = resource.get("arn")
    rtype = resource["type"]
    rname = resource["name"]
    label = f"{rtype}/{rname}"

    if not arn or arn == "N/A":
        log.warning("[SKIP] %s — no ARN available", label)
        summary["skipped"] += 1
        return

    existing_tags = get_existing_tags_rg(rg_client, arn)
    changes       = compute_tag_changes(existing_tags, NEW_TAGS)

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

def process_iam_resource(iam_client, resource):
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
            changes       = compute_tag_changes(existing_tags, NEW_TAGS)

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
            changes       = compute_tag_changes(existing_tags, NEW_TAGS)

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

def process_ec2_id(ec2_client, resource):
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

    changes = compute_tag_changes(existing_tags, NEW_TAGS)

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
# SECTION 9 — ASSUME ROLE
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
# SECTION 10 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(all_resources):
    log.info("=" * 60)
    log.info("TAGGING SUMMARY")
    log.info("=" * 60)
    log.info("Total resources       : %d", summary["total"])
    log.info("Successfully tagged   : %d", summary["tagged"])
    log.info("No change needed      : %d", summary["no_change"])
    log.info("Skipped               : %d", summary["skipped"])
    log.info("Failed                : %d", summary["failed"])
    log.info("Mode                  : %s", "DRY-RUN" if DRY_RUN else "LIVE")
    log.info("Tags applied          : %s", json.dumps(NEW_TAGS))
    log.info("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():

    # ── Validate inputs ───────────────────────────────────────────────────
    validate_inputs()

    # ── Assume role in Account B ──────────────────────────────────────────
    session = assume_role(ACCOUNT_B_ROLE_ARN)

    # ── Get Account ID after assuming role ────────────────────────────────
    global ACCOUNT_ID
    ACCOUNT_ID = session.client("sts").get_caller_identity()["Account"]
    log.info("Operating in Account  : %s", ACCOUNT_ID)
    log.info("Region                : %s", AWS_REGION)
    log.info("Tags to apply         : %s", json.dumps(NEW_TAGS))

    # ── boto3 clients — all using Account B session ───────────────────────
    rg_client  = session.client("resourcegroupstaggingapi")
    iam_client = session.client("iam")
    ec2_client = session.client("ec2")

    # ── Fetch state resources from TFC (if workspace provided) ───────────
    state_resources = []
    if WORKSPACE_NAME:
        ws_id           = get_workspace_id()
        dl_url          = get_state_download_url(ws_id)
        state           = download_state(dl_url)
        state_resources = parse_resources(state)

    # ── Extra resources from YAML ─────────────────────────────────────────
    extra_resources = parse_extra_resources()

    # ── Merge + deduplicate ───────────────────────────────────────────────
    all_resources = deduplicate(state_resources + extra_resources)

    log.info("State file resources  : %d", len(state_resources))
    log.info("Extra resources       : %d", len(extra_resources))
    log.info("Total after dedup     : %d", len(all_resources))

    summary["total"] = len(all_resources)

    if DRY_RUN:
        log.info("*** DRY-RUN MODE — no changes will be applied ***")

    log.info("=" * 60)
    log.info("Processing %d resources...", len(all_resources))
    log.info("=" * 60)

    # ──────────────────────────────────────────────────────────────────────
    # TEST CONDITION 1 — Limit to first N resources
    # Uncomment to process only first 4 resources during testing
    # ──────────────────────────────────────────────────────────────────────
    # MAX_RESOURCES = 4
    # if len(all_resources) > MAX_RESOURCES:
    #     log.info("[TEST MODE] Limiting to first %d resources", MAX_RESOURCES)
    #     all_resources = all_resources[:MAX_RESOURCES]

    # ──────────────────────────────────────────────────────────────────────
    # TEST CONDITION 2 — Filter to specific resource types
    # Uncomment to process only specific resource types during testing
    # ──────────────────────────────────────────────────────────────────────
    # ALLOWED_RESOURCE_TYPES = ["aws_instance", "aws_s3_bucket"]
    # all_resources = [r for r in all_resources if r["type"] in ALLOWED_RESOURCE_TYPES]
    # log.info("[TEST MODE] Filtered to %d resources", len(all_resources))

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

    # ── Print summary ─────────────────────────────────────────────────────
    print_summary(all_resources)


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.HTTPError as e:
        log.error("TFC API HTTP Error: %s - %s", e.response.status_code, e.response.text)
        raise
    except Exception as e:
        log.error("Unexpected error: %s", str(e))
        raise
```