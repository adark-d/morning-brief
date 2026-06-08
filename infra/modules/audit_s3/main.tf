# Immutable audit store: one S3 object per run, storage-enforced WORM via Object Lock.
#
# IRREVERSIBLE: object_lock_enabled can only be set at bucket creation, and COMPLIANCE-mode
# retention cannot be shortened or removed by anyone (including root) until it expires.
# The retention period is a deliberate, compliance-owned decision (var.retention_years).

resource "aws_s3_bucket" "audit" {
  bucket = var.bucket_name

  # Object Lock requires this flag at creation; it cannot be added to an existing bucket.
  object_lock_enabled = true

  lifecycle {
    prevent_destroy = true
  }

  tags = var.tags
}

# Object Lock requires versioning.
resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Default retention applied to every new object version: COMPLIANCE-mode WORM.
resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    default_retention {
      mode  = var.object_lock_mode
      years = var.retention_years
    }
  }
  depends_on = [aws_s3_bucket_versioning.audit]
}

# Encryption at rest with the customer-managed key; bucket key reduces KMS request cost.
resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket                  = aws_s3_bucket.audit.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# TLS-only access.
resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.audit.arn,
        "${aws_s3_bucket.audit.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

# Cheap long-term retention: records are written once and rarely read, so transition them
# to colder storage over time. Object Lock blocks deletion; storage-class transitions are allowed.
resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id
  rule {
    id     = "archive-audit-records"
    status = "Enabled"
    filter {
      prefix = "${var.prefix}/"
    }
    transition {
      days          = var.glacier_after_days
      storage_class = "GLACIER"
    }
    transition {
      days          = var.deep_archive_after_days
      storage_class = "DEEP_ARCHIVE"
    }
  }
}
