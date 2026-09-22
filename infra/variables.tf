variable "project" {
  description = "Project name for resource names and tags; the runtime SSM path is /morning-brief."
  type        = string
  default     = "morning-brief"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "eu-west-2"
}

variable "ecr_repository_name" {
  description = "ECR repository name for the container image."
  type        = string
  default     = "morning-brief"
}

variable "image_tag" {
  description = "Existing immutable ECR image tag, normally a build commit SHA."
  type        = string
}

variable "lambda_timeout_seconds" {
  description = "Lambda deadline, including SSM startup and time to log pipeline failures."
  type        = number
  default     = 480
}

variable "sender" {
  description = "Verified sender address for SMTP delivery."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to the alerts SNS topic (confirmation required once)."
  type        = string
  default     = ""
  validation {
    condition     = !var.schedule_enabled || can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.alert_email))
    error_message = "Set an alert email before enabling the schedules."
  }
}

variable "github_owner" {
  description = "GitHub org/user owning the repo (for the OIDC deploy role trust)."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name (for the OIDC deploy role trust)."
  type        = string
  default     = "morning-brief"
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "existing_oidc_provider_arn" {
  description = "ARN of an existing GitHub OIDC provider (when create_oidc_provider = false)."
  type        = string
  default     = ""
}

variable "selection_model" {
  description = "Anthropic model used to rank topics."
  type        = string
  default     = "claude-haiku-4-5"
}

variable "explanation_model" {
  description = "Anthropic model used to write lessons."
  type        = string
  default     = "claude-sonnet-4-5-20250929"
}

variable "smtp_host" {
  description = "Reachable SMTP server hostname."
  type        = string
}

variable "pipeline_timeout_seconds" {
  description = "Application deadline; Lambda must allow at least 60 extra seconds for startup and cleanup."
  type        = number
  default     = 420
  validation {
    condition = (
      var.pipeline_timeout_seconds > 0 && var.pipeline_timeout_seconds <= 600 &&
      var.lambda_timeout_seconds >= var.pipeline_timeout_seconds + 60 &&
      var.lambda_timeout_seconds <= 900 && floor(var.lambda_timeout_seconds) == var.lambda_timeout_seconds
    )
    error_message = "Pipeline timeout must be within (0, 600]; Lambda must be an integer at least 60 seconds longer and no greater than 900."
  }
}

variable "schedule_expression" {
  description = "When to send the brief; default is every weekday at 07:00."
  type        = string
  default     = "cron(0 7 ? * MON-FRI *)"
}

variable "schedule_timezone" {
  description = "IANA timezone for the briefing schedule."
  type        = string
  default     = "Europe/London"
}

variable "schedule_enabled" {
  description = "Enable only after the image and secret values are ready."
  type        = bool
  default     = false
}

variable "missed_run_hours" {
  description = "Consecutive hours without a healthy completion before alerting; allow for the schedule interval and daylight saving."
  type        = number
  default     = 74
  validation {
    condition     = var.missed_run_hours >= 1 && var.missed_run_hours <= 168 && floor(var.missed_run_hours) == var.missed_run_hours
    error_message = "missed_run_hours must be an integer from 1 to 168."
  }
}

variable "brief_settings" {
  description = "Optional non-secret Settings overrides. Omitted values use Python defaults; collections are JSON encoded for Lambda."
  type = object({
    interests                   = optional(string)
    source_names                = optional(list(string))
    source_hosts                = optional(list(string))
    topic_count                 = optional(number)
    max_age_hours               = optional(number)
    selection_max_tokens        = optional(number)
    explanation_max_tokens      = optional(number)
    agent_retries               = optional(number)
    model_request_limit         = optional(number)
    http_timeout_seconds        = optional(number)
    model_timeout_seconds       = optional(number)
    fetch_timeout_seconds       = optional(number)
    selection_timeout_seconds   = optional(number)
    enrichment_timeout_seconds  = optional(number)
    explanation_timeout_seconds = optional(number)
    source_content_min_chars    = optional(number)
    source_content_max_chars    = optional(number)
    email_subject               = optional(string)
    smtp_port                   = optional(number)
    smtp_start_tls              = optional(bool)
    smtp_use_tls                = optional(bool)
    smtp_timeout_seconds        = optional(number)
  })
  default = {}
}

variable "completion_check_schedule" {
  description = "Check after each delivery window; update alongside schedule_expression."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}

variable "completion_check_lookback_minutes" {
  description = "Window containing the expected run, shorter than the gap between runs."
  type        = number
  default     = 120
  validation {
    condition     = var.completion_check_lookback_minutes >= 10 && var.completion_check_lookback_minutes <= 1440 && floor(var.completion_check_lookback_minutes) == var.completion_check_lookback_minutes
    error_message = "Completion-check lookback must be an integer from 10 to 1440 minutes."
  }
}
