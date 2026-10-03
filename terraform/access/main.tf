locals {
  labels = {
    purpose    = "reviewer-access"
    managed_by = "terraform"
  }

  reviewer_secrets = toset([
    "fleet-lab-grafana-admin",
    "fleet-lab-argo-admin",
  ])
}

resource "google_project_service" "secret_manager" {
  project                    = var.project_id
  service                    = "secretmanager.googleapis.com"
  disable_on_destroy         = false
  disable_dependent_services = false

  depends_on = [terraform_data.review_gate]
}

resource "terraform_data" "review_gate" {
  input = var.resource_plan_reviewed

  lifecycle {
    precondition {
      condition     = var.resource_plan_reviewed && var.review_project_id == var.project_id
      error_message = "Set resource_plan_reviewed=true only after human approval is recorded in the private plan, and ensure its project ID matches project_id."
    }
  }
}

resource "google_secret_manager_secret" "reviewer" {
  for_each  = local.reviewer_secrets
  project   = var.project_id
  secret_id = each.value
  labels    = local.labels

  replication {
    auto {}
  }

  deletion_protection = true

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.secret_manager, terraform_data.review_gate]
}
