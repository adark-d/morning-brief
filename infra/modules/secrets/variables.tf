variable "path_prefix" {
  description = "Absolute runtime SSM path without a trailing slash."
  type        = string
  default     = "/morning-brief"
}

variable "secret_names" {
  description = "Exact MORNING_BRIEF_* env var names to create as SecureString parameters (basename of the SSM key)."
  type        = list(string)
}

variable "kms_key_id" {
  description = "Customer-managed KMS key id/ARN used to encrypt the SecureString values."
  type        = string
}
