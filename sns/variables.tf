variable "env_name" {
  type = string
}

variable "env_type" {
  type = string
}

variable "region" {
  type = string
}

variable "app_name" {
  type = string
}

variable "functionality" {
  type    = string
  default = null
}

variable "source_name" {
  type    = string
  default = null
}

variable "destination_name" {
  type    = string
  default = null
}

variable "software" {
  type    = string
  default = null
}

variable "organization" {
  type    = string
  default = null
}

variable "user_defined" {
  type    = string
  default = null
}

variable "ordinal" {
  type    = number
  default = 0
}

variable "region_short" {
  description = "Optional map to convert a region into a short token for naming. If key not found, falls back to var.region."
  type        = map(string)
  default     = {}
}

variable "is_fifo" {
  type    = bool
  default = false
}

variable "kms_key" {
  description = "KMS key ARN for SNS encryption (mandatory)."
  type        = string
}

variable "topic_props" {
  description = "Optional topic properties object from YAML (display_name, fifo_props, delivery_policy, etc.)."
  type        = any
  default     = {}
}

variable "subscriptions" {
  description = <<EOT
List of subscriptions. Each item:
- protocol (string) required
- endpoint (string) required
- props (object/map) optional; may include:
  - endpoint_auto_confirms (bool) [http/https only]
  - filter_policy (map or json string)
  - filter_policy_scope (string)
  - raw_message_delivery (bool)
  - redrive_policy (map or json string)
  - delivery_policy (map or json string)
EOT
  type    = list(any)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
