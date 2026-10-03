# On-demand weekend lab: sizing and cost

This is the approved initial sizing hypothesis, checked on 2026-10-03, for a synthetic development lab in Iowa (`us-central1`). It is not a production capacity or availability claim. Published application images have passed a bounded local Compose recovery check; that check does not establish a peak resource or full acceptance baseline. The first cloud run has deployed the application and monitoring stack and collected idle resource samples; peak demand remains unmeasured.

## Compute and pod sizing

Start with one zonal GKE Standard cluster and one `e2-standard-2` node: 2 vCPUs and 8 GiB RAM, with a 30 GiB standard persistent boot disk. Keep node autoscaling disabled and the reviewed steady node ceiling at one. GKE creation temporarily uses its bootstrap node before the separately managed node pool is established; account for that transition in quotas and cost. Use one worker and bounded synthetic demand initially.

One node is an economical starting hypothesis for the small application and a non-HA Argo installation. It deliberately has no node-failure availability guarantee. Kubernetes/GKE reserve resources for the system, so 2 vCPUs and 8 GiB are physical capacity, not all available for application scheduling. Confirm actual allocatable resources and the total rendered Argo/system requests before applying; increase the reviewed size only if those requests or measured behavior justify it.

The application chart currently configures:

| Workload | Replicas | CPU request / limit per pod | Memory request / limit per pod |
|---|---:|---:|---:|
| Fleet API | 1 | 100m / 500m | 96 MiB / 256 MiB |
| Ride API | 1 | 100m / 500m | 96 MiB / 256 MiB |
| Assignment worker | 1 | 100m / 500m | 96 MiB / 256 MiB |
| Operator web | 1 | 50m / 250m | 64 MiB / 128 MiB |
| Database migration Job, temporary | 1 | 50m / 250m | 64 MiB / 128 MiB |

With managed PostgreSQL, steady application requests are `100 + 100 + 100 + 50 = 350m` CPU and `96 + 96 + 96 + 64 = 352 MiB` memory. Migration adds 50m and 64 MiB temporarily, making peak requested application allocation 400m and 416 MiB. Steady application limits total 1,750m and 896 MiB; these are ceilings, not reserved capacity, and CPU can throttle under contention.

The first Argo lab profile proposes these explicit budgets; verify its rendered overlay before apply:

| Argo component | CPU request / limit | Memory request / limit |
|---|---:|---:|
| Application controller | 50m / 500m | 512 MiB / 768 MiB |
| Repository server | 50m / 300m | 512 MiB / 768 MiB |
| API/UI server | 50m / 250m | 256 MiB / 512 MiB |
| Redis | 25m / 100m | 128 MiB / 256 MiB |

Unused Dex, notification and ApplicationSet components have zero replicas in this initial profile. Argo requests total 175m and 1,408 MiB; limits total 1,150m and 2,304 MiB. Application plus Argo requests therefore total **525m and 1,760 MiB**, or **575m and 1,824 MiB** while migrations run. Argo CPU requests were reduced after the initial run measured approximately 11m of idle controller use and found GKE system pods requesting another 860m. These are development allocations, not load peaks or SLO evidence.

LGTM adds Grafana 50m/192Mi, Loki 50m/192Mi, Tempo 50m/192Mi, Mimir 200m/384Mi and Alloy 50m/96Mi: 400m CPU and 1,056 MiB total requests. The shared HTTPS gateway adds 50m/64Mi. All application/platform requests therefore total **975m CPU and 2,880 MiB memory**, or **1,025m and 2,944 MiB** during migration. Adding observed GKE system CPU requests gives 1,835m steady, against node allocatable 1,930m; only 95m remains. Single-replica LGTM uses Recreate updates to avoid surge quota deadlocks. Application updates need deliberate rollout headroom; update before the gateway or use an explicitly reviewed no-surge strategy. GKE system requests may change.

The first cloud node reported allocatable capacity of 1,930m CPU and 6,170,260 KiB memory; an early pre-application sample used 155m CPU and 1,309 MiB memory across node/system/Argo workloads. A later sample with the application, gateway and all five monitoring components ready used 397m CPU and 3,788 MiB memory. Neither sample measures a load peak. Argo init containers also add transient bootstrap use. LGTM uses bounded, disk-backed emptyDir volumes for this review lab; telemetry history can be lost when its pods are recreated.

Use Cloud SQL Enterprise PostgreSQL 17 on `db-f1-micro`: shared CPU, approximately 0.6 GiB RAM, one zone and 10 GiB SSD. This is a test/development tier without the Cloud SQL SLA. Keep public IP disabled and use private services access from the dedicated lab VPC, with encrypted database connections and externally managed credentials. The initial disposable lab has no HA, backups, point-in-time recovery or automatic disk growth. Its synthetic database is deleted during teardown; stopping the instance alone would retain storage charges. The earlier in-cluster database failed on a fresh disk's `lost+found` directory and is being replaced by this user-approved managed database.

Private nodes need outbound connectivity for Argo to read GitHub and pull GHCR/upstream images. Cloud NAT serves only the dedicated lab subnet. A user-requested single regional passthrough load balancer fronts the HTTPS gateway for application, Grafana and Argo paths. Its ephemeral IP remains assigned while the Service exists; Grafana and Argo require login. Application images belong to the app repository's GitHub Packages; platform-owned packages belong to the platform repository. No static cloud keys are used.

## Monthly calculation

All figures below are USD list-price estimates, before tax, trial credits, account-wide free-tier eligibility and currency conversion. One explicit planning scenario is one two-hour run on Saturday and one on Sunday:

`runs/month = 2 × 52 / 12 = 8.667`

`lab hours/month = 8.667 × 2 = 17.333 hours`

The two-hour expiry starts from the Actions run start, including provisioning time. Teardown starts at expiry; API deletion and retries take additional time. This is not a hard billing cap. Immediate failure cleanup and a durable independent expiry execution are required; the implementation and real shortened-expiry test must pass before claiming automatic teardown works.

| Cost component | Rate and quantity | Estimated monthly cost |
|---|---|---:|
| One `e2-standard-2` | $0.06701142/hour × 17.333 hours | $1.16 |
| GKE management, gross | $0.10/hour × 17.333 hours | $1.73 |
| 30 GiB standard boot disk | $0.000054795/GiB-hour × 30 × 17.333 | $0.028 |
| Cloud SQL `db-f1-micro` | $0.0105/hour × 17.333 hours | $0.182 |
| Cloud SQL 10 GiB SSD | $0.000232877/GiB-hour × 10 × 17.333 | $0.040 |
| NAT gateway plus one external IP | ($0.0014 × 1 node + $0.005)/hour × 17.333 | $0.111 |
| Shared UI load-balancer forwarding rule | $0.025/hour × 17.333 hours | $0.433 |
| **Scheduled lab infrastructure subtotal** | **About $0.212884/hour** | **$3.69** |
| Cleanup Cloud Build, explicit allowance | 15 build minutes/run × 8.667 × $0.006/minute | $0.78 |
| NAT processed data, explicit allowance | 1 GiB/run × 8.667 × $0.045/GiB | $0.39 |
| Retained state/source storage allowance | 1 GiB × 730 hours × $0.000030137/GiB-hour | $0.022 |

This scenario totals approximately **$4.88/month**, plus load-balancer processing ($0.008/GiB inbound and outbound), storage/API operations, workflow steps, logging, general network egress, bootstrap/deletion overlap and any retained versions beyond the allowance. The forwarding-rule-attached IPv4 has no separate hourly charge. Build minutes and transfer are assumptions, not measured results. Keep retained source/state versions bounded while preserving destroy evidence. Private services access can prevent peering/VPC removal for several days after SQL deletion; the future CI design must retain and separately manage that network foundation rather than claim immediate full destruction.

Each extra two-hour run adds approximately `$0.42577` of scheduled infrastructure, plus its cleanup/transfer allowance and teardown overhead. Substitute actual run counts and measured lifecycle time in the formula. A four-weekend month with eight runs has 16 scheduled hours; the annual-average calculation above uses 8.667 runs.

GKE currently offers $74.40/month of management-fee credit per billing account, applicable to qualifying zonal Standard/Autopilot usage. If that credit is available to this account, this scenario's $1.73 management charge could be offset, leaving roughly $3.15 before other credits and excluded items. Cloud Build currently advertises 2,500 qualifying free build-minutes monthly; do not assume this account has all of them remaining. Trial credit is separate from those eligibility rules. Nothing here upgrades billing or assumes credits make unrestricted resources safe.

At the same gross hourly infrastructure rate, leaving the lab running for 730 hours would cost roughly `$155.41/month` before transfer/build/storage extras, or about `$5.11/day`. The Cloud SQL portion alone would be about `$9.37/month` if left running continuously. The current manual session is intentionally held up for human review; automatic two-hour teardown is not active. The weekend estimate applies only after on-demand cleanup is implemented and verified.

## Evidence to collect on the first run

Record the exact source/image digests, node count/type, allocatable resources, rendered pod requests/limits, `kubectl top` samples (when available), ride completion/backlog/recovery observations, provisioning/deletion duration and post-delete owned-resource inventory. Preserve an error note only when deployment or teardown actually encounters a challenge. Compare the list-price model with delayed billing data after the run; an immediate empty billing chart does not prove zero cost.

## Official pricing sources

- [Compute Engine general-purpose prices](https://cloud.google.com/products/compute/pricing/general-purpose): Iowa on-demand E2 rate used above.
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing): management rate and qualifying monthly credit.
- [Persistent disk pricing](https://cloud.google.com/compute/disks-image-pricing): standard and balanced GiB-hour rates.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing): shared-core instance and SSD storage rates; [machine series](https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview) documents the development tier's size.
- [Cloud NAT pricing](https://cloud.google.com/nat/pricing): per-node gateway, IP and processed-data rates.
- [Load balancer/network pricing](https://cloud.google.com/vpc/network-pricing): forwarding rules, processing and IP treatment.
- [Cloud Build pricing](https://cloud.google.com/build/pricing): default-pool build rate and qualifying free minutes.
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing): retained storage and operation rates; actual location/class applies.
- [Workflows pricing](https://cloud.google.com/workflows/pricing): cleanup orchestration charges depend on executed steps.
- [GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages): Container Registry storage/bandwidth is currently free; other package formats and Actions artifacts have different rules.
