output "ci_state_bucket" {
  description = "Private versioned bucket owned for disposable run state and cleanup handoff data."
  value       = google_storage_bucket.ci_state.name
}

output "deploy_service_account_email" {
  description = "GitHub Actions workload identity target for the reviewed deployment workflow."
  value       = google_service_account.runtime["deploy"].email
}

output "cleanup_service_account_email" {
  description = "Restricted identity used by the asynchronous Terraform cleanup build."
  value       = google_service_account.runtime["cleanup"].email
}

output "shutdown_function_url" {
  description = "Canonical function URL used by Cloud Tasks and the cleanup dispatcher."
  value       = local.function_url
  sensitive   = true
}

output "shutdown_queue_name" {
  description = "Regional queue used for delayed cleanup callbacks."
  value       = google_cloud_tasks_queue.expiry.name
}
