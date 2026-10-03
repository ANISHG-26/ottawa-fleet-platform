# Ottawa Fleet Platform

A platform engineering lab for a fictional electric robotaxi fleet in Ottawa. During a Lansdowne event surge, distinguish available capacity from vehicles with stale telemetry, low battery or maintenance flags. An operations investigator explains incidents using recorded evidence.

**Status: documentation and repository scaffold. No application, cluster or model deployment has been implemented or benchmarked.**

## What we are building

Synthetic fleet telemetry and replay; Kubernetes deployments through Argo CD; Backstage service ownership; observability and measured recovery; a read-only AI investigator; repeatable lab setup and verified teardown.

This is a simulation, not autonomous driving software. Vehicle control and real safety decisions are outside its authority.

## Start here

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [AI stack and GPU feasibility](docs/ai-stack.md)
- [Lab lifecycle](docs/runbooks/lab-lifecycle.md)
- [Contribution workflow](CONTRIBUTING.md)
- [Code reuse inventory](docs/reuse.md)
- [Project board](https://github.com/users/ANISHG-26/projects/6)

## Proposed deployment

One GKE Standard cluster hosts fleet services, PostgreSQL, Backstage, Argo CD and compact observability. GitHub Actions builds images outside the cluster. Hosted inference is the initial option; CPU inference is a measured follow-on experiment. GPU deployment requires a separate eligibility and quota gate. Terraform is deferred.

## Repository layout

```text
apps/        # Simulator, ingestion, API/dashboard, investigator
platform/    # Backstage, Argo CD, observability
deploy/      # Helm charts and environment configuration
contracts/   # Telemetry and incident schemas
tests/       # Behavior, integration and recovery checks
scripts/     # Local checks and future lab commands
docs/        # Architecture, ADRs, evidence and runbooks
.github/     # Issue/PR templates and CI
```

These directories do not yet contain runnable services. Private deliberations and account-specific notes remain outside this Git repository.

## Validate the scaffold

```sh
python scripts/check_repository.py
```

Checks cover required docs, local Markdown links and JSON. They do not establish application correctness or cloud feasibility. Future service checks must have the same entry points locally and in CI.
