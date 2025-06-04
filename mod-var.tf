variable "name" {
  description = "Name of the Kendra index"
  type        = string
}

variable "edition" {
  description = "Kendra index edition: DEVELOPER_EDITION or ENTERPRISE_EDITION"
  type        = string
  default     = "ENTERPRISE_EDITION"
}

variable "description" {
  description = "Optional description for the index"
  type        = string
  default     = ""
}

variable "kms_key_id" {
  description = "ARN of the KMS key used for encryption"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the Kendra index and IAM role"
  type        = map(string)
  default     = {}
}


variable "query_units" {
  type        = number
  default     = 1
  description = "Query capacity units for ENTERPRISE edition"
}

variable "storage_units" {
  type        = number
  default     = 1
  description = "Storage capacity units for ENTERPRISE edition"
}
