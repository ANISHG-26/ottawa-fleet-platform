# Ottawa Fleet Platform

The platform team's repository for operating a small mock Ottawa fleet application. Learning goals: application delivery, Kubernetes, GitOps, scaling, service traffic, observability and eventually AI-assisted operations.

**Status: planning and documentation scaffold. No cluster, controller, Terraform module or AI service has been implemented or deployed.**

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
- [Future AI boundary](docs/ai-stack.md)
- [Contributing](CONTRIBUTING.md)

## Layout

```text
bootstrap/    # Future local cluster and controller bootstrap
gitops/       # Future Argo applications, release pins and environment values
controllers/  # Future KEDA, Istio, monitoring and Backstage configuration
terraform/    # Future approved infrastructure modules/environments
tests/        # Future platform acceptance and experiment checks
scripts/      # Scaffold checks; future platform lifecycle commands
docs/         # Architecture, ADRs, ownership, experiments and runbooks
.github/      # Issue/PR templates and documentation CI
```

Operational directories currently contain boundary descriptions only. Application source and Helm templates live in the application repository.

## Validate the scaffold

```sh
python scripts/check_repository.py
```

This checks required files, local Markdown links and JSON; it is not an application/deployment test. Keep private deliberations, account identifiers and credentials outside both public checkouts.
