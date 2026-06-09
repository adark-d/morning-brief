variable "name_prefix" {
  description = "Prefix for the deploy role name (e.g. \"morning-brief-prod\")."
  type        = string
}

variable "github_owner" {
  description = "GitHub org/user that owns the repository."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name."
  type        = string
}

variable "github_environment" {
  description = "GitHub Actions environment whose OIDC tokens may assume the deploy role."
  type        = string
  default     = "production"
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC provider. Set false if one already exists in the account."
  type        = bool
  default     = true
}

variable "existing_oidc_provider_arn" {
  description = "ARN of a pre-existing GitHub OIDC provider (used when create_oidc_provider = false)."
  type        = string
  default     = ""
}

variable "ecr_repository_arn" {
  description = "ECR repository ARN the deploy role may push to."
  type        = string
}

variable "lambda_function_arn" {
  description = "Lambda function ARN the deploy role may update."
  type        = string
}

variable "tags" {
  description = "Tags applied to the deploy role."
  type        = map(string)
  default     = {}
}
