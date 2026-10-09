# Application-to-platform release contract

Status as of October 9, 2026: application packaging and immutable publication
are implemented. [Tag v0.1.0](https://github.com/ANISHG-26/ottawa-fleet-app/tree/v0.1.0)
selects source commit `f485682ea78c19e17f4194b642f8522e16e77194`;
[trusted build 37131621545](https://github.com/ANISHG-26/ottawa-fleet-app/actions/runs/37131621545)
published six GHCR images and the Helm chart as an Actions artifact. This is a
tagged build, with no GitHub Release record. Artifact publication and the manual
review deployment do not establish repeatable promotion, drift, rollback or
CI expiry/teardown acceptance.

## Ownership and local handoff

The [application repository](https://github.com/ANISHG-26/ottawa-fleet-app) owns source, API/job schemas, migrations, Dockerfiles, Compose and its Helm chart. Platform owns infrastructure, namespaces/policy, controllers, environment values and deployed versions. Do not copy templates between repositories.

Phase 1 handoff includes start/stop/reset instructions, endpoint/configuration inventory, fixtures, probes, graceful shutdown, metrics/correlation IDs, database initialization/ownership and bounded load/fault scenarios. A reset identifies exactly which local data it discards.

Platform validates a fresh clone and records workload, resource use, outage/backlog/recovery and unresolved limits. Applications expose basic metrics before a full monitoring stack exists.

## Phase 2 release package

- Images identify service, source commit, architecture and immutable digest. UI/services expose build metadata.
- The app Helm chart is versioned and documents configuration/schema compatibility. Platform pins immutable chart artifacts or exact source revisions, never a floating branch or `latest` tag.
- Values support namespace portability, probes, ports, resources, graceful shutdown, existing-secret references and an external database. Any disposable lab database option is explicitly identified.
- Chart templates own application workloads only. Namespaces/policies, CRDs, cluster controllers and Istio/KEDA resources remain platform-owned.
- If an autoscaler owns worker replicas, the chart can omit replica management and reconciliation respects that boundary. Backlog signals remain available independently of worker count when scale-to-zero is enabled.
- Migration execution has one owner. Releases state whether older images can run on the new schema; an image rollback does not reverse an incompatible migration.

Publish only from trusted events using scoped credentials. Untrusted PR checks
have no publish/cloud credentials. The current build uses GHCR and chart version
`0.1.0`; its chart package and image metadata are available from the trusted
workflow's artifacts. Platform promotion can select the app-owned chart at the
exact source commit rather than requiring a separately published chart registry.

## Promotion, rollback and acceptance

Application CI produces tested artifacts. A platform PR selects pinned chart/image versions and environment values; Argo reconciles reviewed state. Validate application health and the user journey as well as sync status.

Rollback restores the previous compatible artifact set/configuration after checking database compatibility. Rerun smoke/recovery checks. KEDA and Istio policy changes have independent review and revert procedures.

Phase 1 acceptance remains local. Phase 2 requires a disposable-cluster run with
promotion, drift, compatible rollback and teardown evidence in addition to
published artifacts. The first manual GCP deployment used the v0.1.0 artifact
set; newer merged app fixes do not change that deployed build automatically.
The v0.2.0 chart extends the v0.1.0 package with a seventh
`simulation-controller` image. Platform promotion accepts either the exact
six-image legacy set or the exact seven-image set, and verifies that every
image is immutable, names the expected repository, and carries the chart
source commit. Seven-image promotions may include a strict `runtime` object:
`simulationEnabled` (boolean), `fleetProfile` (`default-six` or `route20synthetic`), and
`backgroundColor` (`green` or `blue`). This object requires chart version 0.2.0
or newer. Enabling simulation requires `route20synthetic`; only the three corresponding
Helm values are emitted. Omitting `runtime` preserves chart defaults.

The green/blue background is a visual release marker. It does not activate
advanced traffic routing or change how requests are routed. The
[first application deployment runbook](runbooks/first-application-deployment.md)
covers the trusted release, reviewed platform pin, Argo sync and workload
smoke sequence. The CI workflow provisions infrastructure and bootstraps Argo;
it does not establish that a live server is healthy or reproduce the complete
application/LGTM deployment. Follow the [on-demand CI runbook](runbooks/on-demand-ci.md)
and keep these acceptance gates separate.
