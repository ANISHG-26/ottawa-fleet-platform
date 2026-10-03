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

variable "authorized_master_cidrs" {
  description = "Reviewed operator CIDR ranges allowed to reach the public GKE control-plane endpoint. Use narrow, stable ranges."
  type        = list(string)

  validation {
    condition = (
      length(var.authorized_master_cidrs) > 0 &&
      length(var.authorized_master_cidrs) <= 5 &&
      alltrue([
        for cidr in var.authorized_master_cidrs : try(
          cidrnetmask(cidr) != "" && tonumber(split("/", cidr)[1]) >= 16,
          false
        )
      ])
    )
    error_message = "Provide 1 to 5 valid IPv4 control-plane CIDRs, each /16 or narrower; 0.0.0.0/0 is forbidden."
  }
}

variable "machine_type" {
  description = "Reviewed CPU-only machine type. The allowlist caps node size at two vCPUs."
  type        = string

  validation {
    condition     = contains(["e2-medium", "e2-standard-2"], var.machine_type)
    error_message = "machine_type must be e2-medium or e2-standard-2."
  }
}

variable "node_count" {
  description = "Exact number of nodes in the single zonal pool; autoscaling is not configured."
  type        = number

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 2 && floor(var.node_count) == var.node_count
    error_message = "node_count must be an integer from 1 through 2."
  }
}

variable "node_disk_size_gb" {
  description = "Per-node boot disk size in GiB, selected in the reviewed inventory."
  type        = number

  validation {
    condition     = var.node_disk_size_gb >= 30 && var.node_disk_size_gb <= 100 && floor(var.node_disk_size_gb) == var.node_disk_size_gb
    error_message = "node_disk_size_gb must be an integer from 30 through 100."
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

variable "workload_measurement_reference" {
  description = "Private reference to the accepted local workload/resource measurement for this lab size."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.workload_measurement_reference)) >= 3 && !contains(["todo", "pending", "placeholder"], lower(trimspace(var.workload_measurement_reference)))
    error_message = "workload_measurement_reference must identify accepted local workload and resource measurements."
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
  description = "Explicit confirmation that count, machine type, disk size, CIDRs and names match the reviewed inventory."
  type        = bool
  default     = false

  validation {
    condition     = var.inventory_matches_review
    error_message = "Planning is gated until the configured resource shape matches the reviewed inventory."
  }
}

variable "reviewed_resource_ceiling" {
  description = "Maximum total nodes allowed by the reviewed quota/pricing ceiling. Must equal or exceed node_count and remain at most two."
  type        = number

  validation {
    condition     = var.reviewed_resource_ceiling >= 1 && var.reviewed_resource_ceiling <= 2 && floor(var.reviewed_resource_ceiling) == var.reviewed_resource_ceiling
    error_message = "reviewed_resource_ceiling must be an integer from 1 through 2."
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
