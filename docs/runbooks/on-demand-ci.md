# On-demand CI lab

The workflow dispatches a new disposable run; it never adopts the held manual review lab. Activation requires a reviewed retained foundation, automation identities and an authenticated shutdown function. Code and offline checks do not establish a successful live provisioning or teardown test.

Tracked in [issue 26](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/26), related to the bounded GCP lab and GitOps outcomes.

## Remote state and ownership

Terraform uses private Google Cloud Storage objects (blobs), rather than Git or a runner-local state file. The GCS backend provides native state locking. Enable bucket versioning for state recovery, uniform bucket access and public access prevention. Terraform state and input files can contain the database password and must never become public Actions artifacts.

Keep foundation and automation state in separate prefixes under the operator's private backend. Keep CI run state in a separate private bucket, with `gcp-lab/runs/<GitHubRunID>` as the backend prefix. CI identities have no grants on the manual state bucket. The retained foundation owns the VPC/PSA peering; each run owns its subnet, NAT/router, GKE and Cloud SQL resources. Private Services Access producer cleanup can delay network deletion for days, so per-run teardown must not attempt to destroy that foundation.

Fixed subnet ranges allow only one live CI lab in this VPC. A conditional-create GCS active-run lease spans the full lab lifetime; Actions concurrency alone is insufficient because provisioning finishes before the two-hour expiry. Release the lease only after successful exact-run teardown verification. An interrupted runner before expiry registration can leave a lease with no paid resources; an operator must inspect its exact run inventory before clearing it. Never delete an unverified lease to force another deployment.

Separate state does not establish complete IAM isolation: the initial deployment and cleanup identities have project-wide GKE/Cloud SQL administration, and subnet/router permissions are also project-wide. They can affect other project resources despite the reviewed code's exact selectors. Owner review must accept this authority or choose stronger isolation before activation. Storage object data permissions remain limited to CI run prefixes. Before function deployment, a conditional project IAM binding grants the function builder object-view access only to the `fleet-lab-shutdown/` copied-source prefix in the regional Cloud Run functions staging bucket; this can be installed before Google creates that bucket.

## GitHub settings and log privacy

Use the `gcp-lab` environment for all cloud settings. Store `GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SERVICE_ACCOUNT`, `LAB_STATE_BUCKET`, `LAB_SHUTDOWN_URL`, `LAB_TASK_INVOKER_SERVICE_ACCOUNT`, `LAB_TASK_QUEUE`, `LAB_TASK_LOCATION` and `LAB_TFVARS_JSON` as environment secrets so step headers and action inputs mask their values. Variables are configuration storage and are not automatically masked. Register masks for string fields extracted from the JSON input and the federation project number before cloud authentication; masking a JSON document alone does not reliably cover its individual fields. Never echo credentials or upload runner credential files.

Failed Terraform commands and cluster bootstrap save bounded diagnostic output (at most 256 KiB) under the exact run's private `diagnostics/` prefix in the state bucket. Public logs report only stage, exit status and whether the diagnostic was saved. These files may contain private configuration and provider output; read them privately, never copy them to Actions artifacts or issue comments. Diagnostic upload failures preserve the original command failure.

The custom network role includes `compute.networks.updatePolicy` to attach run subnets and routers to the retained VPC. It does not grant VPC creation, deletion or IAM-policy changes; this network attachment authority remains project-wide.

The same role includes `compute.instanceGroupManagers.list` for the pinned Google provider's GKE node-pool reads during apply and destroy refresh. This lists project managed instance groups; it does not grant their creation, update or deletion.

For public repositories, standard GitHub-hosted runners are free. GitHub Free's private-repository allowance is 2,000 runner minutes/month and 500 MB artifact storage; the included cache allowance is 10 GB/repository. Environment secrets and deployment protection rules are available on Free for public repositories, while private environments require a paid plan. GitHub permits 100 environment secrets, each at most 48 KB. These allowances do not cover Google Cloud resources. Verify current [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [environment availability](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) and [secret limits](https://docs.github.com/en/actions/reference/security/secrets) before changing repository visibility or runner type.

Main-only federation does not establish a human approval gate. Inspect the live environment's required reviewers and bypass settings, and the branch's required check contexts, rather than assuming every CI check is enforced.

## Provision and expire

1. Dispatch the main-only workflow in the reviewed `gcp-lab` environment. Authenticate through short-lived GitHub OIDC/WIF, restricted to the exact repository/owner identities, branch, workflow and environment. The subject uses GitHub's immutable `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:gcp-lab` format. Verify the active prefix with `gh api repos/ANISHG-26/ottawa-fleet-platform/actions/oidc/customization/sub` before activation; do not relax the condition to work around a format mismatch.
2. Derive the run ID and source SHA from GitHub and the deadline from the Actions run start, not the provisioning step's clock. Store immutable private run inputs and cleanup source in GCS. Acquire the run lease before mutations.
3. Register an authenticated Cloud Task for exactly start plus two hours before Terraform apply. Failure to register prevents provisioning. On provisioning failure, request immediate delivery of that same task; its durable schedule is the independent backstop.
4. Terraform initializes its unique GCS backend, plans/applies the reviewed one-node/private-SQL shape in the retained network, then bootstraps Argo using an exact DNS-endpoint kubeconfig outside the checkout. The application stage selects and verifies the latest stable application release, prepares the database Secret privately, and applies its pinned Argo Application. See the application stage below.
5. At expiry, Cloud Tasks invokes the Cloud Run function with only the run ID. The function loads and validates the stored identity and launches a run-scoped Cloud Build cleanup job. Short durable polling callbacks observe completion, reconcile duplicates and bound failed-build retries.
6. Cleanup removes any exact gateway Service before cluster deletion, destroys only the run's Terraform state, and verifies owned resources are absent. Failure retains state and the lease for repair. Successful verification permits matching-generation lease release.

The application stage is prepared with offline checks; its first automated live run remains to be tested. The earlier manual v0.2.1 deployment does not establish that this automatic stage works in a fresh lab. Monitoring installation, drift and rollback experiments remain separate. Keep any UI ingress restricted to the private reviewer `/32`.

## Automatic application stage

Each dispatch resolves the highest stable `vMAJOR.MINOR.PATCH` application tag,
at or above `v0.2.1`, once. Prereleases are excluded. The selected tag must have
a successful `release.yml` push run for its exact source commit. A missing,
unfinished or failed latest release stops deployment; the stage does not
silently substitute an older release.

The stage reads the seven public GHCR images published for that tag, verifies
their immutable digests, Linux/amd64 identity and source/version labels, and
checks the app-owned chart version at the same source commit. It uses published
registry artifacts rather than relying on time-limited Actions artifact ZIPs.
No additional personal access token or registry credential is required.

The run's private Terraform outputs and stored password prepare
`ottawa-fleet-database` in `fleet-app`. Secret values go through captured stdin,
never command arguments or public evidence. Argo receives an exact chart source
SHA and seven image digests, with simulation enabled, the 20-vehicle synthetic
profile and a green background. Later app tags are selected on the next fresh
lab dispatch; an existing lab does not follow a floating tag.

The workflow records the selected tag, source commit, trusted release run and
image digests in its Actions summary. Its readiness wait is capped at ten minutes
and the original lease, whichever ends first. It checks the migration hook,
Argo's exact synced source, five available deployments, and read-only web runtime,
fleet inventory, route and Ride readiness responses through the Kubernetes
service proxy. A passenger trip journey remains part of later live acceptance.
Failures use the existing exact-run cleanup backstop. It does not extend the
two-hour expiry or claim automatic database
rollback compatibility for future releases. UI access continues through the
documented operator port forward; this stage adds no public ingress.

The instance owns the disposable SQL database and user. Their provider deletion policy is `ABANDON`: Terraform removes those child entries from state and then deletes the instance, which removes its databases and users. This avoids separate database/user drops being blocked by active connections or table ownership. Cleanup still fails if the instance survives; abandoning the child entries does not establish successful teardown.

## Evidence required before activation is accepted

Record the GitHub run, source SHA, exact state prefix, registered task deadline, function/build identities, GKE/SQL provisioning, bootstrap health, actual cleanup completion and residual-resource inventory. Test early delivery of the exact task as a shortened-expiry exercise without changing the production two-hour rule; repeat delivery must be harmless. Verify the manual lab remains up and its state remains untouched. Do not infer cleanup from an empty console billing chart or an accepted task alone.
