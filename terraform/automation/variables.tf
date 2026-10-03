variable "project_id" {
  description = "Private reviewed Google Cloud project ID."
  type        = string
  sensitive   = true
}

variable "project_number" {
  description = "Private numeric project number used to identify Google managed service agents."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{6,20}$", var.project_number))
    error_message = "project_number must be the numeric ID of the reviewed project."
  }
}

variable "ci_state_bucket" {
  description = "Private, globally unique bucket name owned by this root for per-run CI state and cleanup handoff objects."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.ci_state_bucket))
    error_message = "ci_state_bucket must be an explicit valid globally unique GCS bucket name."
  }
}

variable "ci_state_bucket_location" {
  description = "Reviewed regional location for the private per-run state bucket."
  type        = string

  validation {
    condition     = can(regex("^[a-z]+-[a-z0-9]+[1-9]$", var.ci_state_bucket_location))
    error_message = "ci_state_bucket_location must be an explicit regional location."
  }
}

variable "node_service_account_id" {
  description = "ID of the pre-existing lab node service account to which deploy and cleanup may attach."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.node_service_account_id))
    error_message = "node_service_account_id must identify the reviewed existing lab node service account."
  }
}

variable "retained_network_name" {
  description = "Private expected name of the retained VPC created by terraform/foundation."
  type        = string

  validation {
    condition     = var.retained_network_name == "fleet-lab-ci-network"
    error_message = "The automation controller is pinned to the reviewed fleet-lab-ci-network foundation."
  }
}

variable "cloud_build_location" {
  description = "Regional Cloud Build location used by the asynchronous cleanup controller."
  type        = string
  default     = "us-central1"

  validation {
    condition     = var.cloud_build_location == "us-central1"
    error_message = "The cleanup controller and CI workflow use Cloud Build in us-central1."
  }
}

variable "tasks_location" {
  description = "Regional Cloud Tasks queue location."
  type        = string
  default     = "us-central1"

  validation {
    condition     = var.tasks_location == "us-central1"
    error_message = "The cleanup controller uses Cloud Tasks in us-central1."
  }
}

variable "function_source_zip_path" {
  description = "Private local path to the reviewed Cloud Functions source ZIP containing main.py and scripts_validator.py."
  type        = string
  sensitive   = true
}

variable "function_url" {
  description = "Optional private URL override. Use the canonical Cloud Functions URL by default. If Cloud Tasks requires Google's Cloud Run URL, create the function first, read its service URI, then pass that URI on a second apply; self-referencing that URI in the initial function config would create a cycle."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true

  validation {
    condition     = var.function_url == null ? true : can(regex("^https://[^/?#]+(/[^?#]*)?$", var.function_url))
    error_message = "function_url override must be one canonical HTTPS hostname and optional path without a query or fragment."
  }
}

variable "github_repository_id" {
  description = "Private GitHub numeric repository ID used to restrict workload identity federation."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{1,20}$", var.github_repository_id))
    error_message = "github_repository_id must be numeric."
  }
}

variable "github_repository_owner_id" {
  description = "Private GitHub numeric owner ID used to restrict workload identity federation."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{1,20}$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must be numeric."
  }
}

variable "resource_plan_reviewed" {
  description = "Must be true only after reviewing this exact persistent automation, IAM and resource plan and its teardown ownership."
  type        = bool
  default     = false

  validation {
    condition     = var.resource_plan_reviewed
    error_message = "Automation planning is gated until a human has reviewed its exact persistent resources and IAM grants."
  }
}
