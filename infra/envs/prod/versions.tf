terraform {
  # 1.10+ for S3-native state locking (use_lockfile).
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Partial backend: supply bucket/key/region/use_lockfile at init time, e.g.
  #   terraform init -backend-config=backend.hcl
  # (see backend.hcl.example). The state backend itself is created by infra/bootstrap.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
