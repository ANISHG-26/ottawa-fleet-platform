terraform {
  required_version = ">= 1.8.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.29.0"
    }
  }

  # Supply the reviewed private state bucket and prefix with backend config.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}
