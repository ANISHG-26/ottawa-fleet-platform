# Ottawa Fleet Platform

The platform team's repository for operating a small mock Ottawa fleet application. Learning goals: application delivery, Kubernetes, GitOps, scaling, service traffic, observability and eventually AI-assisted operations.

**Status as of October 3, 2026:** local acceptance, immutable promotion,
cluster bootstrap, bounded GCP infrastructure, LGTM telemetry and reviewer
credential tooling are implemented. A manual GCP review run has exercised the
application, Argo CD, Grafana and telemetry; its account-specific evidence stays
private. The on-demand CI lifecycle is merged and passes offline checks, but
live provisioning and independent expiry/teardown acceptance remain open under
[issue #26](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/26).

The application has a published image build and packaged chart from
[tag v0.1.0](https://github.com/ANISHG-26/ottawa-fleet-app/tree/v0.1.0) and
[trusted build 37131621545](https://github.com/ANISHG-26/ottawa-fleet-app/actions/runs/37131621545).
Full local workload acceptance, repeatable promotion/drift/rollback and exact
cloud teardown remain separate evidence gates. KEDA, Istio, Backstage and AI
SRE are future work. See the [delivery status](docs/project-management.md#current-delivery-and-review).

## Two repositories, one program

| Logical team | Repository | Owns |
|---|---|---|
| Application | [ottawa-fleet-app](https://github.com/ANISHG-26/ottawa-fleet-app) | Go APIs/workers, UI, contracts, migrations, Dockerfiles, Compose, application Helm chart and releases |
| Platform | This repository | Cluster bootstrap, environment values/release pins, Argo CD, KEDA, Istio, Terraform, observability, runbooks and later Backstage/AI SRE |

Both use the [shared project board](https://github.com/users/ANISHG-26/projects/6). Teams are responsibility boundaries for a solo learning project, not claims of staffed organizational teams.

Phase 1 builds and validates the application locally. Kubernetes/GitOps follow in Phase 2; KEDA and Istio in Phase 3; Backstage and AI SRE in Phase 4. Inference hosting is a separate future project. Cloud access is not a prerequisite for local work.

## Start here

- [Architecture and ownership](docs/architecture.md)
- [Delivery workflow and ticket map](docs/project-management.md)
- [Application release contract](docs/application-release-contract.md)
- [Roadmap and exit criteria](docs/roadmap.md)
- [Current ADR](docs/adr/0002-two-repository-local-first-platform.md)
- [Lab lifecycle](docs/runbooks/lab-lifecycle.md)
- [Local workload acceptance](docs/runbooks/local-acceptance.md)
- [On-demand CI lab and expiry](docs/runbooks/on-demand-ci.md)
- [Telemetry setup](docs/runbooks/telemetry.md)
- [Reviewer credential lifecycle](docs/runbooks/lab-credentials.md)
- [Tooling ownership and validation map](docs/tooling-map.md)
- [Future AI boundary](docs/ai-stack.md)
- [Contributing](CONTRIBUTING.md)

## Layout

```text
bootstrap/     # kind plans, Argo bootstrap and GCP review gateway
gitops/        # Argo AppProject and immutable promotion inputs
observability/ # Local Compose and bounded Kubernetes LGTM configuration
controllers/   # Boundaries for future KEDA, Istio and Backstage integrations
terraform/     # Disposable lab, retained network, automation and access roots
functions/     # Authenticated expiry dispatcher for exact CI run cleanup
tests/         # Offline platform contracts and provider-mocked bounds checks
scripts/       # Acceptance, promotion, bootstrap and CI/cleanup tooling
docs/          # Architecture, ADRs, ownership, experiments and runbooks
.github/       # Repository/runtime checks and main-only lab dispatch
```

Application source, Docker/Compose packaging and Helm templates live in the
application repository. Platform tooling and environment configuration live here.

## Validate locally

```sh
python scripts/check_repository.py
python -m unittest discover -s tests -v
```

The repository check validates required files, local Markdown links and JSON.
The offline suite checks acceptance, release pins, bootstrap, expiry and cleanup
contracts. Terraform tests need initialized providers and otherwise report an
explicit skip. See [validation entrypoints](docs/tooling-map.md#validation-entrypoints)
for the additional provider and runtime checks used by CI. Passing these checks
does not prove a live rollout or teardown. Keep private deliberations, account
identifiers and credentials outside both public checkouts.
