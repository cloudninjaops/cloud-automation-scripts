###########################################################
#                      LOCALS                            #
###########################################################

locals {

  # ── Bitbucket URL — points to tagging_targets.yaml in Repo A master branch
  bb_base_url      = "https://bitbucket.yourorg.com/projects/${var.bb_project}/repos/${var.bb_repo}/raw"
  tagging_yaml_url = "${local.bb_base_url}/infrastructure/tagging/tagging_targets.yaml?at=refs/heads/master"
  authStr          = base64encode("${var.bb_uid}:${var.bb_pwd}")

  # ── Parse YAML body → extract tagging block
  # yamldecode handles '---' document separator automatically
  tagging_resources = yamldecode(data.http.tagging_yaml.body).tagging

  # ── Extract config block — required
  tagging_config = local.tagging_resources.config

  # ── Extract workspace block — optional
  # returns null if not present in YAML
  workspace = try(local.tagging_resources.workspace, null)

  # ── Extract tagsets block — optional
  # returns empty list if not present in YAML
  tagsets = try(local.tagging_resources.tagsets, [])

  # ── Resolve region — default to us-east-1 if not provided in YAML
  region = try(local.tagging_config.region, "us-east-1")

  # ── Resolve target_role_arn
  # Uses value from YAML if provided
  # Falls back to default role xyz using account_id from config
  target_role_arn = try(
    local.tagging_config.target_role_arn,
    "arn:aws:iam::${local.tagging_config.account_id}:role/xyz"
  )

  # ── Resolve workspace name — from YAML workspace block
  # Falls back to TFC variable if not in YAML
  workspace_name = try(
    local.workspace.name,
    var.workspace_a_name
  )
}

###########################################################
#                   DATA SOURCES                         #
###########################################################

# ── Fetch tagging_targets.yaml from Bitbucket Repo A master branch
data "http" "tagging_yaml" {
  url = local.tagging_yaml_url

  request_headers = {
    Authorization = "Basic ${local.authStr}"
  }
}

###########################################################
#                   LIST RESOURCES                       #
###########################################################

# ── Lists all resources from Workspace A state file
# Runs on every apply — useful for debugging and verification
resource "null_resource" "list_workspace_a_resources" {

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/list_resources.py"

    environment = {
      TFC_ORG        = var.tfc_org
      WORKSPACE_NAME = local.workspace_name
      # TFC_TOKEN — set directly in TFC workspace environment variables
      # Do not pass here — avoids sensitive value in Terraform logs
    }
  }
}

###########################################################
#                   TAG RESOURCES                        #
###########################################################

# ── Applies tags to all resources defined in tagging_targets.yaml
# Triggered by:
#   1. Manual bump of trigger_tag_update variable
#   2. Any change to tagging_targets.yaml content (yaml_hash)
resource "null_resource" "tag_workspace_a_resources" {

  triggers = {
    # Bump this variable manually to force a run
    # e.g. change v1 to v2 in TFC workspace variables
    tag_run = var.trigger_tag_update

    # Auto-detects YAML content changes
    # Re-runs automatically whenever tagging_targets.yaml is updated
    yaml_hash = md5(data.http.tagging_yaml.body)
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/update_tags.py"

    environment = {
      # ── TFC config ────────────────────────────────────────────────────
      TFC_ORG = var.tfc_org

      # ── AWS config ────────────────────────────────────────────────────
      AWS_REGION         = local.region
      ACCOUNT_B_ROLE_ARN = local.target_role_arn

      # ── Run mode ──────────────────────────────────────────────────────
      # DRY_RUN = "true"  → preview changes, nothing applied
      # DRY_RUN = "false" → apply tags for real
      # Always start with true — set to false when ready
      DRY_RUN = var.dry_run

      # ── Full YAML config passed as JSON to Python script ──────────────
      # Contains config, workspace, and tagsets blocks
      # Python reads and processes all blocks from this single variable
      TAGGING_CONFIG = jsonencode(local.tagging_resources)

      # ── TFC_TOKEN — set directly in TFC workspace environment variables
      # Do not pass here — avoids sensitive value in Terraform logs
    }
  }
}