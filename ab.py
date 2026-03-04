import boto3
import requests
import json

# ─────────────────────────────────────────────
# CONFIG — update these as needed
# ─────────────────────────────────────────────
APP_NAME               = "my-app"
ENVIRONMENT_NAME       = "prod"
CONFIG_PROFILE_NAME    = "my-config"
DEPLOYMENT_STRATEGY    = "AppConfig.AllAtOnce"  # or your custom strategy

# The specific key+value you want to update
UPDATE_KEY             = "api_version"
UPDATE_VALUE           = "3.0.0"

# AppConfig Agent local endpoint (Lambda extension or ECS sidecar)
LOCAL_AGENT_URL = (
    f"http://localhost:2772/applications/{APP_NAME}"
    f"/environments/{ENVIRONMENT_NAME}"
    f"/configurations/{CONFIG_PROFILE_NAME}"
)
# ─────────────────────────────────────────────


client = boto3.client("appconfig")

# ── ID resolution helpers ─────────────────────

def get_app_id(app_name: str) -> str:
    paginator = client.get_paginator("list_applications")
    for page in paginator.paginate():
        for app in page["Items"]:
            if app["Name"] == app_name:
                return app["Id"]
    raise ValueError(f"App '{app_name}' not found")


def get_environment_id(app_id: str, env_name: str) -> str:
    paginator = client.get_paginator("list_environments")
    for page in paginator.paginate(ApplicationId=app_id):
        for env in page["Items"]:
            if env["Name"] == env_name:
                return env["Id"]
    raise ValueError(f"Environment '{env_name}' not found")


def get_config_profile_id(app_id: str, profile_name: str) -> str:
    paginator = client.get_paginator("list_configuration_profiles")
    for page in paginator.paginate(ApplicationId=app_id):
        for profile in page["Items"]:
            if profile["Name"] == profile_name:
                return profile["Id"]
    raise ValueError(f"Config profile '{profile_name}' not found")


def get_deployment_strategy_id(strategy_name: str) -> str:
    paginator = client.get_paginator("list_deployment_strategies")
    for page in paginator.paginate():
        for strategy in page["Items"]:
            if strategy["Name"] == strategy_name:
                return strategy["Id"]
    raise ValueError(f"Deployment strategy '{strategy_name}' not found")


# ── Module-level ID cache (reused across warm Lambda invocations) ──
_ids: dict = {}

def get_cached_ids() -> dict:
    if not _ids:
        app_id      = get_app_id(APP_NAME)
        _ids["app"]      = app_id
        _ids["env"]      = get_environment_id(app_id, ENVIRONMENT_NAME)
        _ids["profile"]  = get_config_profile_id(app_id, CONFIG_PROFILE_NAME)
        _ids["strategy"] = get_deployment_strategy_id(DEPLOYMENT_STRATEGY)
        print(f"[IDs resolved] app={_ids['app']} env={_ids['env']} "
              f"profile={_ids['profile']} strategy={_ids['strategy']}")
    return _ids


# ── Read current config from local AppConfig Agent ────────────────

def read_config_local() -> dict:
    """
    Reads config from the AppConfig Agent running on localhost:2772.
    Returns parsed JSON as a dict.
    """
    response = requests.get(LOCAL_AGENT_URL, timeout=5)
    response.raise_for_status()
    config = response.json()
    print(f"[Read] Current config: {json.dumps(config, indent=2)}")
    return config


# ── Update a single key and deploy ───────────────────────────────

def update_and_deploy(key: str, value) -> None:
    """
    1. Reads current config from local agent
    2. Updates only the specified key (all other fields preserved)
    3. Creates a new hosted config version
    4. Starts a deployment
    """
    # Step 1 — Read current config
    current_config = read_config_local()

    # Step 2 — Patch only the target key
    if current_config.get(key) == value:
        print(f"[Skip] '{key}' is already '{value}'. No update needed.")
        return

    updated_config = {**current_config, key: value}   # all fields preserved
    print(f"[Update] '{key}': '{current_config.get(key)}' → '{value}'")

    # Step 3 — Resolve IDs (cached after first call)
    ids = get_cached_ids()

    # Step 4 — Create new hosted config version
    version_response = client.create_hosted_configuration_version(
        ApplicationId=ids["app"],
        ConfigurationProfileId=ids["profile"],
        Content=json.dumps(updated_config).encode("utf-8"),
        ContentType="application/json",
    )
    version_number = version_response["VersionNumber"]
    print(f"[Version] Created version: {version_number}")

    # Step 5 — Start deployment
    client.start_deployment(
        ApplicationId=ids["app"],
        EnvironmentId=ids["env"],
        DeploymentStrategyId=ids["strategy"],
        ConfigurationProfileId=ids["profile"],
        ConfigurationVersion=str(version_number),
    )
    print(f"[Deploy] Deployment started for version {version_number} ✅")


# ── Lambda handler ────────────────────────────────────────────────

def lambda_handler(event, context):
    """
    Lambda entrypoint.
    Optionally accepts override key/value from the event payload:
      { "key": "api_version", "value": "3.1.0" }
    Falls back to module-level UPDATE_KEY / UPDATE_VALUE.
    """
    key   = event.get("key", UPDATE_KEY)
    value = event.get("value", UPDATE_VALUE)

    update_and_deploy(key, value)

    return {
        "statusCode": 200,
        "body": f"Successfully updated '{key}' to '{value}'"
    }


# ── Local testing ─────────────────────────────────────────────────

if __name__ == "__main__":
    update_and_deploy(UPDATE_KEY, UPDATE_VALUE)