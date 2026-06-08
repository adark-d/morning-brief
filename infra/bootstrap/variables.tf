variable "region" {
  description = "AWS region for the Terraform remote-state backend resources."
  type        = string
  default     = "eu-west-2"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket name that will hold Terraform remote state."
  type        = string
}

variable "lock_table_name" {
  description = "DynamoDB table name for Terraform state locking."
  type        = string
  default     = "morning-brief-tf-locks"
}
