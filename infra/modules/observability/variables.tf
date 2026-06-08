variable "name_prefix" {
  description = "Prefix for topic/alarm names (e.g. \"morning-brief-prod\")."
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

variable "slack_channel_id" {
  description = "Slack channel id for Chatbot alerts; empty disables Slack."
  type        = string
  default     = ""
}

variable "slack_team_id" {
  description = "Slack workspace/team id (from the one-time Chatbot console authorization)."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to the alerting resources."
  type        = map(string)
  default     = {}
}
