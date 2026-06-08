variable "bucket_name" {
  description = "Globally-unique name for the audit bucket."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN for SSE-KMS."
  type        = string
}

variable "prefix" {
  description = "Key prefix under which run records are written (matches AuditSettings.s3_prefix)."
  type        = string
  default     = "runs"
}

variable "object_lock_mode" {
  description = "Object Lock retention mode: COMPLIANCE (no override, irreversible) or GOVERNANCE."
  type        = string
  default     = "COMPLIANCE"

  validation {
    condition     = contains(["COMPLIANCE", "GOVERNANCE"], var.object_lock_mode)
    error_message = "object_lock_mode must be COMPLIANCE or GOVERNANCE."
  }
}

variable "retention_years" {
  description = "Object Lock default retention in years. IRREVERSIBLE in COMPLIANCE mode."
  type        = number
  default     = 7
}

variable "glacier_after_days" {
  description = "Transition records to GLACIER after this many days."
  type        = number
  default     = 90
}

variable "deep_archive_after_days" {
  description = "Transition records to DEEP_ARCHIVE after this many days."
  type        = number
  default     = 365
}

variable "tags" {
  description = "Tags applied to the bucket."
  type        = map(string)
  default     = {}
}
