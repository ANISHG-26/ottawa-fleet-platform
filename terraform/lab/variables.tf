variable "project_id" {
  description = "Reviewed GCP project ID. Provide this only through a private tfvars file or input channel."
  type        = string
  sensitive   = true

  validation {
    condition = (
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id)) &&
      !contains(["your-project-id", "example-project", "my-project", "placeholder", "changeme"], lower(var.project_id))
    )
    error_message = "project_id must be an explicit valid GCP project ID, not a sample or placeholder."
  }
}

variable "zone" {
  description = "Reviewed single GCP zone for this zonal Standard cluster."
  type        = string

  validation {
    condition = (
      can(regex("^[a-z]+-[a-z0-9]+[1-9]-[a-z]$", var.zone)) &&
      !contains(["<zone>", "your-zone", "example-zone", "placeholder"], lower(var.zone))
    )
    error_message = "zone must be an explicit GCP zone name, not a sample or placeholder."
  }
}

variable "cluster_name" {
  description = "Reviewed, unique cluster name used to derive the dedicated VPC, subnet, and node pool names."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,22}[a-z0-9]$", var.cluster_name)) && !contains(["example", "placeholder", "changeme"], lower(var.cluster_name))
    error_message = "cluster_name must be an explicit GKE name short enough for derived service-account and node-pool names."
  }
}

variable "node_service_account_id" {
  description = "ID of the separately managed node service account, already granted roles/container.defaultNodeServiceAccount."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.node_service_account_id))
    error_message = "node_service_account_id must identify the pre-created lab node service account."
  }
}

variable "machine_type" {
  description = "Fixed first-lab CPU-only machine type; this hypothesis will be compared with observed cloud resource use."
  type        = string

  validation {
    condition     = var.machine_type == "e2-standard-2"
    error_message = "The initial GCP lab uses one e2-standard-2 node."
  }
}

variable "node_count" {
  description = "Exact number of nodes in the single zonal pool; autoscaling is not configured."
  type        = number

  validation {
    condition     = var.node_count == 1
    error_message = "The initial GCP lab uses exactly one node."
  }
}

variable "node_disk_size_gb" {
  description = "Per-node boot disk size in GiB, selected in the reviewed inventory."
  type        = number

  validation {
    condition     = var.node_disk_size_gb == 30
    error_message = "The initial GCP lab uses a 30 GiB node boot disk."
  }
}

variable "resource_plan_reviewed" {
  description = "Must be true only after the exact project, zone, resource inventory, quotas, pricing and teardown owner/deadline are reviewed."
  type        = bool
  default     = false

  validation {
    condition     = var.resource_plan_reviewed
    error_message = "Terraform planning is gated until a human has reviewed the concrete resource plan."
  }
}

variable "review_project_id" {
  description = "Project ID copied from the private reviewed inventory; must match project_id."
  type        = string
  sensitive   = true
}

variable "review_zone" {
  description = "Zone copied from the private reviewed inventory; must match zone."
  type        = string
}

variable "inventory_reference" {
  description = "Private inventory record identifier. Do not place account notes or credentials in Git."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.inventory_reference)) >= 3 && !contains(["todo", "pending", "placeholder"], lower(trimspace(var.inventory_reference)))
    error_message = "inventory_reference must identify a completed private resource inventory."
  }
}

variable "quota_reviewed" {
  description = "Explicit confirmation that current API enablement and relevant quotas were checked for this project and zone."
  type        = bool
  default     = false

  validation {
    condition     = var.quota_reviewed
    error_message = "Planning is gated until current project/API/quota evidence has been reviewed."
  }
}

variable "pricing_reviewed" {
  description = "Explicit confirmation that current pricing was estimated from the reviewed resource inventory."
  type        = bool
  default     = false

  validation {
    condition     = var.pricing_reviewed
    error_message = "Planning is gated until current pricing has been reviewed for the exact inventory."
  }
}

variable "workload_sizing_reference" {
  description = "Private reference to the reviewed initial unmeasured resource sizing hypothesis; the first cloud run will collect the baseline."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.workload_sizing_reference)) >= 3 && !contains(["todo", "pending", "placeholder"], lower(trimspace(var.workload_sizing_reference)))
    error_message = "workload_sizing_reference must identify the reviewed unmeasured sizing hypothesis."
  }
}

variable "workload_sizing_reviewed" {
  description = "Must be true only after a human reviewed the initial unmeasured resource sizing hypothesis for this first cloud run."
  type        = bool
  default     = false

  validation {
    condition     = var.workload_sizing_reviewed
    error_message = "Planning is gated until the initial unmeasured workload sizing hypothesis has been reviewed."
  }
}

variable "teardown_deadline" {
  description = "Reviewed ISO-8601 UTC deadline by which the lab owner will verify teardown."
  type        = string

  validation {
    condition     = endswith(var.teardown_deadline, "Z") && can(formatdate("YYYY-MM-DD'T'hh:mm:ss'Z'", var.teardown_deadline))
    error_message = "teardown_deadline must be a valid UTC timestamp in ISO-8601 form."
  }
}

variable "teardown_owner_reference" {
  description = "Private reference to the named human who owns teardown verification for this session."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.teardown_owner_reference)) >= 3 && !contains(["todo", "pending", "placeholder"], lower(trimspace(var.teardown_owner_reference)))
    error_message = "teardown_owner_reference must identify the human teardown owner in the private review record."
  }
}

variable "inventory_matches_review" {
  description = "Explicit confirmation that count, machine type, disk size and names match the reviewed inventory."
  type        = bool
  default     = false

  validation {
    condition     = var.inventory_matches_review
    error_message = "Planning is gated until the configured resource shape matches the reviewed inventory."
  }
}

variable "reviewed_resource_ceiling" {
  description = "Maximum total nodes allowed by the reviewed quota/pricing ceiling for this first run."
  type        = number

  validation {
    condition     = var.reviewed_resource_ceiling == 1
    error_message = "The initial GCP lab node ceiling is one."
  }
}

variable "ceiling_matches_review" {
  description = "Explicit confirmation that reviewed_resource_ceiling is copied from the reviewed quota and pricing evidence."
  type        = bool
  default     = false

  validation {
    condition     = var.ceiling_matches_review
    error_message = "Planning is gated until the selected node ceiling matches reviewed quota and pricing evidence."
  }
}

variable "project_zone_match_reviewed" {
  description = "Explicit confirmation that project_id and zone were checked against the reviewed inventory."
  type        = bool
  default     = false

  validation {
    condition     = var.project_zone_match_reviewed
    error_message = "Planning is gated until project and zone match the reviewed inventory."
  }
}

variable "cloudsql_enabled" {
  description = "Creates the optional privately connected PostgreSQL instance only when its separate reviewed database plan is enabled."
  type        = bool
  default     = false
}

variable "cloudsql_plan_reviewed" {
  description = "Must be true after reviewing the exact Cloud SQL tier, storage, private connectivity and deletion impact."
  type        = bool
  default     = false
}

variable "cloudsql_quota_reviewed" {
  description = "Must be true after checking the current Cloud SQL and private service access quotas for the selected project and region."
  type        = bool
  default     = false
}

variable "cloudsql_pricing_reviewed" {
  description = "Must be true after reviewing the current cost estimate for the exact disposable Cloud SQL resources."
  type        = bool
  default     = false
}

variable "cloudsql_inventory_reference" {
  description = "Private reference to the Cloud SQL inventory, including its retained private-service-access network dependency."
  type        = string
  sensitive   = true
  default     = ""
}

variable "database_password" {
  description = "Generated high-entropy password for the disposable PostgreSQL user; keep the tfvars and Terraform state private."
  type        = string
  sensitive   = true
  default     = null
  nullable    = true

  validation {
    condition     = var.database_password == null ? true : length(var.database_password) >= 32
    error_message = "A supplied Cloud SQL password must contain at least 32 characters."
  }
}
