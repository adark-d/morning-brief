# Set log retention before Lambda creates the log group.
resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "batch" {
  function_name                  = var.function_name
  role                           = var.role_arn
  package_type                   = "Image"
  image_uri                      = var.image_uri
  architectures                  = [var.architecture]
  memory_size                    = var.memory_size
  reserved_concurrent_executions = 1
  timeout                        = var.timeout_seconds

  image_config {
    command = [var.handler]
  }

  environment {
    variables = var.environment_variables
  }

  # Preserve the image deployed by GitHub Actions.
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.batch]
}

# Retain Scheduler and Lambda failures for inspection.
resource "aws_sqs_queue" "dlq" {
  name                      = var.dlq_name
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

# Application errors are not retried: SMTP acceptance can be ambiguous.
resource "aws_lambda_function_event_invoke_config" "batch" {
  function_name                = aws_lambda_function.batch.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination = aws_sqs_queue.dlq.arn
    }
  }
}

# Use local time so the weekday schedule follows daylight saving changes.
resource "aws_scheduler_schedule" "brief" {
  name  = "${var.name_prefix}-brief"
  state = var.schedule_enabled ? "ENABLED" : "DISABLED"

  depends_on = [aws_lambda_function_event_invoke_config.batch]

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  target {
    arn      = aws_lambda_function.batch.arn
    role_arn = var.scheduler_role_arn

    retry_policy {
      maximum_retry_attempts       = 0
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

# Check each expected run after its delivery window has closed.
resource "aws_scheduler_schedule" "completion_check" {
  name                         = "${var.name_prefix}-completion-check"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"
  schedule_expression          = var.completion_check_schedule
  schedule_expression_timezone = var.schedule_timezone
  depends_on                   = [aws_lambda_function_event_invoke_config.batch]

  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_lambda_function.batch.arn
    role_arn = var.scheduler_role_arn
    input    = jsonencode({ action = "check_completion" })
    retry_policy {
      maximum_retry_attempts       = 0
      maximum_event_age_in_seconds = 3600
    }
    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}
