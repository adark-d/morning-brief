output "deploy_role_arn" {
  description = "Role ARN GitHub Actions assumes via OIDC (set as the workflow's role-to-assume)."
  value       = aws_iam_role.deploy.arn
}
