output "function_name" {
  description = "Batch Lambda function name."
  value       = aws_lambda_function.batch.function_name
}

output "function_arn" {
  description = "Batch Lambda function ARN."
  value       = aws_lambda_function.batch.arn
}

output "log_group_name" {
  description = "CloudWatch log group name (for the missed-run metric filter)."
  value       = aws_cloudwatch_log_group.batch.name
}

output "dlq_name" {
  description = "SQS DLQ name (for the retries-exhausted alarm)."
  value       = aws_sqs_queue.dlq.name
}

output "dlq_arn" {
  description = "SQS DLQ ARN."
  value       = aws_sqs_queue.dlq.arn
}
