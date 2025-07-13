# Existing data block for compliance user data
data "template_cloudinit_config" "compliance" {
  gzip          = true
  base64_encode = true
  # part {
  #   filename     = "ssm.cfg"
  #   content_type = "text/x-shellscript"
  #   content      = templatefile("${path.module}/resources/user_data_scripts/ssm_config.sh", { AD = local.AD })
  # }
  # ... other parts (tenable.cfg, datadog.cfg, dynamic custom_user_data) ...
}

# New data block to merge app_user_data with compliance data
data "template_cloudinit_config" "merged" {
  gzip          = true
  base64_encode = true

  # Include the original compliance data
  part {
    content_type = "text/cloud-config"
    content      = base64decode(data.template_cloudinit_config.compliance.rendered)
  }

  # Add app_user_data if provided
  dynamic "part" {
    for_each = var.app_user_data != null && var.app_user_data != "" ? [1] : []
    content {
      content_type = "text/x-shellscript"
      content      = base64decode(var.app_user_data)
    }
  }
}

# Update locals to use the merged data


  app_user_data     = var.app_user_data

  # Use the merged data block output
  user_data_base64  = data.template_cloudinit_config.merged.rendered
}

