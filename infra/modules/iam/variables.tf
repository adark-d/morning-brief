variable "name_prefix" {
  description = "Prefix for role names (e.g. \"morning-brief-prod\")."
  type        = string
}

variable "function_name" {
  description = "Batch Lambda function name (used to construct its ARN + log-group ARN)."
  type        = string
}

variable "dlq_name" {
  description = "SQS DLQ name the scheduler may send to (used to construct its ARN)."
  type        = string
}

variable "audit_bucket_arn" {
  description = "Audit S3 bucket ARN."
  type        = string
}

variable "audit_prefix" {
  description = "Key prefix under which run records live (scopes s3:PutObject/GetObject)."
  type        = string
  default     = "runs"
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN (audit SSE-KMS + SSM SecureString)."
  type        = string
}

variable "ssm_path" {
  description = "SSM path prefix for secrets, e.g. /morning-brief/production (no trailing slash)."
  type        = string
}

variable "tags" {
  description = "Tags applied to the roles."
  type        = map(string)
  default     = {}
}
