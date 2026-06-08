"""
Dynatrace Dashboard 2.0 Creator — Lambda Monitoring
Uses: /platform/document/v1/documents API

Verified metrics for this environment:
  dt.cloud.aws.lambda.invocations
  dt.cloud.aws.lambda.errors
  dt.cloud.aws.lambda.duration
  dt.cloud.aws.lambda.throttlers
"""

import json
import os
import requests
import sys

# ──────────────────────────────────────────────
# CONFIG — fill these in or set env vars
# ──────────────────────────────────────────────
DT_BASE_URL  = "https://xyz.apps.dynatrace.com"       # your DT base URL
DT_API_TOKEN = os.environ.get("DT_API_TOKEN", "")     # set env var or paste token here
LAMBDA_PREFIX  = "ab-xyz-cdf-"                        # your lambda prefix
DASHBOARD_NAME = "Lambda Monitoring - ab-xyz-cdf"
# ──────────────────────────────────────────────

# No Content-Type — requests sets it automatically for multipart
HEADERS = {
    "Authorization": f"Api-Token {DT_API_TOKEN}",
}


def build_dashboard_payload(name: str, prefix: str) -> dict:
    """
    Builds the Dynatrace Dashboard 2.0 document payload.
    All DQL queries use verified metric names scoped to lambda prefix.
    """

    # ── Metric tiles ──────────────────────────────────────────────────────────

    q_invocations = (
        f'timeseries invocations = sum(dt.cloud.aws.lambda.invocations), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_errors = (
        f'timeseries errors = sum(dt.cloud.aws.lambda.errors), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_avg_duration = (
        f'timeseries avg_duration = avg(dt.cloud.aws.lambda.duration), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_p95_duration = (
        f'timeseries p95_duration = percentile(dt.cloud.aws.lambda.duration, 95), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_throttlers = (
        f'timeseries throttlers = sum(dt.cloud.aws.lambda.throttlers), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    # Error rate derived: errors / invocations * 100
    q_error_rate = (
        f'timeseries errors = sum(dt.cloud.aws.lambda.errors), '
        f'invocations = sum(dt.cloud.aws.lambda.invocations), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}") '
        f'| fieldsAdd error_rate = if(invocations[0] > 0, (errors[0] / invocations[0]) * 100, else: 0)'
    )

    # ── Log tile ──────────────────────────────────────────────────────────────

    q_error_logs = (
        f'fetch logs '
        f'| filter matchesPhrase(aws.log_group, "{prefix}") '
        f'| filter loglevel == "ERROR" or matchesPhrase(content, "ERROR") '
        f'| sort timestamp desc '
        f'| limit 50 '
        f'| fields timestamp, aws.log_group, content'
    )

    # ── Tile builder helper ───────────────────────────────────────────────────

    def tile(tile_id, title, query, tile_type="LINE_CHART", col=0, row=0, w=6, h=4):
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

    # ── Layout ────────────────────────────────────────────────────────────────
    # Row 1 — Invocations | Errors
    # Row 2 — Avg Duration | P95 Duration
    # Row 3 — Throttlers | Error Rate %
    # Row 4 — Recent Error Logs (full width)

    tiles = [
        tile("tile-invocations",  "Invocations",       q_invocations,  "LINE_CHART", col=0,  row=0,  w=6, h=4),
        tile("tile-errors",       "Errors",            q_errors,       "LINE_CHART", col=6,  row=0,  w=6, h=4),
        tile("tile-avg-duration", "Avg Duration (ms)", q_avg_duration, "LINE_CHART", col=0,  row=4,  w=6, h=4),
        tile("tile-p95-duration", "P95 Duration (ms)", q_p95_duration, "LINE_CHART", col=6,  row=4,  w=6, h=4),
        tile("tile-throttlers",   "Throttlers",        q_throttlers,   "LINE_CHART", col=0,  row=8,  w=6, h=4),
        tile("tile-error-rate",   "Error Rate (%)",    q_error_rate,   "LINE_CHART", col=6,  row=8,  w=6, h=4),
        tile("tile-error-logs",   "Recent Error Logs", q_error_logs,   "TABLE",      col=0,  row=12, w=12, h=6),
    ]

    dashboard_content = {
        "version": "10",
        "variables": [],
        "tiles": {t["id"]: t for t in tiles},
        "layouts": {
            "lg": [
                {
                    "id": t["id"],
                    "x": t["layout"]["x"],
                    "y": t["layout"]["y"],
                    "w": t["layout"]["w"],
                    "h": t["layout"]["h"],
                }
                for t in tiles
            ]
        },
    }

    return {
        "name": name,
        "type": "dashboard",
        "isPrivate": False,
        "content": json.dumps(dashboard_content),
    }


def create_dashboard():
    url = f"{DT_BASE_URL}/platform/document/v1/documents"
    payload = build_dashboard_payload(DASHBOARD_NAME, LAMBDA_PREFIX)

    print(f"Creating dashboard : {DASHBOARD_NAME}")
    print(f"Endpoint           : {url}\n")

    # Document API requires multipart/form-data — NOT application/json
    multipart = {
        "name":      (None, payload["name"]),
        "type":      (None, payload["type"]),
        "isPrivate": (None, str(payload["isPrivate"]).lower()),
        "content":   ("content", payload["content"], "application/json"),
    }

    response = requests.post(url, headers=HEADERS, files=multipart)

    if response.status_code in (200, 201):
        data = response.json()
        doc_id = data.get("id", "unknown")
        print(f"✅ Dashboard created successfully!")
        print(f"   ID  : {doc_id}")
        print(f"   URL : {DT_BASE_URL}/ui/document/{doc_id}")
    else:
        print(f"❌ Failed to create dashboard")
        print(f"   Status   : {response.status_code}")
        print(f"   Response : {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    create_dashboard()