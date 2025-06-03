variable "name" {
  description = "Logical name of the Kendra index (used in naming)"
  type        = string
}

variable "description" {
  description = "Optional description for the Kendra index"
  type        = string
  default     = ""
}

variable "edition" {
  description = "Kendra edition - DEVELOPER_EDITION or ENTERPRISE_EDITION"
  type        = string
  default     = "DEVELOPER_EDITION"
}

variable "kms_key_id" {
  description = "KMS key ARN used for server-side encryption"
  type        = string
}

variable "s3_bucket_name" {
  description = "Optional S3 bucket name for Kendra documents"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags applied to all Kendra-related resources"
  type        = map(string)
  default     = {}
}

variable "app_name" {
  description = "Application name for tagging and naming"
  type        = string
}

variable "env_type" {
  description = "Environment type (dev/stage/prod)"
  type        = string
}

variable "env_name" {
  description = "Environment name (like d1, p1, etc.)"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "env_type_short" {
  type        = map(string)
  description = "Mapping from env_type to short prefix"
}

variable "region_short" {
  type        = map(string)
  description = "Mapping from region name to short code"
}
