variable "name_prefix" {
  description = "Prefix for the schedule name (e.g. \"morning-brief-prod\")."
  type        = string
}

variable "function_name" {
  description = "Lambda function name (must match the name the iam module constructed ARNs from)."
  type        = string
}

variable "image_uri" {
  description = "Full ECR image reference (repo URL + tag) the function runs."
  type        = string
}

variable "role_arn" {
  description = "Batch Lambda execution role ARN (from the iam module)."
  type        = string
}

variable "scheduler_role_arn" {
  description = "EventBridge Scheduler role ARN (from the iam module)."
  type        = string
}

variable "dlq_name" {
  description = "SQS DLQ name (must match the name the iam module constructed the ARN from)."
  type        = string
}

variable "architecture" {
  description = "Lambda CPU architecture. arm64 (Graviton) is cheaper and matches the built image."
  type        = string
  default     = "arm64"
}

variable "memory_size" {
  description = "Lambda memory (MB). pandas/numpy are memory-hungry; tune from CloudWatch max-memory-used."
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Lambda timeout (s). Covers data fetch + LLM call (~30-60s) with headroom."
  type        = number
  default     = 180
}

variable "environment_variables" {
  description = "Non-secret env vars (ENVIRONMENT, audit bucket/region/kms). Secrets are injected from SSM at cold start."
  type        = map(string)
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression."
  type        = string
  default     = "cron(0 7 ? * MON-FRI *)"
}

variable "schedule_timezone" {
  description = "IANA timezone for the schedule so 07:00 is local year-round (handles BST)."
  type        = string
  default     = "Europe/London"
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the function."
  type        = number
  default     = 90
}

variable "tags" {
  description = "Tags applied to the function, queue, and log group."
  type        = map(string)
  default     = {}
}
