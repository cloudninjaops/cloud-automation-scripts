"""
create_ecs_dashboard.py

Creates/updates a Dynatrace dashboard covering:
  - ECS Fargate task/container health (LOG-based - confirmed working)
  - builtin:containers.* metrics (OneAgent - UNTESTED)
  - Service response time / failure rate (builtin:service.* - UNTESTED)
  - ALB health (builtin:cloud.aws.alb.* - UNTESTED)
  - A deep-link tile to the full Service health view

Uses the Platform Document API (multipart create/update, optimistic locking).

*** IMPORTANT ***
Everything marked "UNTESTED" below was found live in Data Explorer (metric
exists, "last written" was today) but the exact DQL filter/dimension syntax
has NOT been validated against real query output. Test each in the query
editor before trusting the tile. The ECS log-based queries ARE confirmed
working end-to-end.
"""

import json
import os
import requests
import sys

# ---------------------------------------------------------------------------
# CONFIG - fill these in or set env vars. Everything else derives from here.
# ---------------------------------------------------------------------------

DT_BASE_URL = "https://rrr-dev-qa.apps.dynatrace.com"
DT_API_TOKEN = os.environ.get("DT_API_TOKEN")

CLUSTER_NAME = "xyz-service-d-cluster"
SERVICE_PREFIX = "xyz-service-d"
LOG_GROUP_MATCH = f"*containerinsights/{SERVICE_PREFIX}*"
DASHBOARD_NAME = f"ECSMonitoring-{SERVICE_PREFIX}"

# Name fragment used to filter the Service entity in DQL (matches how the
# service shows up in Applications & Microservices, e.g. "xyz-service (/pcomm)")
SERVICE_NAME_FILTER = "xyz-service"

# ALB name fragment for filtering, if you know it - leave blank to skip filtering
ALB_NAME_FILTER = "xyz-service-d-alb"

# Deep link to the full Service health page in Dynatrace.
# TODO: replace SERVICE-XXXXXXXXXXXXXXXX with the real entity ID - grab it
# from the browser URL bar when viewing the service's detail page.
SERVICE_ENTITY_ID = "SERVICE-XXXXXXXXXXXXXXXX"
SERVICE_HEALTH_URL = (
    f"{DT_BASE_URL}/ui/apps/dynatrace.classic.services/ui/services/{SERVICE_ENTITY_ID}"
)

HEADERS = {
    "Authorization": f"Api-Token {DT_API_TOKEN}",
}


# ---------------------------------------------------------------------------
# DQL queries - LOG-BASED, CONFIRMED WORKING (ECS Container Insights logs)
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
    "| summarize avg(desired), avg(running), avg(pending), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
)

q_deployment_count = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Service"\n'
    "| fields timestamp, deployments = toLong(parsed.DeploymentCount)\n"
    "| summarize avg(deployments), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
)

q_cpu_utilized = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    "| fields timestamp, cpu = toDouble(parsed.CpuUtilized)\n"
    "| summarize avg(cpu), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
)

# TODO: "MemoryUtilized" field name is a GUESS - only "CpuUtilized" was
# confirmed present in a sample Container-type log record. Verify before trust.
q_memory_utilized = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    "| fields timestamp, memory = toDouble(parsed.MemoryUtilized)\n"
    "| summarize avg(memory), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
)

q_nonrunning_tasks = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Task"\n'
    '| filter parsed.KnownStatus != "RUNNING"\n'
    "| summarize count(), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
)

q_unhealthy_containers = (
    "fetch logs\n"
    f'| filter matchesValue(aws.log_group, "{LOG_GROUP_MATCH}")\n'
    '| parse content, "JSON:parsed"\n'
    '| filter parsed.Type == "Container"\n'
    '| filter parsed.ContainerHealthStatus != "HEALTHY"\n'
    "| summarize count(), by: {interval = bin(timestamp, 5m)}\n"
    "| sort interval asc"
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
# DQL queries - builtin:containers.* (OneAgent) - UNTESTED
# ---------------------------------------------------------------------------

q_cpu_throttling = (
    'timeseries throttled = avg(`builtin:containers.cpu.throttledMilliCores`), '
    'by: {container = dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
)

q_memory_usage_pct = (
    'timeseries memPct = avg(`builtin:containers.memory.usagePercent`), '
    'by: {container = dt.entity.container_group_instance} '
    f'| filter contains(lower(dt.entity.container_group_instance.name), "{SERVICE_PREFIX.lower()}")'
)


# ---------------------------------------------------------------------------
# DQL queries - builtin:service.* - UNTESTED
# Found live in Data Explorer with today's "last written" timestamp, but
# filter/dimension syntax below has not been run against real output.
# ---------------------------------------------------------------------------

q_service_response_time = (
    'timeseries respTime = avg(`builtin:service.response.time`), '
    'by: {svc = dt.entity.service} '
    f'| filter contains(lower(entityName(svc)), "{SERVICE_NAME_FILTER.lower()}")'
)

q_service_failure_rate = (
    'timeseries clientErr = avg(`builtin:service.errors.client.rate`), '
    'by: {svc = dt.entity.service} '
    f'| filter contains(lower(entityName(svc)), "{SERVICE_NAME_FILTER.lower()}")'
)

q_service_5xx_rate = (
    'timeseries http5xx = avg(`builtin:service.errors.server.rate`), '
    'by: {svc = dt.entity.service} '
    f'| filter contains(lower(entityName(svc)), "{SERVICE_NAME_FILTER.lower()}")'
)


# ---------------------------------------------------------------------------
# DQL queries - builtin:cloud.aws.alb.* - UNTESTED
# ---------------------------------------------------------------------------

q_alb_target_response_time = (
    'timeseries respTime = avg(`builtin:cloud.aws.alb.targetresponsetime`), '
    'by: {alb = dt.entity.aws_application_load_balancer} '
    f'| filter contains(lower(entityName(alb)), "{ALB_NAME_FILTER.lower()}")'
)

q_alb_requests = (
    'timeseries requests = sum(`builtin:cloud.aws.alb.requests`), '
    'by: {alb = dt.entity.aws_application_load_balancer} '
    f'| filter contains(lower(entityName(alb)), "{ALB_NAME_FILTER.lower()}")'
)

q_alb_target_connection_errors = (
    'timeseries connErrors = sum(`builtin:cloud.aws.alb.targetconnectionerrors`), '
    'by: {alb = dt.entity.aws_application_load_balancer} '
    f'| filter contains(lower(entityName(alb)), "{ALB_NAME_FILTER.lower()}")'
)


# ---------------------------------------------------------------------------
# Tile builder helpers
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


def markdown_tile(tile_id, content, col=0, row=0, w=12, h=1):
    return {
        "id": tile_id,
        "type": "markdown",
        "title": "",
        "content": content,
        "layout": {"x": col, "y": row, "w": w, "h": h},
    }


# ---------------------------------------------------------------------------
# Layout
# Row 0  - Deep link to full Service health view
# Row 1  - Service response time | Service failure rate (client)
# Row 2  - Service 5xx rate      | ALB target response time
# Row 3  - ALB requests          | ALB target connection errors
# Row 4  - Task counts (log)     | Deployment count (log)
# Row 5  - CPU utilized (log)    | Memory utilized (log, field name TODO)
# Row 6  - CPU throttling (metric, untested) | Memory usage % (metric, untested)
# Row 7  - Non-running tasks (log) | Unhealthy containers (log)
# Row 8  - Recent task events (full width, log)
# ---------------------------------------------------------------------------

tiles = [
    markdown_tile(
        "tile-service-health-link",
        f"### 🔗 [Open Full Service Health View]({SERVICE_HEALTH_URL})",
        col=0, row=0, w=12, h=1,
    ),
    tile("tile-service-resp-time",     "Service Response Time",              q_service_response_time,       "data", col=0, row=1,  w=6, h=4),
    tile("tile-service-failure-rate",  "Service Failure Rate (Client)",      q_service_failure_rate,        "data", col=6, row=1,  w=6, h=4),
    tile("tile-service-5xx-rate",      "Service Failure Rate (5xx)",         q_service_5xx_rate,            "data", col=0, row=5,  w=6, h=4),
    tile("tile-alb-target-resp-time",  "ALB Target Response Time",           q_alb_target_response_time,    "data", col=6, row=5,  w=6, h=4),
    tile("tile-alb-requests",          "ALB Requests",                       q_alb_requests,                 "data", col=0, row=9,  w=6, h=4),
    tile("tile-alb-conn-errors",       "ALB Target Connection Errors",       q_alb_target_connection_errors, "data", col=6, row=9,  w=6, h=4),
    tile("tile-task-counts",           "Task Counts (Desired/Running/Pending)", q_task_counts,               "data", col=0, row=13, w=6, h=4),
    tile("tile-deployment-count",      "Deployment Count",                   q_deployment_count,             "data", col=6, row=13, w=6, h=4),
    tile("tile-cpu-utilized",          "CPU Utilized",                       q_cpu_utilized,                 "data", col=0, row=17, w=6, h=4),
    tile("tile-memory-utilized",       "Memory Utilized",                    q_memory_utilized,              "data", col=6, row=17, w=6, h=4),
    tile("tile-cpu-throttling",        "CPU Throttling (Container, untested)", q_cpu_throttling,             "data", col=0, row=21, w=6, h=4),
    tile("tile-memory-pct",            "Memory Usage % (Container, untested)", q_memory_usage_pct,           "data", col=6, row=21, w=6, h=4),
    tile("tile-nonrunning-tasks",      "Non-Running Task Events",            q_nonrunning_tasks,             "data", col=0, row=25, w=6, h=4),
    tile("tile-unhealthy-containers",  "Unhealthy Container Events",         q_unhealthy_containers,         "data", col=6, row=25, w=6, h=4),
    tile("tile-recent-task-events",    "Recent Task Events",                 q_recent_task_events,           "data", col=0, row=29, w=12, h=6),
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

    doc_id, version = get_existing_dashboard_id(DASHBOARD_NAME)

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