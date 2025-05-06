variable "delete_default_vpc" {
  description = "Flag to indicate whether to delete the default VPC"
  type        = bool
  default     = false 
}

resource "null_resource" "delete_default_vpc" {
  count = var.delete_default_vpc ? 1 : 0

  provisioner "local-exec" {
    command = "bash ./delete_default_vpc.sh"
    on_failure = "continue"  # Optional: Continue even if the script fails
  }

  triggers = {
    always_run = "${timestamp()}"
  }
}
