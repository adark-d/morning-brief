# Shared encryption key for container images and runtime secrets.

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} container and secrets encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # Keep account administration here and grant runtime access through IAM.
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
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}"
  target_key_id = aws_kms_key.this.key_id
}
