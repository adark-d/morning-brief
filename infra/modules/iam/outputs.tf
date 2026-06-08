output "batch_role_arn" {
  description = "Execution role ARN for the batch Lambda."
  value       = aws_iam_role.batch.arn
}

output "scheduler_role_arn" {
  description = "Role ARN the EventBridge Scheduler assumes to invoke the batch Lambda."
  value       = aws_iam_role.scheduler.arn
}
