output "path_prefix" {
  description = "SSM path under which secrets live (/<project>/<environment>). Scope IAM ssm:GetParametersByPath here."
  value       = local.path
}

output "parameter_arns" {
  description = "ARNs of the created SSM parameters (for least-privilege IAM scoping)."
  value       = [for p in aws_ssm_parameter.secret : p.arn]
}
