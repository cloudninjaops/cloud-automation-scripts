import os
import json
import requests

TFC_Tkn      = os.environ["TFC_Tk"]
TFC_ORG        = os.environ["TFC_ORG"]
WORKSPACE_NAME = os.environ["WORKSPACE_NAME"]

HEADERS = {
    "Authorization": f"Bearer {TFC_Tkn}",
    "Content-Type": "application/vnd.api+json"
}
BASE_URL = "https://app.terraform.io/api/v2"


# ── 1. Get Workspace ID ───────────────────────────────────────────────────────
def get_workspace_id():
    url = f"{BASE_URL}/organizations/{TFC_ORG}/workspaces/{WORKSPACE_NAME}"
    print(f"\n[INFO] Fetching workspace ID for: {WORKSPACE_NAME}")
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    ws_id = r.json()["data"]["id"]
    print(f"[INFO] Workspace ID: {ws_id}")
    return ws_id


# ── 2. Get Latest State File Download URL ─────────────────────────────────────
def get_state_download_url(workspace_id):
    url = f"{BASE_URL}/workspaces/{workspace_id}/current-state-version"
    print(f"\n[INFO] Fetching latest state version...")
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()

    data       = r.json()["data"]
    serial     = data["attributes"]["serial"]
    created_at = data["attributes"]["created-at"]
    dl_url     = data["attributes"]["hosted-state-download-url"]

    print(f"[INFO] State Serial  : {serial}")
    print(f"[INFO] State Created : {created_at}")
    return dl_url


# ── 3. Download State File ────────────────────────────────────────────────────
def download_state(download_url):
    print(f"\n[INFO] Downloading state file...")
    r = requests.get(download_url, headers=HEADERS)
    r.raise_for_status()
    return r.json()


# ── 4. Parse and Print Resources ──────────────────────────────────────────────
def parse_and_print_resources(state):
    resources = state.get("resources", [])

    # Filter out data sources — only managed resources
    managed = [r for r in resources if r.get("mode") == "managed"]

    print(f"\n{'='*60}")
    print(f"  TOTAL MANAGED RESOURCES FOUND: {len(managed)}")
    print(f"{'='*60}")

    # Group by resource type for clean output
    by_type = {}
    for res in managed:
        rtype = res["type"]
        if rtype not in by_type:
            by_type[rtype] = []
        by_type[rtype].append(res)

    for rtype, items in sorted(by_type.items()):
        print(f"\n[TYPE] {rtype}  ({len(items)} instance/s)")
        print(f"  {'-'*50}")

        for res in items:
            name   = res.get("name", "N/A")
            module = res.get("module", "root")

            for idx, instance in enumerate(res.get("instances", [])):
                attrs  = instance.get("attributes", {})

                # Try common ID fields in order of preference
                res_id  = attrs.get("id", "N/A")
                arn     = attrs.get("arn", "N/A")
                tags    = attrs.get("tags", {})

                print(f"\n  Resource Name : {name}" + (f"[{idx}]" if idx > 0 else ""))
                print(f"  Module        : {module}")
                print(f"  ID            : {res_id}")
                print(f"  ARN           : {arn}")
                print(f"  Existing Tags : {json.dumps(tags, indent=4) if tags else 'None'}")

    print(f"\n{'='*60}")
    print(f"  SUMMARY BY TYPE")
    print(f"{'='*60}")
    for rtype, items in sorted(by_type.items()):
        total_instances = sum(len(r.get("instances", [])) for r in items)
        print(f"  {rtype:<45} {total_instances} instance/s")

    print(f"{'='*60}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ws_id    = get_workspace_id()
        dl_url   = get_state_download_url(ws_id)
        state    = download_state(dl_url)
        parse_and_print_resources(state)

    except requests.exceptions.HTTPError as e:
        print(f"\n[ERROR] HTTP Error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        raise
```

# ---

# ## What the Output Looks Like
# ```
# ============================================================
#   TOTAL MANAGED RESOURCES FOUND: 12
# ============================================================

# [TYPE] aws_instance  (2 instance/s)
#   --------------------------------------------------
#   Resource Name : web_server
#   Module        : root
#   ID            : i-0abc123456789
#   ARN           : N/A
#   Existing Tags : {"Name": "web-server", "Env": "prod"}

# [TYPE] aws_s3_bucket  (1 instance/s)
#   --------------------------------------------------
#   Resource Name : app_bucket
#   Module        : root
#   ID            : my-app-bucket-prod
#   ARN           : arn:aws:s3:::my-app-bucket-prod
#   Existing Tags : {"Name": "app-bucket"}

# ============================================================
#   SUMMARY BY TYPE
# ============================================================
#   aws_instance                                  2 instance/s
#   aws_s3_bucket                                 1 instance/s
# ============================================================
# ```

# ---

# ## Folder Structure
# ```
# workspace-x/
# ├── main.tf
# ├── variables.tf
# └── scripts/
#     └── list_resources.py