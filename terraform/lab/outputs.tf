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
  value       = google_service_account.nodes.email
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
