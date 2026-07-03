"""
create_ecs_dashboard.py

Creates/updates a Dynatrace dashboard for an ECS Fargate service using the
Platform Document API (multipart create/update with optimistic-locking version).

NOTE ON DATA SOURCE:
ext:cloud.aws.containerinsights.* metrics were confirmed EMPTY in this
environment (Data Explorer showed "No records" across all services/timeframes),
so this version pulls task counts / CPU from the Container Insights LOG records
instead, using the same parse-JSON pattern already validated against real data.
builtin:containers.* metric queries are kept but still UNTESTED - validate in
Data Explorer before trusting them.
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
SERVICE_PREFIX = "xyz-service-d"
LOG_GROUP_MATCH = f"*containerinsights/{SERVICE_PREFIX}*"
DASHBOARD_NAME = f"ECSMonitoring-{SERVICE_PREFIX}"

HEADERS = {
    "Authorization": f"Api-Token {DT_API_TOKEN}",
}


# ---------------------------------------------------------------------------
# DQL queries - LOG-BASED (confirmed data source)
# Pattern: fetch logs | filter log_group | parse content, "JSON:parsed" | ...
# ---------------------------------------------------------------------------

q_task_counts = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Service"\n'
    "| fields timestamp,\n"
    "    desired = toLong(parsed.DesiredTaskCount),\n"
    "    running = toLong(parsed.RunningTaskCount),\n"
    "    pending = toLong(parsed.PendingTaskCount)\n"
    "| summarize avg(desired), avg(running), avg(pending), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
)

q_deployment_count = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Service"\n'
    "| fields timestamp, deployments = toLong(parsed.DeploymentCount)\n"
    "| summarize avg(deployments), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
)

q_cpu_utilized = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    "| fields timestamp, cpu = toDouble(parsed.CpuUtilized)\n"
    "| summarize avg(cpu), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
)

# TODO: "MemoryUtilized" field name on Container-type log records is a GUESS --
# we only confirmed "CpuUtilized" exists in a sample record. Verify the actual
# field name/casing in a log record before trusting this tile.
q_memory_utilized = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    "| fields timestamp, memory = toDouble(parsed.MemoryUtilized)\n"
    "| summarize avg(memory), by: {bin(timestamp, 5m)}\n"
    "| sort timestamp asc"
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
# DQL queries - builtin:containers.* metrics (OneAgent) - STILL UNTESTED.
# Validate each in Data Explorer before relying on these tiles. Metric keys
# with colons must be backtick-quoted in DQL.
# ---------------------------------------------------------------------------

q_cpu_throttling = (
    'timeseries throttled = avg(`builtin:containers.cpu.throttledMilliCores`), '
    'by: {dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
)

q_memory_usage_pct = (
    'timeseries memPct = avg(`builtin:containers.memory.usagePercent`), '
    'by: {dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
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
# Row 1 - Task counts (log)          | Deployment count (log)
# Row 2 - CPU utilized (log)         | Memory utilized (log, field name TODO)
# Row 3 - CPU throttling (metric, untested) | Memory usage % (metric, untested)
# Row 4 - Non-running tasks (log)    | Unhealthy containers (log)
# Row 5 - Recent task events (full width, log)
# ---------------------------------------------------------------------------

tiles = [
    tile("tile-task-counts",          "Task Counts (Desired/Running/Pending)", q_task_counts,          "data", col=0, row=0,  w=6, h=4),
    tile("tile-deployment-count",     "Deployment Count",                      q_deployment_count,      "data", col=6, row=0,  w=6, h=4),
    tile("tile-cpu-utilized",         "CPU Utilized",                          q_cpu_utilized,          "data", col=0, row=4,  w=6, h=4),
    tile("tile-memory-utilized",      "Memory Utilized",                       q_memory_utilized,       "data", col=6, row=4,  w=6, h=4),
    tile("tile-cpu-throttling",       "CPU Throttling (Container, untested)",  q_cpu_throttling,        "data", col=0, row=8,  w=6, h=4),
    tile("tile-memory-pct",           "Memory Usage % (Container, untested)",  q_memory_usage_pct,      "data", col=6, row=8,  w=6, h=4),
    tile("tile-nonrunning-tasks",     "Non-Running Task Events",               q_nonrunning_tasks,      "data", col=0, row=12, w=6, h=4),
    tile("tile-unhealthy-containers", "Unhealthy Container Events",            q_unhealthy_containers,  "data", col=6, row=12, w=6, h=4),
    tile("tile-recent-task-events",   "Recent Task Events",                    q_recent_task_events,    "data", col=0, row=16, w=12, h=6),
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
        print(f"📝 Updating existing dashboard: {DASHBOARD_NAME} (ID: {doc_id})")
        url = f"{DT_BASE_URL}/platform/document/v1/documents/{doc_id}"
        multipart["version"] = (None, str(version))
        response = requests.put(url, headers=HEADERS, files=multipart)
        action = "updated"
    else:
        print(f"➕ Creating new dashboard: {DASHBOARD_NAME}")
        url = f"{DT_BASE_URL}/platform/document/v1/documents"
        response = requests.post(url, headers=HEADERS, files=multipart)
        action = "created"

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