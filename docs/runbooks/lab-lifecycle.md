# Cloud lab lifecycle (draft)

This is a proposed operating procedure for short, disposable learning labs. The repository scaffold has no deployment, Terraform, or scheduled automation. No cloud resources have been provisioned by this project.

## Gate before provisioning

- [ ] Confirm the active Google Cloud project and account type from the console; record the confirmation date and evidence link in a private lab log. The known account is an unupgraded GCP Free Trial. Do not upgrade billing to work around trial restrictions.
- [ ] Treat GPU VM creation as prohibited while the trial is unupgraded. GPU work remains a feasibility-gated future experiment.
- [ ] Check current project/API enablement and applicable CPU, disk, external IP, load balancer, and networking/NAT quotas in the console for the intended region. Record observed quota, current use, needed headroom, region, and evidence links. Do not assume a quota from a published “free” allowance.
- [ ] Write a resource inventory with exact project, region, resource names, owner, purpose, planned size/count, start time, teardown deadline and deletion method. Include cluster/node pool, disks, images, addresses, load balancers, NAT and logging.
- [ ] Estimate cost using current provider pricing and the inventory. Set a short session deadline and a human owner who will verify teardown. Limits and quotas are constraints, not budget caps or cost guarantees.
- [ ] Choose either disabled autoscaling or explicitly capped autoscaling with a small, recorded maximum. Confirm the cap fits the quota and estimate. Do not leave unconstrained autoscaling enabled.
- [ ] Keep logs short-lived and avoid sensitive or real vehicle data. Use synthetic telemetry only.

## Proposed lab shape

The learning target is one GKE Standard cluster in a single region, created only after every gate above passes. This is a proposal, not an implemented deployment. Begin with the smallest suitable CPU node pool and one bounded exercise. Record exact names before creating anything. Terraform is deferred; do not imply that infrastructure-as-code or repeatable deployment exists.

## Shutdown and teardown

Stopping or scaling down nodes is not equivalent to deleting a cluster. Persistent disks, images, reserved IP addresses, load balancers, NAT configuration and logs can remain billable after nodes stop. At the deadline, stop new work, preserve only required synthetic results, and follow this sequence:

1. Use the saved inventory and active-project/region context to identify the exact cluster created for this lab. Check ownership labels and names before acting.
2. Delete that exact named cluster using the provider console or a reviewed command. Do not use a broad project-wide delete, wildcard, or guessed name.
3. Re-list resources in the project and region. For each remaining disk, image, address, load balancer, NAT resource, or other artifact, verify it belongs to this lab, then delete it by its exact name. Retain unrelated/shared resources.
4. Record the post-delete inventory and console evidence. Verify the cluster and each owned residual resource are absent. Check billing/cost reporting later as well; reporting can lag deletion, so absence of an immediate cost change is not proof of failure or success.
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

The command sketch does not discover or remove residual resources. Complete the manual inventory-based checks above and preserve evidence. No scheduled shutdown or cleanup automation is implemented.

## Completion evidence

A lab is complete when its inventory and estimate were recorded before provisioning, the deadline and owner were explicit, the selected autoscaling policy was bounded, and post-teardown evidence shows the exact cluster and owned residual resources removed. Record any delayed billing review separately. This checklist is operational guidance, not proof that a cloud experiment has run.
