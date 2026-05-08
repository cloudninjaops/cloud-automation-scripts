###########################################################
#                      LOCALS                            #
###########################################################
locals {
  # Bitbucket base URL — points to Repo A master branch
  bb_base_url      = "https://bitbucket.yourorg.com/projects/${var.bb_project}/repos/${var.bb_repo}/raw"
  tagging_yaml_url = "${local.bb_base_url}/infrastructure/tagging/tagging_targets.yaml?at=refs/heads/master"
  authStr          = base64encode("${var.bb_uid}:${var.bb_pwd}")
}

###########################################################
#                   FETCH YAML FROM REPO A               #
###########################################################
data "http" "tagging_yaml" {
  url = local.tagging_yaml_url

  request_headers = {
    Authorization = "Basic ${local.authStr}"
  }
}

###########################################################
#                   DECODE YAML → JSON                   #
###########################################################
locals {
  # Parse YAML body → extract tagging_resources block
  tagging_resources = yamldecode(data.http.tagging_yaml.body).tagging_resources

  # Extract config block
  tagging_config    = local.tagging_resources.config

  # Extract resources_list block
  resources_list    = local.tagging_resources.resources_list

  # Resolve region — default to us-east-1 if not set
  region = try(local.tagging_config.region, "us-east-1")

  # Resolve target_role_arn — default to xyz role if not set
  target_role_arn = try(
    local.tagging_config.target_role_arn,
    "arn:aws:iam::${local.tagging_config.account_id}:role/xyz"
  )
}

###########################################################
#                   LIST RESOURCES                       #
###########################################################
resource "null_resource" "list_workspace_a_resources" {

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/list_resources.py"

    environment = {
      TFC_ORG        = var.tfc_org
      WORKSPACE_NAME = var.workspace_a_name
      # TFC_TOKEN set directly in TFC workspace env vars
    }
  }
}

###########################################################
#                   TAG RESOURCES                        #
###########################################################
resource "null_resource" "tag_workspace_a_resources" {

  triggers = {
    tag_run = var.trigger_tag_update
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/update_tags.py"

    environment = {
      # TFC config
      TFC_ORG        = var.tfc_org
      WORKSPACE_NAME = var.workspace_a_name

      # Tag values
      TAG_COSTCENTER  = var.tag_costcenter
      TAG_BILLINGCODE = var.tag_billingcode

      # Resolved from YAML
      AWS_REGION         = local.region
      ACCOUNT_B_ROLE_ARN = local.target_role_arn

      # Resources list from YAML — passed as JSON string
      RESOURCES_LIST = jsonencode(local.resources_list)

      # Run mode
      DRY_RUN = var.dry_run

      # TFC_TOKEN and BB creds set directly in TFC workspace env vars
    }
  }
}