# The scheduled-brief function: the container image on Lambda, its log group, an SQS
# dead-letter queue, and the EventBridge Scheduler that invokes it every weekday morning.

# Pre-create the log group so retention + encryption are owned by Terraform (Lambda would
# otherwise auto-create it with never-expire retention).
resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "batch" {
  function_name = var.function_name
  role          = var.role_arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.architecture]
  memory_size   = var.memory_size
  timeout       = var.timeout_seconds

  # Override the image's default CMD to the scheduled-brief handler (defensive: it is
  # already the image default, but explicit here so the function is self-describing).
  image_config {
    command = ["morning_brief.aws_handlers.run_handler"]
  }

  environment {
    variables = var.environment_variables
  }

  # The deploy pipeline rolls the function to each new image (update-function-code);
  # Terraform owns the function's configuration, not its code. Without this, every
  # apply would revert the image to the bootstrap tag in tfvars.
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.batch]
  tags       = var.tags
}

# Dead-letter queue for schedules the scheduler could not deliver after retries.
resource "aws_sqs_queue" "dlq" {
  name                      = var.dlq_name
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

# 07:00 Europe/London on weekdays. The timezone (not UTC) makes the brief land at 07:00
# local year-round, handling BST automatically.
resource "aws_scheduler_schedule" "brief" {
  name = "${var.name_prefix}-brief"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  target {
    arn      = aws_lambda_function.batch.arn
    role_arn = var.scheduler_role_arn

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}
