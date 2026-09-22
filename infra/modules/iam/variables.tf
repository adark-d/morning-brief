variable "name_prefix" {
  description = "Prefix for role names (e.g. \"morning-brief\")."
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

variable "kms_key_arn" {
  description = "Customer-managed KMS key ARN for SSM decryption."
  type        = string
}

variable "ssm_path" {
  description = "SSM path prefix for secrets, e.g. /morning-brief (no trailing slash)."
  type        = string
}
