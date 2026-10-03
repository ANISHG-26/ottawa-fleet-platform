mock_provider "google" {}

run "creates_only_protected_reviewer_containers" {
  command = plan

  variables {
    project_id             = "fleet-lab-review-12345"
    review_project_id      = "fleet-lab-review-12345"
    resource_plan_reviewed = true
  }

  assert {
    condition = (
      length(google_secret_manager_secret.reviewer) == 2 &&
      contains(keys(google_secret_manager_secret.reviewer), "fleet-lab-grafana-admin") &&
      contains(keys(google_secret_manager_secret.reviewer), "fleet-lab-argo-admin") &&
      alltrue([for secret in values(google_secret_manager_secret.reviewer) : secret.deletion_protection && length(secret.replication[0].auto) == 1 && secret.labels.purpose == "reviewer-access" && secret.labels.managed_by == "terraform"]) &&
      google_project_service.secret_manager.service == "secretmanager.googleapis.com" &&
      !google_project_service.secret_manager.disable_on_destroy &&
      terraform_data.review_gate.input
    )
    error_message = "The access root must create exactly two automatically replicated, protected reviewer containers and retain API enablement after the review gate passes."
  }
}

run "blocks_until_the_two_secret_proposal_is_reviewed" {
  command = plan

  variables {
    project_id             = "fleet-lab-review-12345"
    review_project_id      = "fleet-lab-review-12345"
    resource_plan_reviewed = false
  }

  expect_failures = [terraform_data.review_gate]
}

run "rejects_a_project_different_from_the_private_review" {
  command = plan

  variables {
    project_id             = "fleet-lab-review-12345"
    review_project_id      = "fleet-lab-other-12345"
    resource_plan_reviewed = true
  }

  expect_failures = [terraform_data.review_gate]
}
