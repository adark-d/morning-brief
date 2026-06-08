# Production root — wires the modules into the live batch deployment.
#
# Data flow is acyclic: kms -> {ecr, audit_s3, secrets}; iam derives ARNs from the
# names below (not from batch_lambda) so it can be created first; batch_lambda consumes
# the iam roles; observability + cicd consume batch_lambda outputs.

locals {
  name_prefix = "${var.project}-prod"
  ssm_path    = "/${var.project}/${var.environment}"

  # Names shared between iam (which constructs ARNs from them) and the resources that
  # actually create them — keep these two in lockstep.
  function_name = "${local.name_prefix}-batch"
  dlq_name      = "${local.name_prefix}-brief-dlq"

  image_uri = "${module.ecr.repository_url}:${var.image_tag}"

  # Only true secrets live in SSM; non-secret config is set as Lambda env vars below.
  secret_names = [
    "MORNING_BRIEF_LLM__ANTHROPIC_API_KEY",
    "MORNING_BRIEF_DELIVERY__EMAIL__RECIPIENTS",
    "MORNING_BRIEF_DELIVERY__EMAIL__SMTP_USERNAME",
    "MORNING_BRIEF_DELIVERY__EMAIL__SMTP_PASSWORD",
  ]

  # Non-secret runtime config. Secrets are injected from SSM at cold start and won't be
  # clobbered (bootstrap uses setdefault). Bucket/region/key point the S3 audit store at
  # the bucket this stack creates; SMTP_FROM is the verified sender.
  lambda_env = {
    MORNING_BRIEF_ENVIRONMENT                = var.environment
    MORNING_BRIEF_AUDIT__S3_BUCKET           = module.audit_s3.bucket_name
    MORNING_BRIEF_AUDIT__S3_REGION           = var.region
    MORNING_BRIEF_AUDIT__S3_KMS_KEY_ID       = module.kms.key_arn
    MORNING_BRIEF_DELIVERY__EMAIL__SMTP_FROM = var.smtp_from
  }
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = local.name_prefix
}

module "ecr" {
  source          = "../../modules/ecr"
  repository_name = var.ecr_repository_name
  kms_key_arn     = module.kms.key_arn
}

module "audit_s3" {
  source          = "../../modules/audit_s3"
  bucket_name     = var.audit_bucket_name
  kms_key_arn     = module.kms.key_arn
  retention_years = var.retention_years
}

module "secrets" {
  source       = "../../modules/secrets"
  project      = var.project
  environment  = var.environment
  secret_names = local.secret_names
  kms_key_id   = module.kms.key_id
}

module "iam" {
  source           = "../../modules/iam"
  name_prefix      = local.name_prefix
  function_name    = local.function_name
  dlq_name         = local.dlq_name
  audit_bucket_arn = module.audit_s3.bucket_arn
  kms_key_arn      = module.kms.key_arn
  ssm_path         = local.ssm_path
}

module "batch_lambda" {
  source                = "../../modules/batch_lambda"
  name_prefix           = local.name_prefix
  function_name         = local.function_name
  dlq_name              = local.dlq_name
  image_uri             = local.image_uri
  role_arn              = module.iam.batch_role_arn
  scheduler_role_arn    = module.iam.scheduler_role_arn
  environment_variables = local.lambda_env
}

module "observability" {
  source           = "../../modules/observability"
  name_prefix      = local.name_prefix
  function_name    = module.batch_lambda.function_name
  dlq_name         = module.batch_lambda.dlq_name
  log_group_name   = module.batch_lambda.log_group_name
  alert_email      = var.alert_email
  slack_channel_id = var.slack_channel_id
  slack_team_id    = var.slack_team_id
}

module "cicd" {
  source                     = "../../modules/cicd"
  name_prefix                = local.name_prefix
  github_owner               = var.github_owner
  github_repo                = var.github_repo
  create_oidc_provider       = var.create_oidc_provider
  existing_oidc_provider_arn = var.existing_oidc_provider_arn
  ecr_repository_arn         = module.ecr.repository_arn
  lambda_function_arn        = module.batch_lambda.function_arn
}
