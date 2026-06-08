# SSM Parameter Store SecureString parameters for the runtime secrets.
#
# Terraform owns the parameter *resources* (name, type, KMS key); a human owns the
# *values*. Each parameter is created with a placeholder and `ignore_changes = [value]`
# so real secret values are set out-of-band (`aws ssm put-parameter --overwrite ...`)
# and NEVER enter Terraform state.
#
# Parameter basename == the exact MORNING_BRIEF_* env var name, so bootstrap_secrets()
# injects each by identity at Lambda cold start.

locals {
  path = "/${var.project}/${var.environment}"
}

resource "aws_ssm_parameter" "secret" {
  for_each = toset(var.secret_names)

  name   = "${local.path}/${each.value}"
  type   = "SecureString"
  key_id = var.kms_key_id
  value  = "PLACEHOLDER_SET_OUT_OF_BAND"

  lifecycle {
    ignore_changes = [value]
  }

  tags = var.tags
}
