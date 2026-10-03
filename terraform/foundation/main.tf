locals {
  reviewed_inputs_match = (
    var.project_id == var.review_project_id &&
    var.network_name == var.review_network_name
  )
}

resource "google_compute_network" "ci" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  description             = "Retained VPC foundation for bounded, disposable CI lab runs."

  lifecycle {
    precondition {
      condition     = local.reviewed_inputs_match
      error_message = "Project and network name must exactly match the private reviewed inventory."
    }
  }
}

resource "google_compute_global_address" "cloudsql_private_service_access" {
  project       = var.project_id
  name          = "${var.network_name}-sql-psa"
  address       = "10.96.0.0"
  address_type  = "INTERNAL"
  ip_version    = "IPV4"
  prefix_length = 24
  network       = google_compute_network.ci.id
  purpose       = "VPC_PEERING"
  description   = "Retained Private Services Access range for disposable CI Cloud SQL instances."
}

resource "google_service_networking_connection" "cloudsql_private_service_access" {
  network                 = google_compute_network.ci.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.cloudsql_private_service_access.name]
}

check "reviewed_foundation_inputs" {
  assert {
    condition     = local.reviewed_inputs_match
    error_message = "Project and network name must exactly match the private reviewed inventory."
  }
}
