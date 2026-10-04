locals {
  common_labels = {
    managed_by = "terraform"
    purpose    = "synthetic-fleet-lab"
    issue      = "15"
  }

  review_inputs_match = (
    var.review_project_id == var.project_id &&
    var.review_zone == var.zone &&
    var.node_count <= var.reviewed_resource_ceiling
  )

  network_id   = var.retained_network_name == null ? google_compute_network.lab[0].id : data.google_compute_network.retained[0].id
  network_name = var.retained_network_name == null ? google_compute_network.lab[0].name : data.google_compute_network.retained[0].name
}

data "google_compute_network" "retained" {
  count   = var.retained_network_name == null ? 0 : 1
  project = var.project_id
  name    = var.retained_network_name
}

resource "google_compute_network" "lab" {
  count                   = var.retained_network_name == null ? 1 : 0
  project                 = var.project_id
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  description             = "Dedicated VPC for the bounded synthetic fleet lab."
}

# Preserve addresses for existing manual lab state when making the VPC
# conditional. Retained-network CI state is fresh and owns no foundation.
moved {
  from = google_compute_network.lab
  to   = google_compute_network.lab[0]
}

resource "google_compute_subnetwork" "lab" {
  project                  = var.project_id
  name                     = "${var.cluster_name}-subnet"
  region                   = replace(var.zone, "/-[a-z]$/", "")
  network                  = local.network_id
  ip_cidr_range            = "10.40.0.0/20"
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "${var.cluster_name}-pods"
    ip_cidr_range = "10.64.0.0/20"
  }

  secondary_ip_range {
    range_name    = "${var.cluster_name}-services"
    ip_cidr_range = "10.80.0.0/24"
  }
}

data "google_service_account" "nodes" {
  project    = var.project_id
  account_id = var.node_service_account_id
}

resource "google_compute_router" "lab" {
  project = var.project_id
  name    = "${var.cluster_name}-router"
  region  = replace(var.zone, "/-[a-z]$/", "")
  network = local.network_id
}

resource "google_compute_router_nat" "lab" {
  project                            = var.project_id
  name                               = "${var.cluster_name}-nat"
  router                             = google_compute_router.lab.name
  region                             = google_compute_router.lab.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.lab.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
}

resource "google_container_cluster" "lab" {
  project                  = var.project_id
  name                     = var.cluster_name
  location                 = var.zone
  network                  = local.network_id
  subnetwork               = google_compute_subnetwork.lab.id
  networking_mode          = "VPC_NATIVE"
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false
  resource_labels          = local.common_labels

  ip_allocation_policy {
    cluster_secondary_range_name  = "${var.cluster_name}-pods"
    services_secondary_range_name = "${var.cluster_name}-services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = "172.16.0.0/28"

    master_global_access_config {
      enabled = false
    }
  }

  # GKE creates this temporary default-pool node before removing the pool.
  # Keep it at the same reviewed shape and identity as the managed one-node pool.
  node_config {
    machine_type    = var.machine_type
    disk_type       = "pd-standard"
    disk_size_gb    = var.node_disk_size_gb
    image_type      = "COS_CONTAINERD"
    service_account = data.google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  control_plane_endpoints_config {
    dns_endpoint_config {
      allow_external_traffic    = true
      enable_k8s_tokens_via_dns = false
      enable_k8s_certs_via_dns  = false
    }

    ip_endpoints_config {
      enabled = false
    }
  }

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  lifecycle {
    # Once removed, the bootstrap pool is replaced by the separately managed
    # pool; GKE reports that pool's config here. Manage its settings there.
    ignore_changes = [node_config]

    precondition {
      condition     = local.review_inputs_match
      error_message = "Project, zone and node count must exactly match the reviewed inventory and quota ceiling."
    }
  }
}

resource "google_container_node_pool" "lab" {
  project        = var.project_id
  name           = "${var.cluster_name}-pool"
  location       = var.zone
  cluster        = google_container_cluster.lab.name
  node_count     = var.node_count
  node_locations = [var.zone]
  depends_on     = [google_compute_router_nat.lab]

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # A single-node lab accepts an outage during upgrades instead of a surge node.
  upgrade_settings {
    max_surge       = 0
    max_unavailable = 1
    strategy        = "SURGE"
  }

  node_config {
    machine_type    = var.machine_type
    disk_type       = "pd-standard"
    disk_size_gb    = var.node_disk_size_gb
    image_type      = "COS_CONTAINERD"
    service_account = data.google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    tags            = ["${var.cluster_name}-nodes"]
    labels          = local.common_labels
    metadata = {
      disable-legacy-endpoints = "true"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  lifecycle {
    precondition {
      condition     = var.node_count <= var.reviewed_resource_ceiling
      error_message = "Node pool count exceeds the reviewed total-node ceiling."
    }
  }
}

# In manual mode, this root preserves the existing optional PSA ownership
# shape. CI mode leaves the slow-to-delete peering and its allocated range in
# the separate foundation state because network deletion can take several days.
resource "google_compute_global_address" "cloudsql_private_service_access" {
  count         = var.cloudsql_enabled && var.retained_network_name == null ? 1 : 0
  project       = var.project_id
  name          = "${var.cluster_name}-sql-psa"
  address       = "10.96.0.0"
  address_type  = "INTERNAL"
  ip_version    = "IPV4"
  prefix_length = 24
  network       = local.network_id
  purpose       = "VPC_PEERING"
  description   = "Private service access range retained for disposable Cloud SQL lab instances."
}

resource "google_service_networking_connection" "cloudsql_private_service_access" {
  count                   = var.cloudsql_enabled && var.retained_network_name == null ? 1 : 0
  network                 = local.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.cloudsql_private_service_access[0].name]
}

resource "google_sql_database_instance" "lab" {
  count               = var.cloudsql_enabled ? 1 : 0
  project             = var.project_id
  name                = "${var.cluster_name}-postgres"
  region              = replace(var.zone, "/-[a-z]$/", "")
  database_version    = "POSTGRES_17"
  deletion_protection = false
  depends_on          = [google_service_networking_connection.cloudsql_private_service_access]

  lifecycle {
    precondition {
      condition = (
        var.cloudsql_plan_reviewed && var.cloudsql_quota_reviewed &&
        var.cloudsql_pricing_reviewed &&
        length(trimspace(var.cloudsql_inventory_reference)) >= 3 &&
        (var.database_password == null ? false : length(var.database_password) >= 32)
      )
      error_message = "Cloud SQL requires its exact resource, quota and pricing reviews, a private inventory reference, and a generated strong password."
    }
  }

  settings {
    tier                        = "db-f1-micro"
    edition                     = "ENTERPRISE"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    disk_autoresize             = false
    availability_type           = "ZONAL"
    deletion_protection_enabled = false
    user_labels                 = local.common_labels

    location_preference {
      zone = var.zone
    }

    backup_configuration {
      enabled                        = false
      point_in_time_recovery_enabled = false
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = "projects/${var.project_id}/global/networks/${local.network_name}"
      ssl_mode                                      = "ENCRYPTED_ONLY"
      enable_private_path_for_google_cloud_services = false
    }
  }
}

resource "google_sql_database" "lab" {
  count    = var.cloudsql_enabled ? 1 : 0
  project  = var.project_id
  instance = google_sql_database_instance.lab[0].name
  name     = "fleet"

  # Let the disposable instance deletion remove its children without first
  # issuing separate database/table and user drops against active sessions.
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "lab" {
  count    = var.cloudsql_enabled ? 1 : 0
  project  = var.project_id
  instance = google_sql_database_instance.lab[0].name
  name     = "fleet"
  password = var.database_password

  deletion_policy = "ABANDON"
}
