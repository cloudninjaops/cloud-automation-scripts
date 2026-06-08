"""
Dynatrace Dashboard 2.0 Creator — Lambda Monitoring
Targets lambdas with prefix: ab-xyz-cdf-
Uses: /platform/document/v1/documents API
"""

import json
import requests
import sys

# ──────────────────────────────────────────────
# CONFIG — fill these in
# ──────────────────────────────────────────────
DT_BASE_URL = "https://xyz.apps.dynatrace.com"   # your DT base URL
DT_API_TOKEN = "dt0c01.XXXX"                      # your API token
LAMBDA_PREFIX = "ab-xyz-cdf-"                     # your lambda prefix
DASHBOARD_NAME = "Lambda Monitoring - ab-xyz-cdf"
# ──────────────────────────────────────────────


HEADERS = {
    "Authorization": f"Api-Token {DT_API_TOKEN}",
    "Content-Type": "application/json",
}


def build_dashboard_payload(name: str, prefix: str) -> dict:
    """
    Builds the Dynatrace Dashboard 2.0 document payload.
    Each tile uses DQL queries scoped to the lambda prefix.
    """

    # DQL queries
    q_invocations = (
        f'timeseries invocations = sum(aws.lambda.invocations), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_error_rate = (
        f'timeseries errors = sum(aws.lambda.errors), invocations = sum(aws.lambda.invocations), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}") '
        f'| fieldsAdd error_rate = if(invocations > 0, (errors / invocations) * 100, else: 0)'
    )

    q_avg_duration = (
        f'timeseries avg_duration = avg(aws.lambda.duration), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_p95_duration = (
        f'timeseries p95_duration = percentile(aws.lambda.duration, 95), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_throttles = (
        f'timeseries throttles = sum(aws.lambda.throttles), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_cold_starts = (
        f'timeseries cold_starts = sum(aws.lambda.init_duration, default: 0), '
        f'by: {{entity.name}} '
        f'| filter matchesPhrase(entity.name, "{prefix}")'
    )

    q_error_logs = (
        f'fetch logs '
        f'| filter matchesPhrase(aws.log_group, "{prefix}") '
        f'| filter loglevel == "ERROR" or matchesPhrase(content, "ERROR") '
        f'| sort timestamp desc '
        f'| limit 50 '
        f'| fields timestamp, aws.log_group, content'
    )

    # Tile builder helper
    def tile(tile_id, title, query, tile_type="LINE_CHART", col=0, row=0, w=6, h=4):
        return {
            "id": tile_id,
            "type": tile_type,
            "title": title,
            "query": query,
            "layout": {
                "x": col,
                "y": row,
                "w": w,
                "h": h,
            },
            "querySettings": {
                "maxResultRecords": 1000,
                "defaultTimeframeForLocalQueries": "now-2h",
            },
        }

    tiles = [
        # Row 1 — Invocations + Error Rate
        tile("tile-invocations",  "Invocations",      q_invocations,  "LINE_CHART", col=0,  row=0,  w=6, h=4),
        tile("tile-error-rate",   "Error Rate (%)",   q_error_rate,   "LINE_CHART", col=6,  row=0,  w=6, h=4),

        # Row 2 — Duration
        tile("tile-avg-duration", "Avg Duration (ms)", q_avg_duration, "LINE_CHART", col=0,  row=4,  w=6, h=4),
        tile("tile-p95-duration", "P95 Duration (ms)", q_p95_duration, "LINE_CHART", col=6,  row=4,  w=6, h=4),

        # Row 3 — Throttles + Cold Starts
        tile("tile-throttles",    "Throttles",         q_throttles,    "LINE_CHART", col=0,  row=8,  w=6, h=4),
        tile("tile-cold-starts",  "Cold Starts",       q_cold_starts,  "LINE_CHART", col=6,  row=8,  w=6, h=4),

        # Row 4 — Error Logs (full width)
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

    print(f"Creating dashboard: {DASHBOARD_NAME}")
    print(f"Endpoint: {url}\n")

    response = requests.post(url, headers=HEADERS, json=payload)

    if response.status_code in (200, 201):
        data = response.json()
        doc_id = data.get("id", "unknown")
        print(f"✅ Dashboard created successfully!")
        print(f"   ID   : {doc_id}")
        print(f"   URL  : {DT_BASE_URL}/ui/document/{doc_id}")
    else:
        print(f"❌ Failed to create dashboard")
        print(f"   Status : {response.status_code}")
        print(f"   Response: {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    create_dashboard()