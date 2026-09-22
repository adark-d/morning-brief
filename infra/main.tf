# Single deployment: scheduled Lambda, Anthropic models, and SMTP.

locals {
  name_prefix = var.project
  ssm_path    = "/morning-brief"

  # Keep resource names aligned with the ARNs constructed by IAM.
  function_name = "${local.name_prefix}-batch"
  dlq_name      = "${local.name_prefix}-brief-dlq"

  image_uri = "${module.ecr.repository_url}:${var.image_tag}"

  # Basenames match the environment variables loaded by brief_core.aws.
  secret_names = [
    "MORNING_BRIEF_ANTHROPIC_API_KEY",
    "MORNING_BRIEF_RECIPIENTS",
    "MORNING_BRIEF_SMTP_USERNAME",
    "MORNING_BRIEF_SMTP_PASSWORD",
  ]

  # Leave omitted settings to Python; encode collection overrides as JSON.
  lambda_env = merge({
    for name, value in var.brief_settings :
    "MORNING_BRIEF_${upper(name)}" => try(tostring(value), jsonencode(value))
    if value != null
    }, {
    BRIEF_COMPLETION_METRIC_NAME           = "${local.name_prefix}-BriefCompleted"
    BRIEF_COMPLETION_LOOKBACK_MINUTES      = tostring(var.completion_check_lookback_minutes)
    MORNING_BRIEF_SELECTION_MODEL          = var.selection_model
    MORNING_BRIEF_EXPLANATION_MODEL        = var.explanation_model
    MORNING_BRIEF_PIPELINE_TIMEOUT_SECONDS = tostring(var.pipeline_timeout_seconds)
    MORNING_BRIEF_SEND_EMAIL               = "true"
    MORNING_BRIEF_SENDER                   = var.sender
    MORNING_BRIEF_SMTP_HOST                = var.smtp_host
  })
}

module "kms" {
  source      = "./modules/kms"
  name_prefix = local.name_prefix
}

module "ecr" {
  source          = "./modules/ecr"
  repository_name = var.ecr_repository_name
  kms_key_arn     = module.kms.key_arn
}

module "secrets" {
  source       = "./modules/secrets"
  path_prefix  = local.ssm_path
  secret_names = local.secret_names
  kms_key_id   = module.kms.key_id
}

module "iam" {
  source        = "./modules/iam"
  name_prefix   = local.name_prefix
  function_name = local.function_name
  dlq_name      = local.dlq_name
  kms_key_arn   = module.kms.key_arn
  ssm_path      = local.ssm_path
}

module "batch_lambda" {
  source                    = "./modules/batch_lambda"
  name_prefix               = local.name_prefix
  function_name             = local.function_name
  dlq_name                  = local.dlq_name
  image_uri                 = local.image_uri
  role_arn                  = module.iam.batch_role_arn
  scheduler_role_arn        = module.iam.scheduler_role_arn
  environment_variables     = local.lambda_env
  timeout_seconds           = var.lambda_timeout_seconds
  handler                   = "ai_brief.handler.run_handler"
  schedule_expression       = var.schedule_expression
  schedule_timezone         = var.schedule_timezone
  schedule_enabled          = var.schedule_enabled
  completion_check_schedule = var.completion_check_schedule

  # IAM policies must exist before Lambda validates its failure destination.
  depends_on = [module.iam, module.secrets]
}

module "observability" {
  source           = "./modules/observability"
  name_prefix      = local.name_prefix
  function_name    = module.batch_lambda.function_name
  dlq_name         = module.batch_lambda.dlq_name
  log_group_name   = module.batch_lambda.log_group_name
  alert_email      = var.alert_email
  missed_run_hours = var.missed_run_hours
  schedule_enabled = var.schedule_enabled
}

module "cicd" {
  source                     = "./modules/cicd"
  name_prefix                = local.name_prefix
  github_owner               = var.github_owner
  github_repo                = var.github_repo
  create_oidc_provider       = var.create_oidc_provider
  existing_oidc_provider_arn = var.existing_oidc_provider_arn
  ecr_repository_arn         = module.ecr.repository_arn
  lambda_function_arn        = module.batch_lambda.function_arn
}
