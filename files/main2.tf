# main.tf

# ── List resources from Workspace A ──────────────────────────────────────────
resource "null_resource" "list_workspace_a_resources" {

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/list_resources.py"

    environment = {
      TFC_ORG        = var.tfc_org
      WORKSPACE_NAME = var.workspace_a_name
      # TFC_TOKEN is set directly as workspace environment variable in TFC UI
    }
  }
}

# ── Apply tags to all resources in Workspace A ────────────────────────────────
resource "null_resource" "tag_workspace_a_resources" {

  triggers = {
    # Change this value to force re-run when you want to apply tags again
    tag_run = var.trigger_tag_update
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/update_tags.py"

    environment = {
      TFC_ORG         = var.tfc_org
      WORKSPACE_NAME  = var.workspace_a_name
      AWS_REGION      = var.aws_region
      TAG_COSTCENTER  = var.tag_costcenter
      TAG_BILLINGCODE = var.tag_billingcode
      DRY_RUN         = var.dry_run
      # TFC_TOKEN is set directly as workspace environment variable in TFC UI
    }
  }
}
