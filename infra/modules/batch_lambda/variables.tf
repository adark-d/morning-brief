variable "name_prefix" {
  description = "Prefix for the schedule name (e.g. \"morning-brief\")."
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
  description = "Lambda memory (MB). Tune from CloudWatch max-memory-used."
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Lambda timeout (s). Must exceed the application deadline plus startup headroom."
  type        = number
  default     = 480
}

variable "environment_variables" {
  description = "Non-secret runtime settings. Secrets are loaded from SSM."
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

variable "handler" {
  description = "Python Lambda handler for the scheduled workflow."
  type        = string
  default     = "ai_brief.handler.run_handler"
}

variable "schedule_enabled" {
  description = "Whether the schedule can invoke the function."
  type        = bool
  default     = false
}

variable "completion_check_schedule" {
  description = "Run after each expected brief to detect a missed completion."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}
