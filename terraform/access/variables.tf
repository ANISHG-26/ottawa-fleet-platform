variable "project_id" {
  description = "Google Cloud project that owns the retained reviewer secret containers."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.project_id)) > 0 && !strcontains(lower(var.project_id), "your-project")
    error_message = "Set project_id to the actual reviewed project ID."
  }
}

variable "review_project_id" {
  description = "Sensitive project ID copied from the private two-secret proposal review."
  type        = string
  sensitive   = true

}

variable "resource_plan_reviewed" {
  description = "Set true only after the exact two-container proposal has received human approval and is recorded in the private plan."
  type        = bool
  default     = false
}
