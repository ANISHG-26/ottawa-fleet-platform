# Roadmap

The [shared board](https://github.com/users/ANISHG-26/projects/6) is the current queue. Matching milestones describe the same phase, although GitHub milestone objects are repository-local. There is no invented deadline or production availability commitment.

| Phase | Outcome | Exit evidence |
|---|---|---|
| P0 - Delivery foundation | Two repos, ownership, bounded tickets and dependencies | Reviewed/merged scaffold PRs, passing checks and board audit |
| P1 - Local application | APIs, durable jobs/worker, UI, scenarios, Compose and CI | Fresh start, visible ride journey, failure/recovery and resource baseline |
| P2 - Kubernetes and GitOps | Chart/images, bootstrap/promotion, observability and rollback | Pinned deployment, drift correction, compatible rollback and teardown |
| P3 - Scaling and traffic | Separate KEDA and Istio experiments | Fixed-load comparisons, caps, traffic/failure results and cleanup |
| P4 - Developer experience and AI | Backstage, diagnosis and staged remediation | Working catalog/evidence links and separately reviewed recovery policy |

## Phase 1 sequence

1. Review foundations, then specify API/job contracts and fixtures.
2. Implement fleet and ride APIs; develop UI against fixtures and introduce service CI alongside implementation.
3. Add worker concurrency/crash recovery and the bounded scenario CLI.
4. Package the integrated app in Compose and run its browser journey.
5. Platform verifies fresh setup, worker outage/backlog/recovery, API degradation and resource use.

Application's parent outcome tracks component delivery. Platform's separate acceptance ticket validates the workload. Completion of the app epic does not establish platform acceptance.

## Cloud and AI branches

GCP feasibility follows local measurements and does not block local Kubernetes. Terraform belongs in platform after the deployment shape and cloud inventory are reviewed. No ticket authorizes a billing upgrade or unreviewed provisioning.

Inference hosting belongs in a separate future project. CPU/GPU issues retain evaluation/feasibility goals only. The fleet investigator consumes an endpoint; it does not require a model in this cluster. Remediation follows diagnosis and requires policy, verification, cooldowns and rollback.

See [project management](project-management.md) for links, readiness and ownership.
