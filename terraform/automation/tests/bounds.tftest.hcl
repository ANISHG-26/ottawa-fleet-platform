mock_provider "google" {}

run "reviewed_automation_is_private_and_bounded" {
  command = plan

  override_data {
    target = data.google_service_account.nodes
    values = {
      name       = "projects/fleet-lab-12345/serviceAccounts/test-node-account@fleet-lab-12345.iam.gserviceaccount.com"
      email      = "test-node-account@fleet-lab-12345.iam.gserviceaccount.com"
      account_id = "test-node-account"
      project    = "fleet-lab-12345"
    }
  }

  override_resource {
    target = google_service_account.runtime["task_invoker"]
    values = {
      name       = "projects/fleet-lab-12345/serviceAccounts/fleet-lab-task-invoker@fleet-lab-12345.iam.gserviceaccount.com"
      email      = "fleet-lab-task-invoker@fleet-lab-12345.iam.gserviceaccount.com"
      account_id = "fleet-lab-task-invoker"
      project    = "fleet-lab-12345"
    }
  }

  override_resource {
    target = google_service_account.runtime["function_build"]
    values = {
      name       = "projects/fleet-lab-12345/serviceAccounts/fleet-lab-function-build@fleet-lab-12345.iam.gserviceaccount.com"
      email      = "fleet-lab-function-build@fleet-lab-12345.iam.gserviceaccount.com"
      account_id = "fleet-lab-function-build"
      project    = "fleet-lab-12345"
    }
  }

  variables {
    project_id                 = "fleet-lab-12345"
    project_number             = "123456789012"
    ci_state_bucket            = "fleet-lab-ci-private-state-12345"
    ci_state_bucket_location   = "us-central1"
    node_service_account_id    = "test-node-account"
    retained_network_name      = "fleet-lab-ci-network"
    function_source_zip_path   = "../../functions/lab_shutdown/main.py"
    function_url               = "https://fleet-lab-shutdown-abc.run.app"
    github_repository_id       = "1234567890"
    github_repository_owner_id = "9876543210"
    resource_plan_reviewed     = true
  }

  assert {
    condition = (
      google_storage_bucket.ci_state.uniform_bucket_level_access &&
      google_storage_bucket.ci_state.public_access_prevention == "enforced" &&
      google_storage_bucket.ci_state.versioning[0].enabled &&
      !google_storage_bucket.ci_state.force_destroy &&
      google_storage_bucket_iam_member.function_builder_source_read.role == "roles/storage.objectViewer" &&
      google_storage_bucket_iam_member.function_builder_source_read.condition[0].expression == "resource.name.startsWith(\"projects/_/buckets/${var.ci_state_bucket}/objects/function-sources/\")" &&
      google_storage_bucket_iam_member.runtime_bucket_access["controller"].condition[0].expression == "resource.name.startsWith(\"projects/_/buckets/${var.ci_state_bucket}/objects/gcp-lab/\")" &&
      length(google_storage_bucket_iam_member.runtime_bucket_listing) == 2 &&
      length(google_project_iam_custom_role.ci_bucket_lister.permissions) == 1 &&
      contains(google_project_iam_custom_role.ci_bucket_lister.permissions, "storage.objects.list") &&
      google_cloud_tasks_queue.expiry.rate_limits[0].max_concurrent_dispatches == 1 &&
      google_cloud_tasks_queue.expiry.rate_limits[0].max_dispatches_per_second == 1 &&
      google_cloud_tasks_queue.expiry.retry_config[0].max_attempts == 5 &&
      google_cloud_tasks_queue.expiry.retry_config[0].max_retry_duration == "86400s" &&
      google_cloudfunctions2_function.shutdown.build_config[0].runtime == "python312" &&
      google_cloudfunctions2_function.shutdown.build_config[0].entry_point == "main" &&
      google_cloudfunctions2_function.shutdown.service_config[0].available_memory == "256M" &&
      google_cloudfunctions2_function.shutdown.service_config[0].timeout_seconds == 60 &&
      google_cloudfunctions2_function.shutdown.service_config[0].min_instance_count == 0 &&
      google_cloudfunctions2_function.shutdown.service_config[0].max_instance_count == 1 &&
      google_cloudfunctions2_function.shutdown.service_config[0].max_instance_request_concurrency == 1 &&
      google_cloudfunctions2_function.shutdown.service_config[0].environment_variables["EXPECTED_RETAINED_NETWORK"] == var.retained_network_name &&
      google_cloudfunctions2_function.shutdown.service_config[0].environment_variables["CLOUD_BUILD_LOCATION"] == "us-central1" &&
      google_cloud_run_service_iam_member.task_invoker.role == "roles/run.invoker" &&
      contains(google_project_iam_custom_role.network_editor.permissions, "compute.subnetworks.delete") &&
      contains(google_project_iam_custom_role.network_editor.permissions, "compute.regionOperations.get") &&
      !contains(google_project_iam_custom_role.network_editor.permissions, "compute.networks.create") &&
      !contains(google_project_iam_custom_role.network_editor.permissions, "compute.networks.delete") &&
      contains(google_project_iam_custom_role.cleanup_inventory_reader.permissions, "compute.disks.list") &&
      contains(google_project_iam_custom_role.cleanup_inventory_reader.permissions, "compute.forwardingRules.list") &&
      google_service_account_iam_member.deploy_act_as_invoker.role == "roles/iam.serviceAccountUser" &&
      google_iam_workload_identity_pool_provider.github.oidc[0].issuer_uri == "https://token.actions.githubusercontent.com" &&
      nonsensitive(google_iam_workload_identity_pool_provider.github.attribute_condition) == "assertion.repository_id == '1234567890' && assertion.repository_owner_id == '9876543210' && assertion.repository == 'ANISHG-26/ottawa-fleet-platform' && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == 'ANISHG-26/ottawa-fleet-platform/.github/workflows/lab-deploy.yml@refs/heads/main' && assertion.sub == 'repo:ANISHG-26@9876543210/ottawa-fleet-platform@1234567890:environment:gcp-lab'"
    )
    error_message = "The reviewed automation plan must keep CI state private, serialize expiry callbacks, bound the shutdown function, grant only task identity invocation, restrict network rights, and pin GitHub federation."
  }
}
