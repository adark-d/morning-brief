output "ecr_repository_url" {
  description = "Tag/push images here; referenced by the Lambda image_uri."
  value       = module.ecr.repository_url
}

output "audit_bucket_name" {
  description = "Immutable audit bucket."
  value       = module.audit_s3.bucket_name
}

output "batch_function_name" {
  description = "Scheduled-brief Lambda function name (for manual invoke / CI deploy)."
  value       = module.batch_lambda.function_name
}

output "secrets_path" {
  description = "SSM path under which to set the real secret values."
  value       = module.secrets.path_prefix
}

output "alerts_sns_topic_arn" {
  description = "SNS topic for alerts."
  value       = module.observability.sns_topic_arn
}

output "github_deploy_role_arn" {
  description = "Role ARN for the GitHub Actions deploy workflow (role-to-assume)."
  value       = module.cicd.deploy_role_arn
}
