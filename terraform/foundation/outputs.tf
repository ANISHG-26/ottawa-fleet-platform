output "retained_network_name" {
  description = "Dedicated CI VPC name to pass to the disposable lab Terraform root."
  value       = google_compute_network.ci.name
}

output "cloudsql_private_service_access_range_name" {
  description = "Retained PSA range name associated with the dedicated CI VPC."
  value       = google_compute_global_address.cloudsql_private_service_access.name
}
