variable "name_prefix" {
  description = "Prefix for topic/alarm names (e.g. \"morning-brief\")."
  type        = string
}

variable "function_name" {
  description = "Batch Lambda function name (Errors alarm dimension)."
  type        = string
}

variable "dlq_name" {
  description = "SQS DLQ name (DLQ-depth alarm dimension)."
  type        = string
}

variable "log_group_name" {
  description = "Batch Lambda log group name (missed-run metric filter target)."
  type        = string
}

variable "metric_namespace" {
  description = "CloudWatch namespace for the derived success metric."
  type        = string
  default     = "MorningBrief"
}

variable "alert_email" {
  description = "Email address for SNS alerts; empty disables the email subscription."
  type        = string
  default     = ""
}

variable "missed_run_hours" {
  description = "Consecutive hourly periods without a healthy completed run before alerting."
  type        = number
  default     = 74
}

variable "schedule_enabled" {
  description = "Disable missing-run notifications while the schedule is intentionally paused."
  type        = bool
  default     = false
}
