# Customer-managed KMS key for the audit bucket (SSE-KMS) and the SSM SecureString
# secrets. One key keeps the blast radius and key-policy surface small; rotation is on.

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} audit + secrets encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # Key policy: the account root retains admin (so the key is never orphaned); the
  # batch role is granted data-plane use through IAM policies, not here, to keep the
  # key policy stable as roles change.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "EnableRootAccountAdmin"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
      Action    = "kms:*"
      Resource  = "*"
    }]
  })

  tags = var.tags
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}
