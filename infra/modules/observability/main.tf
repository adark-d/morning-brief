# Alerting for the batch path. One SNS topic fans out to email + Slack; three alarms
# cover the ways a daily brief can go wrong: it ran and failed, the scheduler gave up,
# or no successful run happened at all.

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
  # Not SSE-encrypted: alert payloads carry only alarm metadata + run status (no secrets
  # or PII). Encrypting with a CMK would require granting cloudwatch.amazonaws.com use of
  # the key in its policy; deferred as it buys nothing for non-sensitive alert content.
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email # confirmation email must be accepted once, out of band
}

# ---- Alarm A: a run executed but failed (Lambda surfaced an error) ----
resource "aws_cloudwatch_metric_alarm" "run_failed" {
  alarm_name          = "${var.name_prefix}-run-failed"
  alarm_description   = "The batch Lambda reported an error (a brief run failed)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = var.function_name }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  tags                = var.tags
}

# ---- Alarm B: the scheduler exhausted retries and dead-lettered the invocation ----
resource "aws_cloudwatch_metric_alarm" "retries_exhausted" {
  alarm_name          = "${var.name_prefix}-dlq-not-empty"
  alarm_description   = "A scheduled invocation landed in the DLQ (retries exhausted)."
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
  tags                = var.tags
}

# ---- Alarm C: no successful run at all (schedule disabled, never fired, etc.) ----
# A metric filter counts the orchestrator's success log line; the alarm fires when a
# day passes with zero successes. Matches the JSON event emitted on a successful run.
resource "aws_cloudwatch_log_metric_filter" "brief_success" {
  name           = "${var.name_prefix}-brief-success"
  log_group_name = var.log_group_name
  pattern        = "{ $.event = \"run_finished\" && $.status = \"success\" }"

  metric_transformation {
    name          = "BriefSuccess"
    namespace     = var.metric_namespace
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "missed_run" {
  alarm_name          = "${var.name_prefix}-missed-run"
  alarm_description   = "No successful brief in the last 24h (missed or persistently failing run)."
  namespace           = var.metric_namespace
  metric_name         = aws_cloudwatch_log_metric_filter.brief_success.metric_transformation[0].name
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching" # no data points = no success = alarm
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = var.tags
}

# ---- Slack (optional): SNS -> AWS Chatbot -> Slack channel ----
# Requires a one-time Slack-workspace authorization in the AWS Chatbot console (which
# yields the team/workspace id); the channel + workspace ids are then supplied as vars.
data "aws_iam_policy_document" "chatbot_assume" {
  count = var.slack_channel_id == "" ? 0 : 1
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["chatbot.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "chatbot" {
  count              = var.slack_channel_id == "" ? 0 : 1
  name               = "${var.name_prefix}-chatbot"
  assume_role_policy = data.aws_iam_policy_document.chatbot_assume[0].json
  tags               = var.tags
}

resource "aws_chatbot_slack_channel_configuration" "alerts" {
  count              = var.slack_channel_id == "" ? 0 : 1
  configuration_name = "${var.name_prefix}-alerts"
  iam_role_arn       = aws_iam_role.chatbot[0].arn
  slack_channel_id   = var.slack_channel_id
  slack_team_id      = var.slack_team_id
  sns_topic_arns     = [aws_sns_topic.alerts.arn]
  # Read-only guardrail: Chatbot can surface but never mutate resources from Slack.
  guardrail_policy_arns = ["arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"]
  tags                  = var.tags
}
