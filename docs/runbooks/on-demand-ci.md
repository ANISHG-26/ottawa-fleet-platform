# On-demand CI lab

The workflow dispatches a new disposable run; it never adopts the held manual review lab. Activation requires a reviewed retained foundation, automation identities and an authenticated shutdown function. Code and offline checks do not establish a successful live provisioning or teardown test.

Tracked in [issue 26](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/26), related to the bounded GCP lab and GitOps outcomes.

## Remote state and ownership

Terraform uses private Google Cloud Storage objects (blobs), rather than Git or a runner-local state file. The GCS backend provides native state locking. Enable bucket versioning for state recovery, uniform bucket access and public access prevention. Terraform state and input files can contain the database password and must never become public Actions artifacts.

Keep foundation and automation state in separate prefixes under the operator's private backend. Keep CI run state in a separate private bucket, with `gcp-lab/runs/<GitHubRunID>` as the backend prefix. CI identities have no grants on the manual state bucket. The retained foundation owns the VPC/PSA peering; each run owns its subnet, NAT/router, GKE and Cloud SQL resources. Private Services Access producer cleanup can delay network deletion for days, so per-run teardown must not attempt to destroy that foundation.

Fixed subnet ranges allow only one live CI lab in this VPC. A conditional-create GCS active-run lease spans the full lab lifetime; Actions concurrency alone is insufficient because provisioning finishes before the two-hour expiry. Release the lease only after successful exact-run teardown verification. An interrupted runner before expiry registration can leave a lease with no paid resources; an operator must inspect its exact run inventory before clearing it. Never delete an unverified lease to force another deployment.

Separate state does not establish complete IAM isolation: the initial deployment and cleanup identities have project-wide GKE/Cloud SQL administration, and subnet/router permissions are also project-wide. They can affect other project resources despite the reviewed code's exact selectors. Owner review must accept this authority or choose stronger isolation before activation. Storage object data permissions remain limited to CI run prefixes. Before function deployment, a conditional project IAM binding grants the function builder object-view access only to the `fleet-lab-shutdown/` copied-source prefix in the regional Cloud Run functions staging bucket; this can be installed before Google creates that bucket.

## Provision and expire

1. Dispatch the main-only workflow in the reviewed `gcp-lab` environment. Authenticate through short-lived GitHub OIDC/WIF, restricted to the exact repository/owner identities, branch, workflow and environment. The subject uses GitHub's immutable `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:gcp-lab` format. Verify the active prefix with `gh api repos/ANISHG-26/ottawa-fleet-platform/actions/oidc/customization/sub` before activation; do not relax the condition to work around a format mismatch.
2. Derive the run ID and source SHA from GitHub and the deadline from the Actions run start, not the provisioning step's clock. Store immutable private run inputs and cleanup source in GCS. Acquire the run lease before mutations.
3. Register an authenticated Cloud Task for exactly start plus two hours before Terraform apply. Failure to register prevents provisioning. On provisioning failure, request immediate delivery of that same task; its durable schedule is the independent backstop.
4. Terraform initializes its unique GCS backend, plans/applies the reviewed one-node/private-SQL shape in the retained network, then bootstraps Argo using an exact DNS-endpoint kubeconfig outside the checkout.
5. At expiry, Cloud Tasks invokes the Cloud Run function with only the run ID. The function loads and validates the stored identity and launches a run-scoped Cloud Build cleanup job. Short durable polling callbacks observe completion, reconcile duplicates and bound failed-build retries.
6. Cleanup removes any exact gateway Service before cluster deletion, destroys only the run's Terraform state, and verifies owned resources are absent. Failure retains state and the lease for repair. Successful verification permits matching-generation lease release.

The first workflow is infrastructure and Argo bootstrap acceptance. It does not yet deploy the complete application/monitoring release or prove end-to-end CD. Add reviewed immutable release inputs and application/telemetry checks before making that claim. Keep any UI ingress restricted to the private reviewer `/32`.

## Evidence required before activation is accepted

Record the GitHub run, source SHA, exact state prefix, registered task deadline, function/build identities, GKE/SQL provisioning, bootstrap health, actual cleanup completion and residual-resource inventory. Test early delivery of the exact task as a shortened-expiry exercise without changing the production two-hour rule; repeat delivery must be harmless. Verify the manual lab remains up and its state remains untouched. Do not infer cleanup from an empty console billing chart or an accepted task alone.
