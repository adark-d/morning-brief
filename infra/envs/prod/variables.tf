variable "project" {
  description = "Project name; used in resource names, tags, and the SSM secrets path."
  type        = string
  default     = "morning-brief"
}

variable "environment" {
  description = "Environment name; selects the config YAML and the SSM secrets path segment."
  type        = string
  default     = "production"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "eu-west-2"
}

variable "audit_bucket_name" {
  description = "Globally-unique name for the immutable audit bucket."
  type        = string
}

variable "ecr_repository_name" {
  description = "ECR repository name for the container image."
  type        = string
  default     = "morning-brief"
}

variable "image_tag" {
  description = "Image tag to deploy (pin to a digest or build SHA; tags are immutable in ECR)."
  type        = string
}

variable "retention_years" {
  description = "Object Lock retention in years. IRREVERSIBLE in COMPLIANCE mode."
  type        = number
  default     = 7
}

variable "smtp_from" {
  description = "Verified sender address for the Resend SMTP send (non-secret; set per the verified domain)."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to the alerts SNS topic (confirmation required once)."
  type        = string
  default     = ""
}

variable "slack_channel_id" {
  description = "Slack channel id for Chatbot alerts; empty disables Slack."
  type        = string
  default     = ""
}

variable "slack_team_id" {
  description = "Slack workspace/team id (from the one-time Chatbot authorization)."
  type        = string
  default     = ""
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
