mock_provider "google" {}

run "retained_network_mode_keeps_foundation_out_of_ephemeral_state" {
  command = plan

  override_data {
    target = data.google_compute_network.retained[0]
    values = {
      id        = "projects/fleet-lab-12345/global/networks/fleet-ci-network"
      name      = "fleet-ci-network"
      self_link = "https://www.googleapis.com/compute/v1/projects/fleet-lab-12345/global/networks/fleet-ci-network"
      project   = "fleet-lab-12345"
    }
  }

  variables {
    project_id                   = "fleet-lab-12345"
    zone                         = "us-central1-a"
    cluster_name                 = "fleet-ci-run-12345"
    node_service_account_id      = "fleet-lab-nodes"
    retained_network_name        = "fleet-ci-network"
    machine_type                 = "e2-standard-2"
    node_count                   = 1
    node_disk_size_gb            = 30
    resource_plan_reviewed       = true
    review_project_id            = "fleet-lab-12345"
    review_zone                  = "us-central1-a"
    inventory_reference          = "private-log:ci-lab-2026-01"
    quota_reviewed               = true
    pricing_reviewed             = true
    workload_sizing_reference    = "private-log:initial-sizing"
    workload_sizing_reviewed     = true
    teardown_deadline            = "2026-10-04T00:00:00Z"
    teardown_owner_reference     = "private-log:ci-owner"
    inventory_matches_review     = true
    reviewed_resource_ceiling    = 1
    ceiling_matches_review       = true
    project_zone_match_reviewed  = true
    cloudsql_enabled             = true
    cloudsql_plan_reviewed       = true
    cloudsql_quota_reviewed      = true
    cloudsql_pricing_reviewed    = true
    cloudsql_inventory_reference = "private-log:ci-cloudsql-2026-01"
    database_password            = "unit-test-only-password-with-enough-entropy"
  }

  assert {
    condition = (
      length(google_compute_network.lab) == 0 &&
      length(google_compute_global_address.cloudsql_private_service_access) == 0 &&
      length(google_service_networking_connection.cloudsql_private_service_access) == 0 &&
      google_container_cluster.lab.network == data.google_compute_network.retained[0].id &&
      google_compute_subnetwork.lab.ip_cidr_range == "10.40.0.0/20" &&
      google_compute_router.lab.name == "fleet-ci-run-12345-router" &&
      google_compute_router_nat.lab.name == "fleet-ci-run-12345-nat" &&
      google_container_cluster.lab.name == var.cluster_name &&
      google_container_node_pool.lab.node_count == 1 &&
      length(google_sql_database_instance.lab) == 1 &&
      length(google_sql_database.lab) == 1 &&
      length(google_sql_user.lab) == 1 &&
      google_sql_database_instance.lab[0].settings[0].tier == "db-f1-micro" &&
      !google_sql_database_instance.lab[0].deletion_protection
    )
    error_message = "Retained mode must use the existing VPC, create no VPC or PSA foundation, and keep SQL and cluster resources bounded in the disposable state."
  }
}

run "rejects_placeholder_project" {
  command = plan

  variables {
    project_id                  = "your-project-id"
    zone                        = "northamerica-northeast1-a"
    cluster_name                = "fleet-lab"
    node_service_account_id     = "fleet-lab-nodes"
    machine_type                = "e2-standard-2"
    node_count                  = 1
    node_disk_size_gb           = 30
    resource_plan_reviewed      = true
    review_project_id           = "your-project-id"
    review_zone                 = "northamerica-northeast1-a"
    inventory_reference         = "private-log:lab-2026-01"
    quota_reviewed              = true
    pricing_reviewed            = true
    workload_sizing_reference   = "private-log:initial-sizing"
    workload_sizing_reviewed    = true
    teardown_deadline           = "2026-10-04T00:00:00Z"
    teardown_owner_reference    = "private-log:owner"
    inventory_matches_review    = true
    reviewed_resource_ceiling   = 1
    ceiling_matches_review      = true
    project_zone_match_reviewed = true
  }

  expect_failures = [var.project_id]
}

run "rejects_node_count_above_ceiling" {
  command = plan

  variables {
    project_id                  = "fleet-lab-12345"
    zone                        = "northamerica-northeast1-a"
    cluster_name                = "fleet-lab"
    node_service_account_id     = "fleet-lab-nodes"
    machine_type                = "e2-standard-2"
    node_count                  = 3
    node_disk_size_gb           = 30
    resource_plan_reviewed      = true
    review_project_id           = "fleet-lab-12345"
    review_zone                 = "northamerica-northeast1-a"
    inventory_reference         = "private-log:lab-2026-01"
    quota_reviewed              = true
    pricing_reviewed            = true
    workload_sizing_reference   = "private-log:initial-sizing"
    workload_sizing_reviewed    = true
    teardown_deadline           = "2026-10-04T00:00:00Z"
    teardown_owner_reference    = "private-log:owner"
    inventory_matches_review    = true
    reviewed_resource_ceiling   = 1
    ceiling_matches_review      = true
    project_zone_match_reviewed = true
  }

  expect_failures = [var.node_count]
}

run "rejects_oversized_boot_disk" {
  command = plan

  variables {
    project_id                  = "fleet-lab-12345"
    zone                        = "northamerica-northeast1-a"
    cluster_name                = "fleet-lab"
    node_service_account_id     = "fleet-lab-nodes"
    machine_type                = "e2-standard-2"
    node_count                  = 1
    node_disk_size_gb           = 101
    resource_plan_reviewed      = true
    review_project_id           = "fleet-lab-12345"
    review_zone                 = "northamerica-northeast1-a"
    inventory_reference         = "private-log:lab-2026-01"
    quota_reviewed              = true
    pricing_reviewed            = true
    workload_sizing_reference   = "private-log:initial-sizing"
    workload_sizing_reviewed    = true
    teardown_deadline           = "2026-10-04T00:00:00Z"
    teardown_owner_reference    = "private-log:owner"
    inventory_matches_review    = true
    reviewed_resource_ceiling   = 1
    ceiling_matches_review      = true
    project_zone_match_reviewed = true
  }

  expect_failures = [var.node_disk_size_gb]
}

run "blocks_plan_until_review_is_complete" {
  command = plan

  variables {
    project_id                  = "fleet-lab-12345"
    zone                        = "northamerica-northeast1-a"
    cluster_name                = "fleet-lab"
    node_service_account_id     = "fleet-lab-nodes"
    machine_type                = "e2-standard-2"
    node_count                  = 1
    node_disk_size_gb           = 30
    resource_plan_reviewed      = false
    review_project_id           = "fleet-lab-12345"
    review_zone                 = "northamerica-northeast1-a"
    inventory_reference         = "private-log:lab-2026-01"
    quota_reviewed              = true
    pricing_reviewed            = true
    workload_sizing_reference   = "private-log:initial-sizing"
    workload_sizing_reviewed    = true
    teardown_deadline           = "2026-10-04T00:00:00Z"
    teardown_owner_reference    = "private-log:owner"
    inventory_matches_review    = true
    reviewed_resource_ceiling   = 1
    ceiling_matches_review      = true
    project_zone_match_reviewed = true
  }

  expect_failures = [var.resource_plan_reviewed]
}

run "accepts_reviewed_bounded_shape_without_node_autoscaling" {
  command = apply

  variables {
    project_id                  = "fleet-lab-12345"
    zone                        = "northamerica-northeast1-a"
    cluster_name                = "fleet-lab"
    node_service_account_id     = "fleet-lab-nodes"
    machine_type                = "e2-standard-2"
    node_count                  = 1
    node_disk_size_gb           = 30
    resource_plan_reviewed      = true
    review_project_id           = "fleet-lab-12345"
    review_zone                 = "northamerica-northeast1-a"
    inventory_reference         = "private-log:lab-2026-01"
    quota_reviewed              = true
    pricing_reviewed            = true
    workload_sizing_reference   = "private-log:initial-sizing"
    workload_sizing_reviewed    = true
    teardown_deadline           = "2026-10-04T00:00:00Z"
    teardown_owner_reference    = "private-log:owner"
    inventory_matches_review    = true
    reviewed_resource_ceiling   = 1
    ceiling_matches_review      = true
    project_zone_match_reviewed = true
  }

  assert {
    condition = (
      google_container_node_pool.lab.node_count == var.node_count &&
      length(google_container_node_pool.lab.autoscaling) == 0 &&
      google_container_node_pool.lab.node_config[0].machine_type == var.machine_type &&
      google_container_node_pool.lab.node_config[0].disk_size_gb == var.node_disk_size_gb &&
      google_container_cluster.lab.remove_default_node_pool &&
      google_container_cluster.lab.initial_node_count == 1 &&
      google_container_cluster.lab.network == google_compute_network.lab[0].id &&
      google_container_cluster.lab.subnetwork == google_compute_subnetwork.lab.id &&
      google_container_cluster.lab.node_config[0].machine_type == var.machine_type &&
      google_container_cluster.lab.node_config[0].disk_type == "pd-standard" &&
      google_container_cluster.lab.node_config[0].disk_size_gb == var.node_disk_size_gb &&
      google_container_cluster.lab.node_config[0].service_account == data.google_service_account.nodes.email &&
      google_container_node_pool.lab.upgrade_settings[0].max_surge == 0 &&
      google_container_node_pool.lab.upgrade_settings[0].max_unavailable == 1 &&
      google_compute_router_nat.lab.source_subnetwork_ip_ranges_to_nat == "LIST_OF_SUBNETWORKS" &&
      length(google_compute_router_nat.lab.subnetwork) == 1 &&
      google_container_cluster.lab.control_plane_endpoints_config[0].dns_endpoint_config[0].allow_external_traffic &&
      !google_container_cluster.lab.control_plane_endpoints_config[0].ip_endpoints_config[0].enabled &&
      length(google_sql_database_instance.lab) == 0
    )
    error_message = "The reviewed plan must use the dedicated VPC and subnet with exactly the selected bounded node and disk shape and no node autoscaling."
  }
}

run "accepts_reviewed_private_disposable_cloudsql" {
  command = plan

  variables {
    project_id                   = "fleet-lab-12345"
    zone                         = "us-central1-a"
    cluster_name                 = "fleet-lab-r37131621545"
    node_service_account_id      = "fleet-lab-nodes"
    machine_type                 = "e2-standard-2"
    node_count                   = 1
    node_disk_size_gb            = 30
    resource_plan_reviewed       = true
    review_project_id            = "fleet-lab-12345"
    review_zone                  = "us-central1-a"
    inventory_reference          = "private-log:lab-2026-01"
    quota_reviewed               = true
    pricing_reviewed             = true
    workload_sizing_reference    = "private-log:initial-sizing"
    workload_sizing_reviewed     = true
    teardown_deadline            = "2026-10-04T00:00:00Z"
    teardown_owner_reference     = "private-log:owner"
    inventory_matches_review     = true
    reviewed_resource_ceiling    = 1
    ceiling_matches_review       = true
    project_zone_match_reviewed  = true
    cloudsql_enabled             = true
    cloudsql_plan_reviewed       = true
    cloudsql_quota_reviewed      = true
    cloudsql_pricing_reviewed    = true
    cloudsql_inventory_reference = "private-log:cloudsql-2026-01"
    database_password            = "unit-test-only-password-with-enough-entropy"
  }

  assert {
    condition = (
      length(google_compute_global_address.cloudsql_private_service_access) == 1 &&
      google_compute_global_address.cloudsql_private_service_access[0].prefix_length == 24 &&
      length(google_service_networking_connection.cloudsql_private_service_access) == 1 &&
      google_sql_database_instance.lab[0].database_version == "POSTGRES_17" &&
      google_sql_database_instance.lab[0].settings[0].tier == "db-f1-micro" &&
      google_sql_database_instance.lab[0].settings[0].disk_size == 10 &&
      google_sql_database_instance.lab[0].settings[0].disk_type == "PD_SSD" &&
      !google_sql_database_instance.lab[0].settings[0].disk_autoresize &&
      google_sql_database_instance.lab[0].settings[0].availability_type == "ZONAL" &&
      google_sql_database_instance.lab[0].settings[0].location_preference[0].zone == var.zone &&
      !google_sql_database_instance.lab[0].settings[0].ip_configuration[0].ipv4_enabled &&
      google_sql_database_instance.lab[0].settings[0].ip_configuration[0].ssl_mode == "ENCRYPTED_ONLY" &&
      !google_sql_database_instance.lab[0].settings[0].backup_configuration[0].enabled &&
      google_sql_database.lab[0].deletion_policy == "ABANDON" &&
      google_sql_user.lab[0].deletion_policy == "ABANDON" &&
      !google_sql_database_instance.lab[0].deletion_protection &&
      !google_sql_database_instance.lab[0].settings[0].deletion_protection_enabled &&
      google_sql_user.lab[0].password == var.database_password
    )
    error_message = "Cloud SQL must match the approved bounded PostgreSQL plan and stay private, encrypted, fixed-size, and disposable."
  }
}

run "rejects_cloudsql_without_its_private_plan_review" {
  command = plan

  variables {
    project_id                   = "fleet-lab-12345"
    zone                         = "us-central1-a"
    cluster_name                 = "fleet-lab-r37131621545"
    node_service_account_id      = "fleet-lab-nodes"
    machine_type                 = "e2-standard-2"
    node_count                   = 1
    node_disk_size_gb            = 30
    resource_plan_reviewed       = true
    review_project_id            = "fleet-lab-12345"
    review_zone                  = "us-central1-a"
    inventory_reference          = "private-log:lab-2026-01"
    quota_reviewed               = true
    pricing_reviewed             = true
    workload_sizing_reference    = "private-log:initial-sizing"
    workload_sizing_reviewed     = true
    teardown_deadline            = "2026-10-04T00:00:00Z"
    teardown_owner_reference     = "private-log:owner"
    inventory_matches_review     = true
    reviewed_resource_ceiling    = 1
    ceiling_matches_review       = true
    project_zone_match_reviewed  = true
    cloudsql_enabled             = true
    cloudsql_plan_reviewed       = false
    cloudsql_quota_reviewed      = true
    cloudsql_pricing_reviewed    = true
    cloudsql_inventory_reference = "private-log:cloudsql-2026-01"
    database_password            = "unit-test-only-password-with-enough-entropy"
  }

  expect_failures = [google_sql_database_instance.lab]
}

run "rejects_cloudsql_with_null_password" {
  command = plan

  variables {
    project_id                   = "fleet-lab-12345"
    zone                         = "us-central1-a"
    cluster_name                 = "fleet-lab-r37131621545"
    node_service_account_id      = "fleet-lab-nodes"
    machine_type                 = "e2-standard-2"
    node_count                   = 1
    node_disk_size_gb            = 30
    resource_plan_reviewed       = true
    review_project_id            = "fleet-lab-12345"
    review_zone                  = "us-central1-a"
    inventory_reference          = "private-log:lab-2026-01"
    quota_reviewed               = true
    pricing_reviewed             = true
    workload_sizing_reference    = "private-log:initial-sizing"
    workload_sizing_reviewed     = true
    teardown_deadline            = "2026-10-04T00:00:00Z"
    teardown_owner_reference     = "private-log:owner"
    inventory_matches_review     = true
    reviewed_resource_ceiling    = 1
    ceiling_matches_review       = true
    project_zone_match_reviewed  = true
    cloudsql_enabled             = true
    cloudsql_plan_reviewed       = true
    cloudsql_quota_reviewed      = true
    cloudsql_pricing_reviewed    = true
    cloudsql_inventory_reference = "private-log:cloudsql-2026-01"
    database_password            = null
  }

  expect_failures = [google_sql_database_instance.lab]
}
