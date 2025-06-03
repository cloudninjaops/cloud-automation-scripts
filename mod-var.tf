variable "name" {
  description = "Name of the Kendra index"
  type        = string
}

variable "edition" {
  description = "Kendra index edition: DEVELOPER_EDITION or ENTERPRISE_EDITION"
  type        = string
  default     = "DEVELOPER_EDITION"
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
