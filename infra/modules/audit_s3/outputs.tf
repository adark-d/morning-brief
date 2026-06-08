output "bucket_name" {
  description = "Audit bucket name (set as MORNING_BRIEF_AUDIT__S3_BUCKET)."
  value       = aws_s3_bucket.audit.id
}

output "bucket_arn" {
  description = "Audit bucket ARN (for scoping the batch role's S3 permissions)."
  value       = aws_s3_bucket.audit.arn
}
