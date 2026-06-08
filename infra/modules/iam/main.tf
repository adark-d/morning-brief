# Least-privilege IAM for the batch path. Two roles:
#   - the Lambda execution role (what the function can do at runtime)
#   - the EventBridge Scheduler role (what the scheduler can do to invoke the function)
#
# Policies reference foundation ARNs directly (bucket, key) and construct the
# Lambda/DLQ/log-group ARNs from their names, so this module depends only on name
# strings from the root — never on the batch_lambda module, avoiding a dependency cycle.

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

# ---- Batch Lambda execution role ----

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
  tags               = var.tags
}

data "aws_iam_policy_document" "batch" {
  # CloudWatch Logs — only the function's own pre-created log group.
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.log_group_arn}:*"]
  }

  # Audit store — write + read + list, never delete (the store is append-only; Object
  # Lock would block deletion anyway, but least-privilege omits the permission).
  statement {
    sid       = "AuditObjects"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.audit_bucket_arn}/${var.audit_prefix}/*"]
  }
  statement {
    sid       = "AuditList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"] # list_objects_v2 + head_bucket
    resources = [var.audit_bucket_arn]
  }

  # KMS — GenerateDataKey* for SSE-KMS writes; Decrypt for reads + SSM SecureString.
  statement {
    sid       = "Kms"
    effect    = "Allow"
    actions   = ["kms:GenerateDataKey", "kms:GenerateDataKeyWithoutPlaintext", "kms:Decrypt"]
    resources = [var.kms_key_arn]
  }

  # Secrets — read the SecureString parameters under the env path at cold start.
  statement {
    sid       = "SsmSecrets"
    effect    = "Allow"
    actions   = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
    resources = [local.ssm_params_arn]
  }
}

resource "aws_iam_role_policy" "batch" {
  name   = "${var.name_prefix}-batch"
  role   = aws_iam_role.batch.id
  policy = data.aws_iam_policy_document.batch.json
}

# ---- EventBridge Scheduler role ----

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    # Scope the trust to this account to prevent the confused-deputy problem.
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
  tags               = var.tags
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
