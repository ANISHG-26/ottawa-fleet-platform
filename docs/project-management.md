# Delivery workflow and ticket map

One program, two logical teams and one [project board](https://github.com/users/ANISHG-26/projects/6). GitHub repository ownership remains with the same human; Team describes the responsibility for the outcome.

## Board and milestones

Filter `Team` to Application or Platform and `Phase` to the current phase. `Repository`, `Milestone`, `Labels`, `Parent issue` and `Sub-issues progress` provide the remaining context. `type:task` is a bounded delivery, `type:experiment` needs measured evidence, and `type:epic` is a parent outcome.

Matching milestones exist in each applicable repo; they are separate GitHub objects. Phase is the cross-repository program view. Cloud, scaling, mesh and AI remain outside P1.

| Status | Review stage | Meaning |
|---|---|---|
| Todo | Blank | Backlog or blocked; inspect native blocked-by links |
| Todo | Ready | Contract/scope understood, dependencies accepted and merged, validation path known |
| In Progress | In progress | Assignee actively implementing the bounded outcome |
| In Progress | In review | PR and evidence available for review |
| Done | Done | Accepted evidence and merged delivery; an experiment also has measured results/cleanup |

Do not infer completion from documentation, a checked-in manifest or a green scaffold check. Planning PRs remain In review until authorized merge. Unstarted implementation is unassigned; claim ownership when taking it. Keep at most one implementation ticket active per logical team; parent epics are outcome trackers, not extra implementation streams.

## Meaningful tickets and review

Each issue names the user/operator outcome, team/phase, scope, exclusions, acceptance criteria, dependencies, evidence and resource lifecycle. Use native blocked-by relationships and native sub-issues alongside readable links. Child completion alone does not prove the parent outcome.

Prefer one coherent behavior per task/PR. Split an issue further when one acceptance criterion needs an independent design/release or cannot be reviewed alongside the rest. Later experiments are deliberately coarse until they become the next phase; refine them before marking Ready. No time estimates or deadlines are fabricated.

Define interfaces with careful review, then hand bounded implementation tickets to an execution agent with the issue, permitted files, contract version and exact check commands. Model choice does not replace tests or review. Architecture/cross-repo changes return to design review. No agents are automatically launched by this workflow.

## Phase 1 critical path

Foundation review -> API/job contract -> fleet and ride APIs -> worker/scenarios -> integrated Compose -> platform acceptance. UI starts against contract fixtures; service CI grows with implementation. Full live UI validation is part of integrated acceptance.

Cloud feasibility, Kubernetes, Helm publication, KEDA, Istio, Backstage and AI do not block P1. Implementation begins with the contract ticket after foundation merge. Application's local epic tracks app delivery; Platform acceptance validates the handoff separately.

## Current ticket map

### P0 - Delivery foundation

| Team | Outcome | Type | Blocked by |
|---|---|---|---|
| Platform | [Establish two-team repository boundaries and delivery workflow](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/1) | task | None |
| Application | [Establish application repository layout and contribution checks](https://github.com/ANISHG-26/ottawa-fleet-app/issues/3) | task | [ottawa-fleet-platform#1](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/1) |

### P1 - Local application

| Team | Outcome | Type | Blocked by |
|---|---|---|---|
| Application | [Deliver the local mock fleet operations application](https://github.com/ANISHG-26/ottawa-fleet-app/issues/4) | epic | [ottawa-fleet-app#3](https://github.com/ANISHG-26/ottawa-fleet-app/issues/3) |
| Application | [Define fleet, ride and job contracts with executable examples](https://github.com/ANISHG-26/ottawa-fleet-app/issues/1) | task | [ottawa-fleet-app#3](https://github.com/ANISHG-26/ottawa-fleet-app/issues/3) |
| Application | [Implement the Go mock fleet API and deterministic inventory](https://github.com/ANISHG-26/ottawa-fleet-app/issues/2) | task | [ottawa-fleet-app#1](https://github.com/ANISHG-26/ottawa-fleet-app/issues/1) |
| Application | [Implement durable ride submission and queued work in Go](https://github.com/ANISHG-26/ottawa-fleet-app/issues/5) | task | [ottawa-fleet-app#1](https://github.com/ANISHG-26/ottawa-fleet-app/issues/1) |
| Application | [Process ride jobs with bounded retries and restart recovery](https://github.com/ANISHG-26/ottawa-fleet-app/issues/6) | task | [ottawa-fleet-app#2](https://github.com/ANISHG-26/ottawa-fleet-app/issues/2), [ottawa-fleet-app#5](https://github.com/ANISHG-26/ottawa-fleet-app/issues/5) |
| Application | [Build the operator UI for fleet and ride visibility](https://github.com/ANISHG-26/ottawa-fleet-app/issues/7) | task | [ottawa-fleet-app#1](https://github.com/ANISHG-26/ottawa-fleet-app/issues/1) |
| Application | [Add repeatable demand and service-failure scenarios](https://github.com/ANISHG-26/ottawa-fleet-app/issues/8) | task | [ottawa-fleet-app#2](https://github.com/ANISHG-26/ottawa-fleet-app/issues/2), [ottawa-fleet-app#5](https://github.com/ANISHG-26/ottawa-fleet-app/issues/5) |
| Application | [Package the complete application for local Docker Compose](https://github.com/ANISHG-26/ottawa-fleet-app/issues/9) | task | [ottawa-fleet-app#2](https://github.com/ANISHG-26/ottawa-fleet-app/issues/2), [ottawa-fleet-app#5](https://github.com/ANISHG-26/ottawa-fleet-app/issues/5), [ottawa-fleet-app#6](https://github.com/ANISHG-26/ottawa-fleet-app/issues/6), [ottawa-fleet-app#7](https://github.com/ANISHG-26/ottawa-fleet-app/issues/7), [ottawa-fleet-app#8](https://github.com/ANISHG-26/ottawa-fleet-app/issues/8) |
| Application | [Gate application changes with local and CI behavior checks](https://github.com/ANISHG-26/ottawa-fleet-app/issues/10) | task | [ottawa-fleet-app#1](https://github.com/ANISHG-26/ottawa-fleet-app/issues/1) |
| Platform | [Validate the local application as a platform workload](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12) | experiment | [ottawa-fleet-app#9](https://github.com/ANISHG-26/ottawa-fleet-app/issues/9), [ottawa-fleet-app#10](https://github.com/ANISHG-26/ottawa-fleet-app/issues/10) |

### P2 - Kubernetes and GitOps

| Team | Outcome | Type | Blocked by |
|---|---|---|---|
| Application | [Package application workloads in a versioned Helm chart](https://github.com/ANISHG-26/ottawa-fleet-app/issues/11) | task | [ottawa-fleet-platform#12](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12), [ottawa-fleet-app#12](https://github.com/ANISHG-26/ottawa-fleet-app/issues/12) |
| Application | [Publish immutable application images with release metadata](https://github.com/ANISHG-26/ottawa-fleet-app/issues/12) | task | [ottawa-fleet-platform#12](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12) |
| Platform | [Verify optional GCP lab readiness and teardown feasibility](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/2) | experiment | [ottawa-fleet-platform#12](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12) |
| Platform | [Deliver repeatable Kubernetes application rollout with GitOps](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/5) | epic | [ottawa-fleet-platform#12](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12) |
| Platform | [Bootstrap a disposable local cluster and Argo CD boundary](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/13) | task | [ottawa-fleet-platform#12](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/12) |
| Platform | [Promote app chart and image versions through reviewed GitOps changes](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/14) | task | [ottawa-fleet-platform#13](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/13), [ottawa-fleet-app#11](https://github.com/ANISHG-26/ottawa-fleet-app/issues/11) |
| Platform | [Measure deployed workload health and worker recovery](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) | experiment | [ottawa-fleet-platform#14](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/14) |
| Platform | [Provision a bounded GCP lab with Terraform after feasibility review](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/15) | task | [ottawa-fleet-platform#2](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/2), [ottawa-fleet-platform#7](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) |

### P3 - Scaling and traffic

| Team | Outcome | Type | Blocked by |
|---|---|---|---|
| Platform | [Scale assignment workers from backlog using KEDA](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/16) | experiment | [ottawa-fleet-platform#7](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) |
| Platform | [Explore service traffic routing and failure handling with Istio](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/17) | experiment | [ottawa-fleet-platform#7](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) |

### P4 - Developer experience and AI

| Team | Outcome | Type | Blocked by |
|---|---|---|---|
| Platform | [Integrate Backstage ownership, catalog and operating runbooks](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/8) | task | [ottawa-fleet-platform#7](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) |
| Platform | [Build a read-only AI SRE investigator over platform evidence](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/6) | task | [ottawa-fleet-platform#7](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/7) |
| Platform | [Design and validate one bounded AI-assisted service recovery action](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/18) | experiment | [ottawa-fleet-platform#6](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/6), [ottawa-fleet-platform#16](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/16), [ottawa-fleet-platform#17](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/17) |
| Platform | [Plan the handoff to a separate self-hosted AI infrastructure project](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/9) | experiment | [ottawa-fleet-platform#6](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/6) |
| Platform | [Assess GPU feasibility for the separate AI infrastructure project](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/10) | experiment | [ottawa-fleet-platform#9](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/9) |

## Review handoff

Review platform foundation PR #11 and the application scaffold PR together. Both contain documentation/scaffolding only. Merge requires human authorization; the first Phase 1 implementation is application issue #1.
