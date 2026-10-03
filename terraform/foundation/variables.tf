variable "project_id" {
  description = "Private reviewed GCP project ID for the retained CI network foundation."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id)) && !contains(["your-project-id", "example-project", "my-project", "placeholder", "changeme"], lower(var.project_id))
    error_message = "project_id must be an explicit valid GCP project ID, not a sample or placeholder."
  }
}

variable "network_name" {
  description = "Reviewed dedicated CI VPC name retained across disposable runs."
  type        = string

  validation {
    condition     = can(regex("^[a-z]([-a-z0-9]*[a-z0-9])?$", var.network_name))
    error_message = "network_name must be a valid GCP VPC name."
  }
}

variable "review_project_id" {
  description = "Private review record project ID, required to equal project_id."
  type        = string
  sensitive   = true
}

variable "review_network_name" {
  description = "Private review record network name, required to equal network_name."
  type        = string
}

variable "inventory_reference" {
  description = "Private inventory/review record reference. Do not put account notes in Git."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.inventory_reference)) >= 3 && !contains(["todo", "pending", "placeholder"], lower(trimspace(var.inventory_reference)))
    error_message = "inventory_reference must identify a completed private foundation review."
  }
}

variable "network_plan_reviewed" {
  description = "Must be true only after reviewing the exact project, VPC, fixed CIDRs, retained PSA and teardown ownership."
  type        = bool
  default     = false

  validation {
    condition     = var.network_plan_reviewed
    error_message = "Foundation planning is gated until a human reviews its exact retained network plan."
  }
}
