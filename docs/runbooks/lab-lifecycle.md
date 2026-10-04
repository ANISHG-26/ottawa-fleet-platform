# Cloud lab lifecycle (draft)

This is the operating procedure for an optional GCP lab. Local application and local Kubernetes work do not depend on it. The first manual review lab has deployed the application, monitoring and shared UI gateway; its account-specific inventory and acceptance evidence remain private. Checked-in tooling alone does not establish acceptance or teardown. Sizing remains a hypothesis until bounded load measurements are complete.

## Gate before provisioning

- [ ] Confirm the active Google Cloud project and account type from the console; record the confirmation date and evidence link in a private lab log. Verify current eligibility privately; do not publish account-specific claims. Do not upgrade billing to work around trial restrictions.
- [ ] Exclude GPU provisioning from this fleet lab. A separate future AI project must verify current provider restrictions and eligibility.
- [ ] Check current project/API enablement and applicable CPU, disk, external IP, load balancer, and networking/NAT quotas in the console for the intended region. Record observed quota, current use, needed headroom, region, and evidence links. Do not assume a quota from a published “free” allowance.
- [ ] Write a resource inventory with exact project, region, resource names, owner, purpose, planned size/count, start time, teardown deadline and deletion method. Include cluster/node pool, disks, images, addresses, load balancers, NAT and logging.
- [ ] Estimate cost using current provider pricing and the inventory. Set a short session deadline and a human owner who will verify teardown. Limits and quotas are constraints, not budget caps or cost guarantees.
- [ ] Choose either disabled autoscaling or explicitly capped autoscaling with a small, recorded maximum. Confirm the cap fits the quota and estimate. Do not leave unconstrained autoscaling enabled.
- [ ] Keep logs short-lived and avoid sensitive or real vehicle data. Use synthetic telemetry only.

## Lab shape

The Terraform root creates one zonal GKE Standard cluster with one private `e2-standard-2` node, a 30 GiB standard boot disk, a DNS-only IAM-gated control-plane endpoint and Cloud NAT scoped to the lab subnet. The reviewed managed database option adds private Cloud SQL PostgreSQL and private services access. NAT is required for Argo's pinned GitHub chart source and public GHCR image pulls. The separately applied gateway Service creates one public HTTPS load balancer for application, Grafana and Argo paths. See [Terraform inputs and commands](../../terraform/README.md) and [sizing and cost](../lab-sizing-and-cost.md) for scope and assumptions.

The node service account and versioned Terraform state bucket are persistent
prerequisites managed outside the disposable root. Use a unique state prefix
and cluster name for each run. The manual review deployment has no active
automatic expiry; when teardown is authorized, use its exact Terraform state.

The merged [on-demand CI path](on-demand-ci.md) registers a Cloud Task before
Terraform apply. An authenticated Cloud Run function launches Cloud Build for
exact-run cleanup and verifies absence before releasing the active lease. Its
live activation and expiry/teardown test remain pending under issue #26. CI uses
separate retained network foundation state because Cloud SQL producer cleanup
can delay peering/VPC deletion for days. Run teardown preserves that foundation
and the retained credential containers; the manual lab remains outside CI run
selectors. Do not report complete deletion while run-owned residual resources
remain.

## Shutdown and teardown

Stopping or scaling down nodes is not equivalent to deleting a cluster. Persistent disks, images, reserved IP addresses, load balancers, NAT configuration and logs can remain billable after nodes stop. At the deadline, stop new work, preserve only required synthetic results, and follow this sequence:

1. Disable Argo automated reconciliation, delete the exact application, and delete the lab namespace. Delete the exact gateway LoadBalancer Service while the cluster controller is still running, and verify its forwarding rule/address are removed. Wait for any PVCs and owned persistent disks to be removed before cluster teardown.
2. Use the exact reviewed Terraform backend, state prefix and variable file to destroy the run. Do not use a broad project-wide delete, wildcard, or guessed name.
3. Re-list resources in the project and zone. Verify the cluster, nodes, disks, external addresses, NAT/router and subnet owned by this run are absent. Verify VPC removal only when that VPC belongs to the disposable state; the CI foundation VPC is retained. Retain unrelated/shared resources.
4. Record the post-delete inventory and console evidence. Check billing/cost reporting later as well; reporting can lag deletion, so an immediate cost change is not proof of success or failure.
5. Record who verified teardown, when, any retained resource and its owner/deadline, and the next cost-report review date. Escalate discrepancies to the account owner; do not silently leave resources running.

### Command sketch (DRAFT — UNTESTED)

The following is a shape example only. Replace every `<...>` placeholder with values copied from the reviewed inventory; inspect the selected project and region before running. It intentionally contains no broad cleanup command. Prefer the console if the target cannot be confirmed unambiguously.

```sh
# DRAFT — UNTESTED. Confirm project, region, and exact cluster name first.
gcloud config get-value project
gcloud container clusters list --project <PROJECT_ID>
gcloud container clusters delete <EXACT_CLUSTER_NAME> --project <PROJECT_ID> --location <EXACT_ZONE_OR_REGION>
# Re-list and inspect each residual resource; delete only individually verified lab-owned names.
```

The command sketch does not discover or remove residual resources. Complete the
manual inventory-based checks above and preserve evidence. CI scheduling and
cleanup code are implemented; the manual review lab has no scheduled expiry,
and a live CI cleanup run has not yet demonstrated that automation.

## Completion evidence

A lab is complete when its inventory and estimate were recorded before provisioning, the deadline and owner were explicit, the selected autoscaling policy was bounded, and post-teardown evidence shows the exact cluster and owned residual resources removed. Record any delayed billing review separately. This checklist is operational guidance, not proof that a cloud experiment has run.
