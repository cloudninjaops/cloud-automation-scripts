resource "aws_secretsmanager_secret" "acm_key" {
  name        = "${var.env_type}-${var.app_name}-acm-cert-key"
  description = "Private key for ${var.env_type}-${var.app_name} ACM certificate"
  tags        = var.tags
}

resource "aws_secretsmanager_secret_version" "acm_key_version" {
  secret_id     = aws_secretsmanager_secret.acm_key.id
  secret_string = data.external.get-certificate.result.private_key
}

<OrganizationName>-<EnvironmentType>-<EnvironmentName>-<Region>-sm-<Application>-<Purpose>-<Ordinal###>

output "acm_cert_arn" {
  value = aws_acm_certificate.app_cert.arn
}

output "cert_key_secret_name" {
  value = aws_secretsmanager_secret.cert_key.name
}

module "ec2_instance" {
  source = "..."

  acm_cert_arn         = module.acm.acm_cert_arn
  cert_key_secret_name = module.acm.cert_key_secret_name
}
---
data "template_file" "user_data" {
  template = file("${path.module}/templates/user_data.sh.tpl")
  vars = {
    acm_cert_arn         = module.acm.acm_cert_arn
    cert_key_secret_name = module.acm.cert_key_secret_name
  }
}

resource "aws_launch_template" "lt" {
  ...
  user_data = base64encode(data.template_file.user_data.rendered)
}
----

resource "aws_launch_template" "lt" {
  ...
  user_data = base64encode(templatefile("${path.module}/userdata.sh.tpl", {
    cert_arn              = var.cert_arn,
    cert_key_secret_name  = var.cert_key_secret_name
  }))
}

----
user_data.sh.tpl

#!/bin/bash
CERT_ARN="${acm_cert_arn}"
SECRET_NAME="${cert_key_secret_name}"

# Fetch cert from ACM (optional: if cert download logic exists)
# Fetch private key from Secrets Manager
aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --region us-east-1 --query SecretString --output text > /etc/myapp/ssl/private.key

# Use certificate and key in your app
---
user_data.sh.tpl
#!/bin/bash

CERT_PATH="/etc/ssl/myapp"
mkdir -p ${CERT_PATH}

# Fetch private key from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id ${cert_key_secret_name} \
  --query SecretString \
  --region <your-region> \
  --output text > ${CERT_PATH}/myapp.key

# Fetch cert if needed using cert_arn (optional)
# You can also pre-attach cert to ALB instead if not needed locally
---

locals {
  cert_arn             = module.acm["${local.app_key}"].acm_cert_arn
  cert_key_secret_name = module.acm["${local.app_key}"].cert_key_secret_name
}
-----

# Local flag to check if both values exist
locals {
  enable_cert_user_data = (
    try(length(trimspace(var.cert_key_secret_name)), 0) > 0 &&
    try(length(trimspace(var.acm_cert_arn)), 0) > 0
  )
}

# Conditionally add asg_cert_config.sh to cloud-init
dynamic "part" {
  for_each = local.enable_cert_user_data ? [1] : []
  content {
    filename     = "asg_cert_config.sh"
    content_type = "text/x-shellscript"
    content      = templatefile("${path.module}/resources/user_data_scripts/asg_cert_config.sh", {
      cert_secret = var.cert_key_secret_name,
      acm_arn     = var.acm_cert_arn
    })
    merge_type   = "list(append)+"
  }
}

resource "null_resource" "debug_cert_vars" {
  provisioner "local-exec" {
    command = <<EOT
      echo "=== DEBUG: Certificate Variables ==="
      echo "Region: ${var.region}"
      echo "Cert Key Secret Name: ${var.cert_key_secret_name}"
      echo "ACM Cert ARN: ${var.acm_cert_arn}"
      echo "====================================="
    EOT
  }
}
