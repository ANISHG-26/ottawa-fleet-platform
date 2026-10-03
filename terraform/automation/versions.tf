terraform {
  required_version = ">= 1.8.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.29.0"
    }
  }

  # This root is operator-managed from the existing private automation state
  # bucket. Runtime identities receive no access to this backend.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}
