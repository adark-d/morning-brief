terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.66"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "morning-brief"
      ManagedBy = "terraform"
      Component = "tf-state-backend"
    }
  }
}
