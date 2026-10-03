# Terraform preparation

`lab/` is a preparatory Terraform root for one zonal GKE Standard lab. It owns a dedicated VPC/subnet, one bounded CPU node pool and its node identity. It contains no application or Argo resources. The GKE nodes have private addresses, and the control-plane public endpoint accepts only explicit reviewed CIDRs. Cloud NAT is omitted, so node workloads do not have general outbound internet access and cannot pull from GHCR or another external registry. A future release plan must choose a reviewed image path reachable through Private Google Access (for example, Artifact Registry) or separately review any bounded NAT requirement before deployment.

This code does not establish that cloud provisioning is feasible or authorized. Issue #15 remains open and blocked until the separate feasibility and workload-measurement issues have evidence, and the actual resources have approved apply, teardown and residual-inventory evidence.

## Required private review inputs

There is no default project, zone, cluster name, machine size, node count, disk size or operator CIDR. The caller must supply the project/zone from the reviewed inventory and confirm them again in the review inputs. The default-false gate inputs require confirmation of the inventory, current API/quota checks, pricing, measured local workload, explicit resource shape, total node ceiling and teardown owner/deadline. The node ceiling and each node count are capped at two; machine types are limited to two-vCPU CPU types; disks are capped at 100 GiB. GKE requires a one-node bootstrap pool on cluster creation before Terraform removes it and creates the separately managed pool, so inventory and quota review must account for that transient node. These bounds do not claim that a size fits a quota or budget.

Keep the variable file and review references private and outside Git. Do not put credentials, personal account notes or cost evidence in source control. Required APIs must already be enabled through a separately reviewed process: this configuration intentionally does not create `google_project_service` resources or change billing/API enablement.

## State and credentials

The root selects the GCS backend, but does not create a bucket or commit its name. Before initialization, choose and review an existing private bucket, its IAM access, object versioning and a unique prefix. Put `bucket` and `prefix` in a private backend config file outside the checkout, then initialize with that file. Keep credentials external; the Google provider uses the operator's separately configured Application Default Credentials.

```powershell
terraform -chdir=terraform/lab init -backend=false
terraform -chdir=terraform/lab fmt -check -recursive
terraform -chdir=terraform/lab validate
terraform -chdir=terraform/lab test
```

These are source and mock-provider checks only; initialization downloads the pinned provider but uses no GCP credentials. For a later reviewed run, initialize the GCS backend with its private config file instead of `-backend=false`. This task does not run a cloud plan, apply, destroy, or `gcloud` command. A later plan requires freshly reviewed project/API/quota/pricing evidence, matching inventory and explicit teardown ownership; review the exact resulting plan separately before any apply. Terraform state and plan files can contain sensitive infrastructure metadata.

The Google provider is constrained to `hashicorp/google` 7.29.0. A provider lock file has not been generated because Terraform Registry package discovery was unavailable during preparation; generate and review `.terraform.lock.hcl` for Windows and Linux AMD64 before any cloud plan. Provider and GKE schema details should be rechecked when changing the pin.

Configuration references the official [Google provider 7.29.0 schema](https://registry.terraform.io/providers/hashicorp/google/7.29.0/docs) (provider license: [MPL-2.0](https://github.com/hashicorp/terraform-provider-google/blob/main/LICENSE)) and Google's [GKE hardening guidance](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster). No upstream source code is copied or redistributed.
