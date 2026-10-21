# On-demand CI lab

The workflow dispatches a new disposable run; it never adopts the held manual review lab. Activation requires a reviewed retained foundation, automation identities and an authenticated shutdown function. Code and offline checks do not establish a successful live provisioning or teardown test.

Tracked in [issue 26](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/26), related to the bounded GCP lab and GitOps outcomes.

## Remote state and ownership

Terraform uses private Google Cloud Storage objects (blobs), rather than Git or a runner-local state file. The GCS backend provides native state locking. Enable bucket versioning for state recovery, uniform bucket access and public access prevention. Terraform state and input files can contain the database password and must never become public Actions artifacts.

Keep foundation and automation state in separate prefixes under the operator's private backend. Keep CI run state in a separate private bucket, with `gcp-lab/runs/<GitHubRunID>` as the backend prefix. CI identities have no grants on the manual state bucket. The retained foundation owns the VPC/PSA peering; each run owns its subnet, NAT/router, GKE and Cloud SQL resources. Private Services Access producer cleanup can delay network deletion for days, so per-run teardown must not attempt to destroy that foundation.

Fixed subnet ranges allow only one live CI lab in this VPC. A conditional-create GCS active-run lease spans the full lab lifetime; Actions concurrency alone is insufficient because provisioning finishes before the selected session expiry. Release the lease only after successful exact-run teardown verification. An interrupted runner before expiry registration can leave a lease with no paid resources; an operator must inspect its exact run inventory before clearing it. Never delete an unverified lease to force another deployment.

## Session duration and cleanup activation

In Actions, open **Bounded GCP lab**, choose **Run workflow** on `main`, and
select **2**, **4** or **6** hours under **Lab session hours**. The default is 2.
The deadline is the original Actions run start plus that duration, including
provisioning. It is written once into the cleanup request, Terraform inputs and
expiry task, and the app readiness wait respects it. Retrying the same run with
a changed duration fails its immutable lease check; it does not extend the lab.

The retained shutdown function runs a separately deployed validator. Before
activating longer sessions, update that function from this reviewed source:

1. Package `main.py`, `scripts_validator.py` and `requirements.txt` from
   `functions/lab_shutdown/` at the reviewed revision into the private source ZIP
   used by `terraform/automation` (`function_source_zip_path`). Do not reuse an older
   bundle that only accepts two-hour requests.
2. Review/apply the existing automation root's plan for the new function source
   and verify that the deployed function uses the compatible bundle. This does
   not dispatch a new lab. The validator remains compatible with existing
   two-hour requests and accepts only exact two-, four- or six-hour intervals.
3. In the repository's **gcp-lab environment variables**, set
   `LAB_CLEANUP_MAX_SESSION_HOURS` to `6`. This non-secret setting is the
   operator's activation acknowledgement, not automatic runtime discovery.
   Leave it unset or set to `2` until the function update is verified.

The workflow defaults the activation setting to 2 and rejects longer choices
before uploading inputs or provisioning resources. A value of 4 permits only
2/4-hour selections; unsupported values fail closed. Set it back to 2 before
rolling the function back to an older two-hour-only bundle.

The hosted runner still exits after provisioning; selecting six hours does not
keep a GitHub job running for six hours. Cloud resources remain until cleanup.
At the same resource shape, four/six hours schedule roughly twice/three times
the resource time of two hours. Actual usage also includes deletion and retries;
the deadline is not a hard billing cap.

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
3. Register an authenticated Cloud Task for exactly start plus the selected 2, 4 or 6 hours before Terraform apply. Failure to register prevents provisioning. On provisioning failure, request immediate delivery of that same task; its durable schedule is the independent backstop.
4. Terraform initializes its unique GCS backend, plans/applies the reviewed one-node/private-SQL shape in the retained network, then bootstraps Argo using an exact DNS-endpoint kubeconfig outside the checkout. The application stage selects and verifies the latest stable application release, prepares the database Secret privately, and applies its pinned Argo Application. See the application stage below.
5. At expiry, Cloud Tasks invokes the Cloud Run function with only the run ID. The function loads and validates the stored identity and launches a run-scoped Cloud Build cleanup job. Short durable polling callbacks observe completion, reconcile duplicates and bound failed-build retries.
6. Cleanup removes any exact gateway Service before cluster deletion, destroys only the run's Terraform state, and verifies owned resources are absent. Failure retains state and the lease for repair. Successful verification permits matching-generation lease release.

The application stage passed its first fresh automated live run on October 20,
2026; see [dated acceptance](../acceptance/automatic-application-bootstrap.md).
That historical run did not install monitoring. The automatic LGTM stage below
adds it to new provisioning; fresh live acceptance of that stage remains to be
recorded after the application release and platform changes are activated.
Drift and rollback remain separate experiments. UI access uses private forwards.

## Automatic application stage

Each dispatch resolves the highest stable `vMAJOR.MINOR.PATCH` application tag,
at or above `v0.2.2`, once. Prereleases are excluded. The selected tag must have
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
profile, a green background, and the supported `telemetry.enabled=true` and
`telemetry.otlpEndpoint=http://alloy.observability.svc.cluster.local:4318`
chart values. Older charts are rejected before unsupported settings are applied.
Later app tags are selected on the next fresh
lab dispatch; an existing lab does not follow a floating tag.

The workflow records the selected tag, source commit, trusted release run and
image digests in its Actions summary. Its readiness wait is capped at ten minutes
and the original lease, whichever ends first. It checks the migration hook,
Argo's exact synced source, five available deployments, and read-only web runtime,
fleet inventory, route and Ride readiness responses through the Kubernetes
service proxy. A passenger trip journey remains part of later live acceptance.
Failures use the existing exact-run cleanup backstop. It does not extend the
selected session expiry or claim automatic database
rollback compatibility for future releases. UI access continues through the
documented operator port forward; this stage adds no public ingress.

## Automatic LGTM stage and access

After application readiness, `scripts.ci_telemetry` applies the existing five
single-replica monitoring components through `observability/ci`. It checks live
node requests against allocatable CPU/memory, reserving 400m CPU / 1,056 MiB for
monitoring plus 50m / 64 MiB for one web rolling-update surge. Unexpected or
over-budget monitoring pods fail the preflight. It never increases node size or
count. Existing per-component resource quotas and ephemeral storage bounds apply.

The stage creates `observability/grafana-admin` with a random per-lab password
through captured stdin. It reuses an existing CI-owned Secret on retry, and
refuses an unowned or malformed credential. No retained Secret Manager IAM
permission or static password in GitHub is required. Alloy gets only the existing
namespace-scoped application pod/log access. Application trace export uses the
chart contract, without manual environment patches or Argo ignore exceptions.

All five deployments must become available. A temporary loopback-only forward
then authenticates to Grafana, verifies the three provisioned data sources,
checks all three application scrape targets are up, and requires nonempty
metrics, logs and trace query results. Read-only Fleet/Ride requests generate
fresh log and trace observations; no rides or simulation runs are created.
Pod readiness alone cannot pass this gate. All waits share an eight-minute cap
and the original lab expiry, whichever is sooner. Failure requests the same
registered exact-run cleanup task used by application failures.

Use the exact lab kubeconfig/context prepared for the application UI:

```powershell
kubectl --kubeconfig <owned-lab-kubeconfig> --context <owned-lab-context> -n observability port-forward service/grafana 13000:3000 --address=127.0.0.1
```

Open `http://127.0.0.1:13000/grafana/` and sign in as `admin`. Privately retrieve
the base64-encoded `data.password` from the exact lab's `grafana-admin` Secret
using `kubectl get secret grafana-admin -n observability -o json`; decode it
locally. Keep it out of screenshots, logs, issue bodies and commits.

The CI overlay serves HTTP with non-Secure cookies for this loopback forward;
the service stays ClusterIP and has no public ingress or anonymous login. The
manual HTTPS gateway configuration remains separate. Do not expose this overlay
through a public gateway. Grafana state, passwords and telemetry history are
ephemeral and are removed with the lab cluster.

Activation order is important: merge the app chart setting, publish and verify
its trusted `v0.2.2` (or newer) seven-image release, then merge this platform
integration. A new user-dispatched lab must verify the whole path before live
fresh-provisioning acceptance is recorded. Do not extend or replace an existing
lab merely to make this documentation claim pass.

The instance owns the disposable SQL database and user. Their provider deletion policy is `ABANDON`: Terraform removes those child entries from state and then deletes the instance, which removes its databases and users. This avoids separate database/user drops being blocked by active connections or table ownership. Cleanup still fails if the instance survives; abandoning the child entries does not establish successful teardown.

## Evidence required before activation is accepted

Record the GitHub run, source SHA, selected session hours, exact state prefix, registered task deadline, function/build identities, GKE/SQL provisioning, bootstrap health, actual cleanup completion and residual-resource inventory. Test early delivery of the exact task as a shortened-expiry exercise without changing the selected session deadline; repeat delivery must be harmless. Verify the manual lab remains up and its state remains untouched. Do not infer cleanup from an empty console billing chart or an accepted task alone.
