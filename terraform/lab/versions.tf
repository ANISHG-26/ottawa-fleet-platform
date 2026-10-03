terraform {
  required_version = ">= 1.8.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.29.0"
    }
  }

  # The bucket is created and secured separately after its own review.
  # Supply bucket and prefix with a private backend config at init time.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  zone    = var.zone
}
