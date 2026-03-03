# variables.tf

variable "tfc_token" {
  description = "TFC API token with read access to Workspace A"
  type        = string
  sensitive   = true
}

variable "tfc_org" {
  description = "TFC Organization name"
  type        = string
}

variable "workspace_a_name" {
  description = "Name of Workspace A to read resources from"
  type        = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "tag_costcenter" {
  type = string
}
variable "tag_billingcode" {
  type = string
}
variable "dry_run" {
  type    = string
  default = "true"   # safe default — dry-run unless explicitly false
}
variable "trigger_tag_update" {
  type    = string
  default = "v1"     # bump this value to trigger a new tagging run
}