# Tooling ownership and validation map

This inventory records the platform source at `662ec2b` (October 3, 2026) for
[maintenance issue #28](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/28).
It describes current callers and deployment boundaries so a later simplification
proposal can be reviewed. Structural consolidation follows live lab acceptance;
this inventory changes no provisioning, expiry or cleanup behavior.

## Python entrypoints and helpers

All rows belong to Platform. Paths are relative to the repository root.

| File | Caller and purpose | Side effects and checks |
|---|---|---|
| `scripts/check_repository.py` | README/contributor command; repository CI documentation job. Checks required files, Markdown links and JSON. | Reads the checkout; does not validate runtime behavior. |
| `scripts/local_acceptance.py` | Operator following the local acceptance runbook; `test_platform_readiness.py` and `test_acceptance_outcomes.py`. Collects or validates local workload evidence. | Collector reads bounded loopback HTTP endpoints and writes an evidence report; validator reads a report. No provisioning. |
| `scripts/local_cluster.py` | Operator following bootstrap docs; also imported/called by `gcp_lab.py`. Prints kind creation/deletion plans and verifies the pinned Argo manifest. | Plans print commands. `verify-argo` downloads and writes only the checksum-verified upstream manifest. Covered by `test_platform_readiness.py`. |
| `scripts/promote_release.py` | Operator following GitOps docs. Verifies an app checkout and renders a pinned Argo Application. | Reads release inputs/Git and writes a manifest; does not reconcile Kubernetes. Covered by `test_platform_readiness.py`. |
| `scripts/gcp_lab.py` | Operator after approved GKE apply; `ci_lab.py` after pipeline apply. Bootstraps bounded Argo and the AppProject. | Runs gcloud/kubectl against an exact DNS-endpoint context with a dedicated private kubeconfig. Covered by `test_gcp_deployment_contract.py` and gateway renders. |
| `scripts/lab_cleanup.py` | Imported by `ci_lab.py` and `cleanup_execute.py`. Validates exact-run identity, builds private inputs and archives allowlisted cleanup source. | Writes private files and runs `git archive`; it has no CLI, scheduler or destroy operation. Covered by `test_gcp_deployment_contract.py` and `test_ci_lab.py`. |
| `scripts/ci_lab.py` | `.github/workflows/lab-deploy.yml` via `python3 -m scripts.ci_lab`. Owns run lease/input upload, expiry registration, Terraform apply and Argo bootstrap ordering. | Calls GitHub/GCS/Cloud Tasks and cloud CLIs with reviewed private inputs. `test_ci_lab.py` uses fakes for ordering, failure and lease checks. No app/LGTM promotion yet. |
| `scripts/cleanup_execute.py` | Cloud Build launched by the shutdown function; also imported by the cleanup smoke. Loads pinned private run inputs and destroys/verifies only that run. | Runs GCS, Terraform and cloud inventory operations; failures retain the lease. Covered by `test_cleanup_executor.py` and cleanup-image smoke. |
| `scripts/smoke_shutdown_runtime.py` | Repository CI startup smoke with the pinned function requirements installed. | Starts the real Functions Framework in-process and sends malformed input; expects HTTP 400 without cloud access. |
| `scripts/smoke_cleanup_worker.py` | Repository CI inside the immutable Cloud SDK container. | Downloads/checks the pinned Terraform archive, runs tool versions and cleanup `--help`; no cloud credentials or destroy operation. |

`scripts/__init__.py` provides the module package; it is not another command.
There are **10 maintained script modules plus that package marker**.

The function deploys a separate two-file Python bundle:

| File | Caller and responsibility | Validation |
|---|---|---|
| `functions/lab_shutdown/main.py` | Authenticated Cloud Tasks HTTP delivery. Loads the stored run identity, submits/reuses Cloud Build, polls completion, handles duplicate delivery and releases the matching lease only after successful cleanup. | `test_shutdown_function.py` uses fake APIs; startup smoke uses the real Framework. |
| `functions/lab_shutdown/scripts_validator.py` | Imported by the function bundle. Packages the cleanup-request contract without depending on the runner checkout. | Function tests exercise identity, expiry and rejection paths. Its duplicated contract must remain compatible with `scripts/lab_cleanup.py`. |

Runner/cleanup script imports use the Python standard library. Runtime command
dependencies are Git, Docker, kubectl, gcloud and Terraform where the caller
needs them. The function/startup smoke adds the three pinned direct dependencies
in `functions/lab_shutdown/requirements.txt`: Functions Framework, google-auth
and requests. Terraform roots pin the Google provider separately. See
[dependency provenance](reuse.md) before changing versions or packaging.

## Manifests and state ownership

Counts below include tracked YAML files, including Kustomization and configuration
inputs; generated upstream manifests and private overlays are excluded.

| Group | Tracked YAML files | Owner/caller and validation |
|---|---:|---|
| `bootstrap/kind.yaml`, `bootstrap/namespaces.yaml` | 2 | Local cluster/node configuration and bootstrap namespaces. `local_cluster.py` prints the local plan; GCP bootstrap applies the shared namespaces. |
| `bootstrap/gcp/argo/` | 1 | Kustomize adjustments to the verified upstream Argo install; `gcp_lab.py` applies this overlay. The upstream manifest is downloaded/generated separately and ignored by Git. Gateway rendering tests cover the overlay. |
| `bootstrap/gcp/gateway/` | 6 | Namespace, NGINX deployment/config, Service, intended NetworkPolicy and Kustomization. Operator applies a private reviewer/TLS overlay; CI provisioning does not install it. `test_gateway_kustomize.py` renders the base; policy enforcement depends on the chosen dataplane. |
| `observability/kubernetes/` | 11 | Five bounded LGTM pods, configuration generators and Alloy's separately applied app-namespace log RBAC. Operator follows the telemetry runbook. `test_lgtm_kubernetes.py` checks wiring, budgets and scratch paths. Two additional tracked inputs are `alloy.k8s.alloy` and `ottawa-fleet.json`. |
| `gitops/project.yaml` | 1 | Bootstrap applies the AppProject source/destination boundary. `promote_release.py` generates a separate app Application JSON from reviewed release inputs. The app chart owns workload/migration templates. |

The groups contain **21 tracked YAML files and two additional Kubernetes LGTM
inputs**. Local Compose telemetry additionally uses `observability/compose.telemetry.yaml`
and configuration under `observability/{alloy,loki,tempo,mimir,grafana}`. Those
local volume/configuration paths have a different lifecycle from Kubernetes
`emptyDir` telemetry storage.

The four Terraform roots are distinct state owners:

- `terraform/lab`: disposable GKE/SQL/subnet/NAT run state; can use the reviewed
  retained network for CI or a separately reviewed manual network.
- `terraform/foundation`: retained CI VPC and Private Services Access.
- `terraform/automation`: retained CI bucket, OIDC/IAM, function, queue and
  cleanup automation configuration.
- `terraform/access`: retained reviewer Secret Manager containers only; credential
  payload versions are migrated outside Terraform.

Separate state does not provide complete IAM isolation. The CI runbook documents
the initial project-wide GKE/SQL authority and the activation review boundary.
Do not fold retained roots into run teardown to reduce file count.

## Validation entrypoints

From the repository root, the basic dependency-free checks are:

```powershell
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

The top-level suite has eight test modules. The gateway suite lives outside its
discovery directory. Prepare the checksum-verified upstream Argo manifest through
[bootstrap](../bootstrap/README.md), then copy that verified file to the GCP
overlay's ignored input path, as `gcp_lab.py` does. Run the separate rendering
suite with kubectl on PATH; these commands do not contact a cluster:

```powershell
Copy-Item -LiteralPath bootstrap/argo-install-v3.5.3.yaml -Destination bootstrap/gcp/argo/argo-install-v3.5.3.yaml
python -m unittest discover -s bootstrap/gcp/gateway/tests -v
```

For each root (`lab`, `foundation`, `automation`, `access`), repository CI initializes
without a backend, checks formatting, validates, and runs provider-mocked tests.
For example, in a fresh offline-validation checkout:

```powershell
terraform -chdir=terraform/lab init -backend=false -input=false
terraform -chdir=terraform/lab fmt -check -recursive
terraform -chdir=terraform/lab validate
terraform -chdir=terraform/lab test -no-color
```

Use a separate validation checkout; do not replace a live root's private backend
configuration with this example. Runtime smoke commands and exact pinned
dependencies/container arguments are maintained in
[`repository-checks.yml`](../.github/workflows/repository-checks.yml).
[`telemetry-checks.yml`](../.github/workflows/telemetry-checks.yml) validates the
local Compose collectors/backends with pinned images. The main-only
[`lab-deploy.yml`](../.github/workflows/lab-deploy.yml) is a live provisioning
workflow and requires the reviewed private environment/activation described in
the [CI runbook](runbooks/on-demand-ci.md).

None of the offline/static/runtime smoke checks establishes cloud teardown or
full application CD acceptance. Record a real dispatch, scheduled task,
provisioning/bootstrap, early/duplicate expiry, residual inventory and lease
release before accepting issue #26.

## Simplification review boundary

The current inventory is the baseline for #28. A future proposal should compare
file counts, operator commands and dependencies before/after, then preserve the
same rendered resources and lifecycle/security tests. A proposed Helm package
would own only platform gateway/LGTM configuration; it must not duplicate the
app chart or adopt the upstream Argo controller install. Potential shared
cleanup-contract packaging must preserve the independently deployed function
bundle and allowlisted worker archive. No target file count is selected before
that proposal and live lifecycle evidence are reviewed. The baseline remains
**10 script modules, two function modules and 21 YAML inputs**. This inventory
adds one Markdown file and removes no runtime files.
