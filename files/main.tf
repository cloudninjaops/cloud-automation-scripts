# main.tf

resource "null_resource" "list_workspace_a_resources" {

  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/list_resources.py"

    environment = {
      TFC_TOKEN      = var.tfc_token
      TFC_ORG        = var.tfc_org
      WORKSPACE_NAME = var.workspace_a_name
    }
  }
}
