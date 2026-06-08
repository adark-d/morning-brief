variable "project" {
  description = "Project segment of the SSM path (e.g. \"morning-brief\")."
  type        = string
  default     = "morning-brief"
}

variable "environment" {
  description = "Environment segment of the SSM path (e.g. \"production\"). bootstrap_secrets reads /<project>/<environment>/."
  type        = string
}

variable "secret_names" {
  description = "Exact MORNING_BRIEF_* env var names to create as SecureString parameters (basename of the SSM key)."
  type        = list(string)
}

variable "kms_key_id" {
  description = "Customer-managed KMS key id/ARN used to encrypt the SecureString values."
  type        = string
}

variable "tags" {
  description = "Tags applied to each parameter."
  type        = map(string)
  default     = {}
}
