variable "name_prefix" {
  description = "Prefix for the key alias and description (e.g. \"morning-brief-prod\")."
  type        = string
}

variable "tags" {
  description = "Tags applied to the KMS key."
  type        = map(string)
  default     = {}
}
