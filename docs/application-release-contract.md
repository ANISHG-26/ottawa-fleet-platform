# Application-to-platform release contract

Status: agreed ownership direction; artifacts remain unimplemented.

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

Publish only from trusted events using scoped credentials. Untrusted PR checks have no publish/cloud credentials. Registry and version selection occurs in packaging tickets.

## Promotion, rollback and acceptance

Application CI produces tested artifacts. A platform PR selects pinned chart/image versions and environment values; Argo reconciles reviewed state. Validate application health and the user journey as well as sync status.

Rollback restores the previous compatible artifact set/configuration after checking database compatibility. Rerun smoke/recovery checks. KEDA and Istio policy changes have independent review and revert procedures.

Phase 1 acceptance is local. Phase 2 needs actual chart/images and a disposable-cluster deployment with promotion, drift and rollback evidence. This contract is not a claim that releases exist.
