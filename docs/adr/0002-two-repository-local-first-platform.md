# ADR 0002: Two repositories and a local mock application first

- **Status:** Accepted direction from October 3, 2026 planning; scaffolds remain in review and implementation is unverified.
- **Supersedes:** [ADR 0001](0001-platform-boundaries.md) for repo shape, application scope, cloud sequencing and AI hosting.

## Context

Supporting infrastructure is the learning objective. A small mock application supplies HTTP traffic, queued work, UI feedback and failure scenarios. Building a broad fleet telemetry system first would consume the limited implementation time.

## Decision

Keep `ottawa-fleet-platform` for operations; create `ottawa-fleet-app` for application development. One GitHub Project uses Team/Phase fields, repository-local milestones, parent outcomes and blocking dependencies. Teams express responsibilities, not staffed organizational units.

Application owns Go services/scenario tooling, UI, contracts, migrations, Docker/Compose and Helm packages. Platform owns bootstrap, environment values/version pins, GitOps, controllers, Terraform and operating evidence. Use one Go module with separate processes where scaling/failure experiments benefit.

Phase 1 is local: fleet/ride APIs, PostgreSQL-backed durable jobs, worker, UI and scenarios. Exact semantics belong in the contract ticket. Full append-only telemetry/projector infrastructure is not a Phase 1 requirement; idempotency and crash recovery remain essential.

Phase 2 adds Kubernetes/GitOps, Phase 3 KEDA/Istio, Phase 4 Backstage/AI SRE. Cloud and inference do not block local work. Model hosting is a separate future project; no third repo is created now. Initial diagnosis remains read-only; self-healing requires separate policy/approval/executor design and reviewed activation.

## Consequences and review triggers

Two release queues require a cross-repo handoff. Application packaging may require a later platform promotion PR. This makes responsibilities visible without creating a repository per service.

PostgreSQL keeps local dependencies small while making claim/lease semantics an explicit worker contract. A broker is deferred until justified by measurements or a focused experiment.

Review if measured resources cannot support the stack, job contracts prevent concurrent workers, or another experiment needs a service boundary. This ADR establishes no running app, cluster, benchmark or cloud feasibility.
