"""
create_ecs_dashboard.py

Creates/updates a Dynatrace dashboard for an ECS Fargate service using the
Platform Document API (multipart create/update with optimistic-locking version).
"""

import json
import os
import requests
import sys

# ---------------------------------------------------------------------------
# CONFIG - fill these in or set env vars
# ---------------------------------------------------------------------------
DT_BASE_URL = "https://rrr-dev-qa.apps.dynatrace.com"
DT_API_TOKEN = os.environ.get("DT_API_TOKEN")

CLUSTER_NAME = "xyz-service-d-cluster"
SERVICE_PREFIX = "xyz-service-d"          # matches ServiceName filtering in DQL
LOG_GROUP_MATCH = f"*containerinsights/{SERVICE_PREFIX}*"
DASHBOARD_NAME = f"ECSMonitoring-{SERVICE_PREFIX}"

# No Content-Type - requests sets it automatically for multipart
HEADERS = {
    "Authorization": f"Api-Token {DT_API_TOKEN}",
}


# ---------------------------------------------------------------------------
# DQL queries
# Metric tiles use: timeseries alias = agg(metric), by: {dim} | filter contains(...)
# Log tiles use:    fetch logs | parse content, "JSON:parsed" | filter ...
# ---------------------------------------------------------------------------

q_task_counts = (
    'timeseries desired = avg(ext:cloud.aws.containerinsights.desiredTaskCountByServiceName), '
    'running = avg(ext:cloud.aws.containerinsights.runningTaskCountByServiceName), '
    'pending = avg(ext:cloud.aws.containerinsights.pendingTaskCountByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

q_cpu_utilized = (
    'timeseries cpu = avg(ext:cloud.aws.containerinsights.cpuUtilizedByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

q_memory_utilized = (
    'timeseries memory = avg(ext:cloud.aws.containerinsights.memoryUtilizedByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

q_deployment_count = (
    'timeseries deployments = sum(ext:cloud.aws.containerinsights.deploymentCountByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

q_network_io = (
    'timeseries rx = avg(ext:cloud.aws.containerinsights.networkRxBytesByServiceName), '
    'tx = avg(ext:cloud.aws.containerinsights.networkTxBytesByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

q_storage_io = (
    'timeseries read = avg(ext:cloud.aws.containerinsights.storageReadBytesByServiceName), '
    'write = avg(ext:cloud.aws.containerinsights.storageWriteBytesByServiceName), '
    'by: {ServiceName} '
    f'| filter contains(lower(ServiceName), "{SERVICE_PREFIX.lower()}")'
)

# builtin:containers.* metrics are OneAgent container entities, not tagged the
# same way as Container Insights metrics -- TODO: confirm dimension/filter
# once tested live; using a name-contains filter as a starting guess.
q_cpu_throttling = (
    'timeseries throttled = avg(builtin:containers.cpu.throttledMilliCores), '
    'by: {dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
)

q_memory_usage_pct = (
    'timeseries memPct = avg(builtin:containers.memory.usagePercent), '
    'by: {dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
)

q_nonrunning_tasks = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Task"\n'
    '| filter parsed.KnownStatus != "RUNNING"\n'
    "| summarize count(), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
)

q_unhealthy_containers = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    '| filter parsed.ContainerHealthStatus != "HEALTHY"\n'
    "| summarize count(), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
)

q_recent_task_events = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Task"\n'
    '| fields timestamp, taskId = parsed.TaskId, status = parsed.KnownStatus, '
    'az = parsed.AvailabilityZone\n'
    "| sort timestamp desc\n"
    "| limit 50"
)


# ---------------------------------------------------------------------------
# Tile builder helper
# ---------------------------------------------------------------------------

def tile(tile_id, title, query, tile_type="data", col=0, row=0, w=6, h=4):
    return {
        "id": tile_id,
        "type": tile_type,
        "title": title,
        "query": query,
        "layout": {"x": col, "y": row, "w": w, "h": h},
        "querySettings": {
            "maxResultRecords": 1000,
            "defaultTimeframeForLocalQueries": "now-2h",
        },
    }


# ---------------------------------------------------------------------------
# Layout
# Row 1 - Task counts | CPU utilized
# Row 2 - Memory utilized | Deployment count
# Row 3 - CPU throttling | Memory usage %
# Row 4 - Network I/O | Storage I/O
# Row 5 - Non-running tasks | Unhealthy containers
# Row 6 - Recent task events (full width)
# ---------------------------------------------------------------------------

tiles = [
    tile("tile-task-counts",          "Task Counts (Desired/Running/Pending)", q_task_counts,          "data", col=0, row=0,  w=6, h=4),
    tile("tile-cpu-utilized",         "CPU Utilized",                          q_cpu_utilized,          "data", col=6, row=0,  w=6, h=4),
    tile("tile-memory-utilized",      "Memory Utilized",                       q_memory_utilized,       "data", col=0, row=4,  w=6, h=4),
    tile("tile-deployment-count",     "Deployment Count",                      q_deployment_count,      "data", col=6, row=4,  w=6, h=4),
    tile("tile-cpu-throttling",       "CPU Throttling (Container)",            q_cpu_throttling,        "data", col=0, row=8,  w=6, h=4),
    tile("tile-memory-pct",           "Memory Usage % (Container)",            q_memory_usage_pct,      "data", col=6, row=8,  w=6, h=4),
    tile("tile-network-io",           "Network Rx/Tx Bytes",                   q_network_io,            "data", col=0, row=12, w=6, h=4),
    tile("tile-storage-io",           "Storage Read/Write Bytes",              q_storage_io,            "data", col=6, row=12, w=6, h=4),
    tile("tile-nonrunning-tasks",     "Non-Running Task Events",               q_nonrunning_tasks,      "data", col=0, row=16, w=6, h=4),
    tile("tile-unhealthy-containers", "Unhealthy Container Events",            q_unhealthy_containers,  "data", col=6, row=16, w=6, h=4),
    tile("tile-recent-task-events",   "Recent Task Events",                    q_recent_task_events,    "data", col=0, row=20, w=12, h=6),
]


# ---------------------------------------------------------------------------
# Assemble dashboard content + payload
# ---------------------------------------------------------------------------

def build_dashboard_payload(name: str) -> dict:
    dashboard_content = {
        "version": "10",
        "variables": [],
        "tiles": {
            t["id"]: {k: v for k, v in t.items() if k != "layout"}
            for t in tiles
        },
        "layouts": {
            "lg": {
                t["id"]: {
                    "x": t["layout"]["x"],
                    "y": t["layout"]["y"],
                    "w": t["layout"]["w"],
                    "h": t["layout"]["h"],
                }
                for t in tiles
            }
        },
    }
    return {
        "name": name,
        "type": "dashboard",
        "isPrivate": False,
        "content": json.dumps(dashboard_content),
    }


def get_existing_dashboard_id(name: str):
    """
    Search the Document API for an existing dashboard with this name.
    NOTE: filter syntax / response shape below is a best-guess reconstruction --
    confirm against your working get_existing_dashboard_id() implementation
    and swap in directly if different.
    """
    url = f"{DT_BASE_URL}/platform/document/v1/documents"
    params = {"filter": f'type=="dashboard" and name=="{name}"'}
    resp = requests.get(url, headers=HEADERS, params=params)
    if resp.status_code != 200:
        print(f"⚠ Could not check for existing dashboard: {resp.status_code} {resp.text}")
        return None, None
    data = resp.json()
    documents = data.get("documents", [])
    if not documents:
        return None, None
    doc = documents[0]
    return doc.get("id"), doc.get("version")


def create_or_update_dashboard():
    payload = build_dashboard_payload(DASHBOARD_NAME)

    # 1. Check if the dashboard already exists
    doc_id, version = get_existing_dashboard_id(DASHBOARD_NAME)

    # 2. Build the multipart request fields
    multipart = {
        "name": (None, payload["name"]),
        "type": (None, payload["type"]),
        "isPrivate": (None, str(payload["isPrivate"]).lower()),
        "content": ("content", payload["content"], "application/json"),
    }

    if doc_id:
        # UPDATE workflow (PUT) - Next-Gen API uses optimistic locking.
        # You must provide the current version to update content.
        print(f"📝 Updating existing dashboard: {DASHBOARD_NAME} (ID: {doc_id})")
        url = f"{DT_BASE_URL}/platform/document/v1/documents/{doc_id}"
        multipart["version"] = (None, str(version))
        response = requests.put(url, headers=HEADERS, files=multipart)
        action = "updated"
    else:
        # CREATE workflow (POST)
        print(f"➕ Creating new dashboard: {DASHBOARD_NAME}")
        url = f"{DT_BASE_URL}/platform/document/v1/documents"
        response = requests.post(url, headers=HEADERS, files=multipart)
        action = "created"

    # 3. Handle the response
    if response.status_code in (200, 201):
        data = response.json()
        final_id = data.get("id", doc_id if doc_id else "unknown")
        print(f"✅ Dashboard {action}: {DASHBOARD_NAME} (ID: {final_id})")
    else:
        print(f"❌ Failed to {action[:-1]} dashboard: {response.status_code}")
        print(response.text)
        sys.exit(1)


if __name__ == "__main__":
    if not DT_API_TOKEN:
        print("❌ DT_API_TOKEN environment variable not set")
        sys.exit(1)
    create_or_update_dashboard()