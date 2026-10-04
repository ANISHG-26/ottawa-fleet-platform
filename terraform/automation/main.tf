locals {
  labels = {
    managed_by = "terraform"
    purpose    = "fleet-lab-ci-automation"
    issue      = "15"
  }

  service_accounts = {
    deploy         = "fleet-lab-deploy"
    cleanup        = "fleet-lab-cleanup"
    controller     = "fleet-lab-controller"
    task_invoker   = "fleet-lab-task-invoker"
    function_build = "fleet-lab-function-build"
  }

  function_name                = "fleet-lab-shutdown"
  queue_name                   = "fleet-lab-expiry"
  function_url                 = coalesce(var.function_url, "https://${var.cloud_build_location}-${var.project_id}.cloudfunctions.net/${local.function_name}")
  source_hash                  = filesha256(var.function_source_zip_path)
  source_object                = "function-sources/lab-shutdown-${local.source_hash}.zip"
  function_build_source_bucket = "gcf-v2-sources-${var.project_number}-${var.cloud_build_location}"

  github_repo    = "ANISHG-26/ottawa-fleet-platform"
  workflow_ref   = "${local.github_repo}/.github/workflows/lab-deploy.yml@refs/heads/main"
  github_subject = "repo:ANISHG-26@${var.github_repository_owner_id}/ottawa-fleet-platform@${var.github_repository_id}:environment:gcp-lab"
  workload_identity_condition = join(" && ", [
    "assertion.repository_id == '${var.github_repository_id}'",
    "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
    "assertion.repository == '${local.github_repo}'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.workflow_ref == '${local.workflow_ref}'",
    "assertion.sub == '${local.github_subject}'",
  ])

  automation_services = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudtasks.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
    "sts.googleapis.com",
  ])
}

resource "google_project_service" "automation" {
  for_each                   = local.automation_services
  project                    = var.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

resource "google_storage_bucket" "ci_state" {
  project                     = var.project_id
  name                        = var.ci_state_bucket
  location                    = var.ci_state_bucket_location
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.automation]
}

resource "google_service_account" "runtime" {
  for_each     = local.service_accounts
  project      = var.project_id
  account_id   = each.value
  display_name = "Fleet lab ${replace(each.key, "_", " ")} automation identity"
  description  = "Dedicated least-privilege identity for bounded CI lab lifecycle automation."

  depends_on = [google_project_service.automation]
}

data "google_service_account" "nodes" {
  project    = var.project_id
  account_id = var.node_service_account_id
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "fleet-lab-github"
  display_name              = "Fleet lab GitHub Actions"
  description               = "Federation restricted to the reviewed main deployment workflow and environment."
  disabled                  = false

  depends_on = [google_project_service.automation]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "fleet-lab-deploy"
  display_name                       = "Fleet lab main deploy workflow"
  description                        = "GitHub OIDC trust for the exact repository, main ref, workflow and gcp-lab environment."
  attribute_condition                = local.workload_identity_condition

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.repository"          = "assertion.repository"
    "attribute.ref"                 = "assertion.ref"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  depends_on = [google_project_service.automation]
}

resource "google_service_account_iam_member" "github_deploy" {
  service_account_id = google_service_account.runtime["deploy"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_project_iam_custom_role" "network_editor" {
  project     = var.project_id
  role_id     = "fleetLabEphemeralNetworkEditor"
  title       = "Fleet lab ephemeral subnet and NAT editor"
  description = "Can manage run-scoped subnets, routers and Cloud NAT and attach them to VPCs, but cannot create/delete VPCs, PSA ranges, IAM or billing resources."
  stage       = "GA"
  permissions = [
    "compute.networks.get",
    "compute.networks.use",
    "compute.networks.updatePolicy",
    "compute.subnetworks.create",
    "compute.subnetworks.delete",
    "compute.subnetworks.get",
    "compute.subnetworks.list",
    "compute.subnetworks.update",
    "compute.subnetworks.use",
    "compute.routers.create",
    "compute.routers.delete",
    "compute.routers.get",
    "compute.routers.list",
    "compute.routers.update",
    "compute.regionOperations.get",
  ]
}

resource "google_project_iam_custom_role" "cleanup_inventory_reader" {
  project     = var.project_id
  role_id     = "fleetLabCleanupInventoryReader"
  title       = "Fleet lab cleanup inventory reader"
  description = "Can confirm that run-owned disks and forwarding rules were removed after cleanup."
  stage       = "GA"
  permissions = [
    "compute.disks.list",
    "compute.forwardingRules.list",
  ]
}

resource "google_project_iam_custom_role" "ci_bucket_lister" {
  project     = var.project_id
  role_id     = "fleetLabCiBucketLister"
  title       = "Fleet lab CI bucket object lister"
  description = "Can list object metadata in the CI state bucket for Terraform GCS backend operation."
  stage       = "GA"
  permissions = ["storage.objects.list"]
}

resource "google_project_iam_custom_role" "task_inspector" {
  project     = var.project_id
  role_id     = "fleetLabTaskInspector"
  title       = "Fleet lab task inspector"
  description = "Allows the deployment identity to inspect and execute only tasks in the dedicated expiry queue."
  stage       = "GA"
  permissions = [
    "cloudtasks.tasks.get",
    "cloudtasks.tasks.fullView",
    "cloudtasks.tasks.run",
  ]
}

resource "google_artifact_registry_repository" "function_builds" {
  project       = var.project_id
  location      = var.cloud_build_location
  repository_id = "fleet-lab-function-builds"
  description   = "Private image repository for the retained lab shutdown function."
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.automation]
}

resource "google_cloud_tasks_queue" "expiry" {
  project  = var.project_id
  location = var.tasks_location
  name     = local.queue_name

  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "86400s"
  }

  depends_on = [google_project_service.automation]
}

resource "google_storage_bucket_object" "function_source" {
  bucket       = google_storage_bucket.ci_state.name
  name         = local.source_object
  source       = var.function_source_zip_path
  content_type = "application/zip"
}

resource "google_cloudfunctions2_function" "shutdown" {
  project     = var.project_id
  name        = local.function_name
  location    = var.cloud_build_location
  description = "Validates and dispatches delayed Terraform teardown for one exact CI lab run."
  labels      = local.labels

  build_config {
    runtime           = "python312"
    entry_point       = "main"
    service_account   = "projects/-/serviceAccounts/${google_service_account.runtime["function_build"].email}"
    docker_repository = google_artifact_registry_repository.function_builds.id

    source {
      storage_source {
        bucket     = google_storage_bucket.ci_state.name
        object     = google_storage_bucket_object.function_source.name
        generation = google_storage_bucket_object.function_source.generation
      }
    }
  }

  service_config {
    service_account_email            = google_service_account.runtime["controller"].email
    available_memory                 = "256M"
    timeout_seconds                  = 60
    min_instance_count               = 0
    max_instance_count               = 1
    max_instance_request_concurrency = 1
    ingress_settings                 = "ALLOW_ALL"
    all_traffic_on_latest_revision   = true
    environment_variables = {
      PROJECT_ID                   = var.project_id
      PROJECT_NUMBER               = var.project_number
      STATE_BUCKET                 = google_storage_bucket.ci_state.name
      EXPECTED_RETAINED_NETWORK    = var.retained_network_name
      TASK_QUEUE                   = local.queue_name
      TASKS_LOCATION               = var.tasks_location
      CLOUD_BUILD_LOCATION         = var.cloud_build_location
      TASK_INVOKER_SERVICE_ACCOUNT = google_service_account.runtime["task_invoker"].email
      CLEANUP_SERVICE_ACCOUNT      = google_service_account.runtime["cleanup"].email
      FUNCTION_URL                 = local.function_url
    }
  }

  depends_on = [
    google_project_service.automation,
    google_artifact_registry_repository_iam_member.function_builder_writer,
    google_project_iam_member.function_builder_log_writer,
    google_project_iam_member.function_builder_service_usage,
    google_storage_bucket_iam_member.function_builder_source_read,
    google_project_iam_member.function_builder_copied_source_read,
    google_storage_bucket_iam_member.runtime_bucket_access,
  ]
}

resource "google_cloud_run_service_iam_member" "task_invoker" {
  project  = var.project_id
  location = var.cloud_build_location
  service  = element(split("/", google_cloudfunctions2_function.shutdown.service_config[0].service), length(split("/", google_cloudfunctions2_function.shutdown.service_config[0].service)) - 1)
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime["task_invoker"].email}"
}

# The Cloud Tasks service agent must be able to mint the OIDC token as the
# dedicated invoker identity. The HTTP service itself has no public invoker.
resource "google_service_account_iam_member" "tasks_agent_invoker" {
  service_account_id = google_service_account.runtime["task_invoker"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${var.project_number}@gcp-sa-cloudtasks.iam.gserviceaccount.com"

  depends_on = [google_project_service.automation]
}

resource "google_project_iam_member" "deploy_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_project_iam_member" "deploy_cloudsql_admin" {
  project = var.project_id
  role    = "roles/cloudsql.admin"
  member  = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_project_iam_member" "cleanup_container_admin" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "cleanup_cloudsql_admin" {
  project = var.project_id
  role    = "roles/cloudsql.admin"
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "deploy_network_editor" {
  project = var.project_id
  role    = google_project_iam_custom_role.network_editor.name
  member  = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_project_iam_member" "cleanup_network_editor" {
  project = var.project_id
  role    = google_project_iam_custom_role.network_editor.name
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "cleanup_inventory_reader" {
  project = var.project_id
  role    = google_project_iam_custom_role.cleanup_inventory_reader.name
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "deploy_service_usage" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_project_iam_member" "cleanup_service_usage" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "cleanup_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_project_iam_member" "controller_build_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.runtime["controller"].email}"
}

resource "google_project_iam_member" "controller_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime["controller"].email}"
}

resource "google_service_account_iam_member" "controller_act_as_cleanup" {
  service_account_id = google_service_account.runtime["cleanup"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["controller"].email}"
}

resource "google_service_account_iam_member" "controller_act_as_invoker" {
  service_account_id = google_service_account.runtime["task_invoker"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["controller"].email}"
}

resource "google_service_account_iam_member" "deploy_act_as_nodes" {
  service_account_id = data.google_service_account.nodes.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_service_account_iam_member" "deploy_act_as_invoker" {
  service_account_id = google_service_account.runtime["task_invoker"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_service_account_iam_member" "cleanup_act_as_nodes" {
  service_account_id = data.google_service_account.nodes.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["cleanup"].email}"
}

resource "google_storage_bucket_iam_member" "runtime_bucket_access" {
  for_each = toset(["deploy", "cleanup", "controller"])
  bucket   = google_storage_bucket.ci_state.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.runtime[each.value].email}"

  condition {
    title       = "gcp lab run objects only"
    description = "Runtime identities may manage per-run state and cleanup handoff objects only."
    expression  = "resource.name.startsWith(\"projects/_/buckets/${var.ci_state_bucket}/objects/gcp-lab/\")"
  }
}

resource "google_storage_bucket_iam_member" "runtime_bucket_listing" {
  for_each = toset(["deploy", "cleanup"])
  bucket   = google_storage_bucket.ci_state.name
  role     = google_project_iam_custom_role.ci_bucket_lister.name
  member   = "serviceAccount:${google_service_account.runtime[each.value].email}"
}

resource "google_storage_bucket_iam_member" "function_builder_source_read" {
  bucket = google_storage_bucket.ci_state.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runtime["function_build"].email}"

  condition {
    title       = "function source objects only"
    description = "The function build identity can read only versioned shutdown source archives."
    expression  = "resource.name.startsWith(\"projects/_/buckets/${var.ci_state_bucket}/objects/function-sources/\")"
  }
}

# Cloud Run functions copies the source archive into its regional managed
# staging bucket before Cloud Build retrieves it. Keep that read grant to this
# function's copied source object prefix only.
resource "google_project_iam_member" "function_builder_copied_source_read" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.runtime["function_build"].email}"

  condition {
    title       = "shutdown function copied source only"
    description = "The function build identity can read only the copied shutdown function source objects."
    expression  = "resource.name.startsWith(\"projects/_/buckets/${local.function_build_source_bucket}/objects/${local.function_name}/\")"
  }

  depends_on = [google_project_service.automation]
}

resource "google_artifact_registry_repository_iam_member" "function_builder_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.function_builds.location
  repository = google_artifact_registry_repository.function_builds.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.runtime["function_build"].email}"
}

resource "google_project_iam_member" "function_builder_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime["function_build"].email}"
}

resource "google_project_iam_member" "function_builder_service_usage" {
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.runtime["function_build"].email}"
}

resource "google_cloud_tasks_queue_iam_member" "deploy_enqueue" {
  project  = var.project_id
  location = google_cloud_tasks_queue.expiry.location
  name     = google_cloud_tasks_queue.expiry.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_cloud_tasks_queue_iam_member" "deploy_inspect" {
  project  = var.project_id
  location = google_cloud_tasks_queue.expiry.location
  name     = google_cloud_tasks_queue.expiry.name
  role     = google_project_iam_custom_role.task_inspector.name
  member   = "serviceAccount:${google_service_account.runtime["deploy"].email}"
}

resource "google_cloud_tasks_queue_iam_member" "controller_enqueue" {
  project  = var.project_id
  location = google_cloud_tasks_queue.expiry.location
  name     = google_cloud_tasks_queue.expiry.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.runtime["controller"].email}"
}

check "reviewed_automation_inputs" {
  assert {
    condition = (
      var.retained_network_name == "fleet-lab-ci-network" &&
      var.cloud_build_location == "us-central1" &&
      var.tasks_location == "us-central1"
    )
    error_message = "Automation selectors must match the reviewed retained network and regional service locations."
  }
}
