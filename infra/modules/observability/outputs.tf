output "sns_topic_arn" {
  description = "ARN of the alerts SNS topic."
  value       = aws_sns_topic.alerts.arn
}
