output "repository_url" {
  description = "Repository URI to tag/push images to and reference from the Lambda image_uri."
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "Repository ARN (for scoping the CI deploy role's ECR push permission)."
  value       = aws_ecr_repository.this.arn
}

output "repository_name" {
  description = "Repository name."
  value       = aws_ecr_repository.this.name
}
