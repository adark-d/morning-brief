output "path_prefix" {
  description = "SSM path under which secrets live (/morning-brief). Scope IAM ssm:GetParametersByPath here."
  value       = local.path
}
