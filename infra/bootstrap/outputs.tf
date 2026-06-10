output "state_bucket" {
  description = "Name of the S3 bucket holding Terraform remote state. Use as the prod backend `bucket`."
  value       = aws_s3_bucket.state.id
}
