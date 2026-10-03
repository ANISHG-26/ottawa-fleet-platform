terraform {
  required_version = ">= 1.8.4, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.29.0"
    }
  }

  # Initialize with the existing private state bucket and prefix=lab-access.
  # Keep this state separate from disposable lab and CI teardown states.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}
