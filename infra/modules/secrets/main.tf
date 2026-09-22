# Create placeholders; set real secret values in SSM.

locals {
  path = var.path_prefix
}

resource "aws_ssm_parameter" "secret" {
  for_each = toset(var.secret_names)

  name   = "${local.path}/${each.value}"
  type   = "SecureString"
  key_id = var.kms_key_id
  value  = "PLACEHOLDER_SET_OUT_OF_BAND"

  # Prevent value overwrites; decrypted secrets can still enter Terraform state.
  lifecycle {
    ignore_changes = [value]
  }
}
