# TFC config
variable "tfc_org" {
  description = "TFC Organization name"
  type        = string
}

variable "workspace_a_name" {
  description = "Name of Workspace A to read state from"
  type        = string
}

variable "trigger_tag_update" {
  description = "Bump this value to trigger a new tagging run e.g v1 to v2"
  type        = string
  default     = "v1"
}

# Bitbucket config
variable "bb_project" {
  description = "Bitbucket project key where Repo A lives"
  type        = string
}

variable "bb_repo" {
  description = "Bitbucket repository name for Repo A"
  type        = string
}

variable "bb_uid" {
  description = "Bitbucket username for authentication"
  type        = string
  sensitive   = true
}

variable "bb_pwd" {
  description = "Bitbucket password or app token for authentication"
  type        = string
  sensitive   = true
}

# Tag values
variable "tag_costcenter" {
  description = "Value for costcenter tag"
  type        = string
}

variable "tag_billingcode" {
  description = "Value for BillingCode tag"
  type        = string
}

# Run mode
variable "dry_run" {
  description = "Set to true to preview changes without applying. Set to false to apply."
  type        = string
  default     = "true"
}