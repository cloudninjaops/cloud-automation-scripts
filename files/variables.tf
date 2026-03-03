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
