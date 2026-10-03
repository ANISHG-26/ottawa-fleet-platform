output "cluster_name" {
  description = "Name of the GKE Standard cluster owned by this Terraform root."
  value       = google_container_cluster.lab.name
}

output "cluster_location" {
  description = "Single zone selected in the reviewed inventory."
  value       = google_container_cluster.lab.location
}

output "node_service_account_email" {
  description = "Dedicated node identity. Workloads require separate identities and grants."
  value       = data.google_service_account.nodes.email
}

output "cloudsql_enabled" {
  description = "Whether the disposable private PostgreSQL instance was enabled for this exact lab run."
  value       = var.cloudsql_enabled
}

output "cloudsql_instance_name" {
  description = "Private PostgreSQL instance name, or null when Cloud SQL is disabled."
  value       = try(google_sql_database_instance.lab[0].name, null)
}

output "cloudsql_private_ip" {
  description = "Private-only Cloud SQL address for the in-VPC app connection, or null when disabled."
  value       = try(google_sql_database_instance.lab[0].private_ip_address, null)
}

output "cloudsql_database_name" {
  description = "Disposable PostgreSQL database name, or null when Cloud SQL is disabled."
  value       = try(google_sql_database.lab[0].name, null)
}

output "cloudsql_user_name" {
  description = "Disposable PostgreSQL application user, or null when Cloud SQL is disabled."
  value       = try(google_sql_user.lab[0].name, null)
}

output "resource_summary" {
  description = "Selected bounded compute shape for comparison with the reviewed inventory."
  value = {
    nodes               = var.node_count
    node_ceiling        = var.reviewed_resource_ceiling
    machine_type        = var.machine_type
    boot_disk_gb        = var.node_disk_size_gb
    autoscaling_enabled = false
    gpu_count           = 0
  }
}
