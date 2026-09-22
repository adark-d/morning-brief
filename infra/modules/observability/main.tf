# Send run-failure, queued-failure, and missed-run alerts by email.

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email # Confirm the SNS subscription email.
}

# Alert when Lambda reports an execution error.
resource "aws_cloudwatch_metric_alarm" "run_failed" {
  alarm_name          = "${var.name_prefix}-run-failed"
  alarm_description   = "The batch Lambda reported an error (a brief run failed)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# Alert when a failed invocation reaches the queue.
resource "aws_cloudwatch_metric_alarm" "queued_failure" {
  alarm_name          = "${var.name_prefix}-dlq-not-empty"
  alarm_description   = "A scheduler delivery or Lambda execution failed; inspect the failure queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Count delivered and quiet-day runs as healthy completions.
resource "aws_cloudwatch_log_metric_filter" "brief_completed" {
  name           = "${var.name_prefix}-brief-completed"
  log_group_name = var.log_group_name
  pattern        = "{ $.event = \"run_finished\" && ($.status = \"success\" || $.status = \"skipped\") }"

  metric_transformation {
    name          = "${var.name_prefix}-BriefCompleted"
    namespace     = var.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "missed_run" {
  alarm_name          = "${var.name_prefix}-missed-run"
  alarm_description   = "No healthy completed run for ${var.missed_run_hours} consecutive hourly periods."
  namespace           = var.metric_namespace
  metric_name         = aws_cloudwatch_log_metric_filter.brief_completed.metric_transformation[0].name
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = var.missed_run_hours
  datapoints_to_alarm = var.missed_run_hours
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = var.schedule_enabled ? "breaching" : "notBreaching"
  actions_enabled     = var.schedule_enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
