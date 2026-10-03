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
}

resource "google_compute_network" "lab" {
  project                 = var.project_id
  name                    = "${var.cluster_name}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  description             = "Dedicated VPC for the bounded synthetic fleet lab."
}

resource "google_compute_subnetwork" "lab" {
  project                  = var.project_id
  name                     = "${var.cluster_name}-subnet"
  region                   = replace(var.zone, "/-[a-z]$/", "")
  network                  = google_compute_network.lab.id
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

resource "google_service_account" "nodes" {
  project      = var.project_id
  account_id   = "${var.cluster_name}-nodes"
  display_name = "${var.cluster_name} GKE node identity"
  description  = "Dedicated, least-privilege node identity for the synthetic fleet lab."
}

resource "google_project_iam_member" "node_service_account" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

resource "google_container_cluster" "lab" {
  project                  = var.project_id
  name                     = var.cluster_name
  location                 = var.zone
  network                  = google_compute_network.lab.id
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
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"

    master_global_access_config {
      enabled = false
    }
  }

  master_authorized_networks_config {
    gcp_public_cidrs_access_enabled = false

    dynamic "cidr_blocks" {
      for_each = var.authorized_master_cidrs
      content {
        cidr_block   = cidr_blocks.value
        display_name = "reviewed-operator-${cidr_blocks.key + 1}"
      }
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
  depends_on     = [google_project_iam_member.node_service_account]

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = var.machine_type
    disk_type       = "pd-standard"
    disk_size_gb    = var.node_disk_size_gb
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.nodes.email
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
