import requests
import json
import sys

# -------------------------------
# 🛠️ Configurable Inputs
# -------------------------------
TFC_TOKEN = "your-api-token-here"
ORG_NAME = "your-org-name"
SOURCE_WORKSPACE_NAME = "source-workspace"
TARGET_WORKSPACE_NAME = "target-workspace"
TFC_API = "https://app.terraform.io/api/v2"
HEADERS = {
    "Authorization": f"Bearer {TFC_TOKEN}",
    "Content-Type": "application/vnd.api+json"
}

# -------------------------------
# 🔍 Helper Functions
# -------------------------------
def get_workspace_id(workspace_name):
    url = f"{TFC_API}/organizations/{ORG_NAME}/workspaces/{workspace_name}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json()["data"]["id"]
    else:
        print(f"❌ Failed to get workspace ID for {workspace_name}: {resp.text}")
        sys.exit(1)

def get_workspace_vars(workspace_id):
    url = f"{TFC_API}/workspaces/{workspace_id}/vars"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json()["data"]
    else:
        print(f"❌ Failed to get variables: {resp.text}")
        sys.exit(1)

def create_workspace(workspace_name):
    url = f"{TFC_API}/organizations/{ORG_NAME}/workspaces"
    payload = {
        "data": {
            "attributes": {
                "name": workspace_name,
                "terraform-version": "1.6.6",
                "auto-apply": False
            },
            "type": "workspaces"
        }
    }
    resp = requests.post(url, headers=HEADERS, data=json.dumps(payload))
    if resp.status_code == 201:
        return resp.json()["data"]["id"]
    else:
        print(f"❌ Failed to create workspace {workspace_name}: {resp.text}")
        sys.exit(1)

def copy_variable(var, target_workspace_id):
    payload = {
        "data": {
            "type": "vars",
            "attributes": {
                "key": var["attributes"]["key"],
                "value": var["attributes"]["value"],
                "category": var["attributes"]["category"],
                "hcl": var["attributes"]["hcl"],
                "sensitive": var["attributes"]["sensitive"]
            },
            "relationships": {
                "workspace": {
                    "data": {
                        "id": target_workspace_id,
                        "type": "workspaces"
                    }
                }
            }
        }
    }
    url = f"{TFC_API}/vars"
    resp = requests.post(url, headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 201:
        print(f"⚠️ Failed to copy variable {var['attributes']['key']}: {resp.text}")

def get_variable_sets_attached_to_workspace(workspace_id):
    url = f"{TFC_API}/workspaces/{workspace_id}/relationships/variable-sets"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return [vs["id"] for vs in resp.json()["data"]]
    else:
        print(f"⚠️ Failed to list variable sets for workspace {workspace_id}: {resp.text}")
        return []

def attach_variable_set_to_workspace(varset_id, workspace_id):
    url = f"{TFC_API}/variable-sets/{varset_id}/relationships/workspaces"
    payload = {
        "data": [
            {
                "type": "workspaces",
                "id": workspace_id
            }
        ]
    }
    resp = requests.post(url, headers=HEADERS, data=json.dumps(payload))
    if resp.status_code != 200:
        print(f"⚠️ Failed to attach varset {varset_id} to workspace {workspace_id}: {resp.text}")
    else:
        print(f"✅ Attached varset {varset_id} to workspace {workspace_id}")

# -------------------------------
# 🚀 Main Execution
# -------------------------------
print("🔍 Fetching source workspace ID...")
source_ws_id = get_workspace_id(SOURCE_WORKSPACE_NAME)

print("📋 Fetching variables from source workspace...")
vars_to_copy = get_workspace_vars(source_ws_id)

print("🛠️ Creating new workspace...")
target_ws_id = create_workspace(TARGET_WORKSPACE_NAME)

print("📦 Copying workspace variables...")
for var in vars_to_copy:
    copy_variable(var, target_ws_id)

print("🔗 Fetching variable sets attached to source workspace...")
varset_ids = get_variable_sets_attached_to_workspace(source_ws_id)

print("🔁 Attaching same variable sets to new workspace...")
for vs_id in varset_ids:
    attach_variable_set_to_workspace(vs_id, target_ws_id)
print(f"\n✅ Finished! Workspace '{TARGET_WORKSPACE_NAME}' created and configured.\n")