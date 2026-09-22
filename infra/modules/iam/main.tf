# Separate roles limit Lambda runtime access and Scheduler invocation permissions.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id     = data.aws_caller_identity.current.account_id
  region         = data.aws_region.current.name
  function_arn   = "arn:aws:lambda:${local.region}:${local.account_id}:function:${var.function_name}"
  log_group_arn  = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.function_name}"
  dlq_arn        = "arn:aws:sqs:${local.region}:${local.account_id}:${var.dlq_name}"
  ssm_params_arn = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.ssm_path}/*"
}

# Lambda execution permissions.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "batch" {
  name               = "${var.name_prefix}-batch"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "batch" {
  # CloudWatch metric reads do not support resource-level permissions.
  statement {
    sid       = "CheckCompletion"
    effect    = "Allow"
    actions   = ["cloudwatch:GetMetricStatistics"]
    resources = ["*"]
  }

  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.log_group_arn}:*"]
  }

  # Allow key decryption only through SSM.
  statement {
    sid       = "Kms"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.kms_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${local.region}.amazonaws.com"]
    }
  }

  statement {
    sid       = "FailedInvocations"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [local.dlq_arn]
  }

  statement {
    sid       = "SsmSecrets"
    effect    = "Allow"
    actions   = ["ssm:GetParametersByPath"]
    resources = [local.ssm_params_arn]
  }
}

resource "aws_iam_role_policy" "batch" {
  name   = "${var.name_prefix}-batch"
  role   = aws_iam_role.batch.id
  policy = data.aws_iam_policy_document.batch.json
}

# Scheduler invocation permissions.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Only this account may use the Scheduler role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeBatch"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.function_arn]
  }
  statement {
    sid       = "SendToDlq"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [local.dlq_arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.name_prefix}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
