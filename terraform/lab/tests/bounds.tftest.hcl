mock_provider "google" {}

run "rejects_placeholder_project" {
  command = plan

  variables {
    project_id                     = "your-project-id"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["198.51.100.10/32"]
    machine_type                   = "e2-medium"
    node_count                     = 1
    node_disk_size_gb              = 30
    resource_plan_reviewed         = true
    review_project_id              = "your-project-id"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 1
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  expect_failures = [var.project_id]
}

run "rejects_node_count_above_ceiling" {
  command = plan

  variables {
    project_id                     = "fleet-lab-12345"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["198.51.100.10/32"]
    machine_type                   = "e2-medium"
    node_count                     = 3
    node_disk_size_gb              = 30
    resource_plan_reviewed         = true
    review_project_id              = "fleet-lab-12345"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 2
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  expect_failures = [var.node_count]
}

run "rejects_oversized_boot_disk" {
  command = plan

  variables {
    project_id                     = "fleet-lab-12345"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["198.51.100.10/32"]
    machine_type                   = "e2-medium"
    node_count                     = 1
    node_disk_size_gb              = 101
    resource_plan_reviewed         = true
    review_project_id              = "fleet-lab-12345"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 1
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  expect_failures = [var.node_disk_size_gb]
}

run "blocks_plan_until_review_is_complete" {
  command = plan

  variables {
    project_id                     = "fleet-lab-12345"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["198.51.100.10/32"]
    machine_type                   = "e2-medium"
    node_count                     = 1
    node_disk_size_gb              = 30
    resource_plan_reviewed         = false
    review_project_id              = "fleet-lab-12345"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 1
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  expect_failures = [var.resource_plan_reviewed]
}

run "rejects_unrestricted_control_plane_cidr" {
  command = plan

  variables {
    project_id                     = "fleet-lab-12345"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["0.0.0.0/0"]
    machine_type                   = "e2-medium"
    node_count                     = 1
    node_disk_size_gb              = 30
    resource_plan_reviewed         = true
    review_project_id              = "fleet-lab-12345"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 1
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  expect_failures = [var.authorized_master_cidrs]
}

run "accepts_reviewed_bounded_shape_without_node_autoscaling" {
  command = plan

  variables {
    project_id                     = "fleet-lab-12345"
    zone                           = "northamerica-northeast1-a"
    cluster_name                   = "fleet-lab"
    authorized_master_cidrs        = ["198.51.100.10/32"]
    machine_type                   = "e2-medium"
    node_count                     = 1
    node_disk_size_gb              = 30
    resource_plan_reviewed         = true
    review_project_id              = "fleet-lab-12345"
    review_zone                    = "northamerica-northeast1-a"
    inventory_reference            = "private-log:lab-2026-01"
    quota_reviewed                 = true
    pricing_reviewed               = true
    workload_measurement_reference = "private-log:local-baseline"
    teardown_deadline              = "2026-10-04T00:00:00Z"
    teardown_owner_reference       = "private-log:owner"
    inventory_matches_review       = true
    reviewed_resource_ceiling      = 1
    ceiling_matches_review         = true
    project_zone_match_reviewed    = true
  }

  assert {
    condition = (
      google_container_node_pool.lab.node_count == var.node_count &&
      length(google_container_node_pool.lab.autoscaling) == 0 &&
      google_container_node_pool.lab.node_config[0].machine_type == var.machine_type &&
      google_container_node_pool.lab.node_config[0].disk_size_gb == var.node_disk_size_gb &&
      google_container_cluster.lab.network == google_compute_network.lab.id &&
      google_container_cluster.lab.subnetwork == google_compute_subnetwork.lab.id
    )
    error_message = "The reviewed plan must use the dedicated VPC and subnet with exactly the selected bounded node and disk shape and no node autoscaling."
  }
}
