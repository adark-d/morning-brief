variable "repository_name" {
  description = "ECR repository name (e.g. \"morning-brief\")."
  type        = string
}

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN for image encryption at rest."
  type        = string
}

variable "keep_last_images" {
  description = "Number of most-recent images to retain; older ones expire."
  type        = number
  default     = 10
}

variable "tags" {
  description = "Tags applied to the repository."
  type        = map(string)
  default     = {}
}
