# Terraform lab

`lab/` is the Terraform root for the optional, zonal GKE Standard lab. It owns
one private VPC and subnet, subnet-scoped Cloud NAT for GitHub/GHCR traffic,
one `e2-standard-2` node with a 30 GiB `pd-standard` disk, and a DNS-only GKE
control-plane endpoint gated by IAM. Nodes have no external IP addresses.
Cloud NAT is required because Argo CD fetches the app chart from GitHub and
the public, immutable app images from GHCR. Terraform does not create a public
load balancer; the separately applied `bootstrap/gcp/gateway` Kubernetes Service
creates the shared review UI load balancer and must be deleted before cluster
teardown. Its charge is included in the lab sizing and cost document.

The first run uses an explicitly reviewed sizing hypothesis; it is not backed
by an accepted local measurement. Collect resource and workload observations
during the cloud run and compare them with that hypothesis. The single node is
not highly available: maintenance and node upgrades can interrupt workloads.
The cluster uses a node service account created and granted
`roles/container.defaultNodeServiceAccount` separately. Terraform reads that
identity but does not edit project IAM, so later expiry cleanup does not need
`setIamPolicy`.

## Private inputs and reviewed plan

Keep the versioned GCS state bucket, backend config, variable file, plan file,
and any account-specific evidence private and outside Git. Use a unique state
prefix and cluster name for each disposable run. The variable file includes
the concrete inventory, API/quota/pricing confirmation, teardown owner and
deadline, exact node shape, and the reviewed initial sizing hypothesis. No
project, zone, billing data, credentials, or account notes have defaults in
source control. APIs are enabled separately before Terraform runs.

From PowerShell, initialize using the private backend config, then save and
review the exact plan before applying it:

```powershell
terraform -chdir=terraform/lab init -input=false -backend-config="<PRIVATE_BACKEND_CONFIG>"
terraform -chdir=terraform/lab plan -input=false -var-file="<PRIVATE_TFVARS>" -out="<PRIVATE_PLAN_FILE>"
terraform -chdir=terraform/lab show -no-color "<PRIVATE_PLAN_FILE>"
terraform -chdir=terraform/lab apply -input=false "<PRIVATE_PLAN_FILE>"
```

The private inputs must include `node_service_account_id`, which identifies
the separately managed node identity. Terraform requires the project, zone,
node count, node ceiling, machine and disk shape to match the reviewed
inventory. The actual reviewed plan remains the apply approval boundary.

The root is pinned to Google provider 7.29.0. Credential-free validation and
mock tests can be run with:

```powershell
terraform -chdir=terraform/lab fmt -check -recursive
terraform -chdir=terraform/lab validate
terraform -chdir=terraform/lab test
```

## Bootstrap and smoke check

After apply, use a dedicated kubeconfig file outside the checkout. The helper
fetches only the pinned Argo CD v3.5.3 manifest, rejects redirects, caps it at
2 MiB and verifies SHA-256 `7efe2d6bbc03f63623640f1e4198f16c84009d510fb810ef71e56df1b7614ba9`
before applying it. It verifies the exact DNS-endpoint context before any
Kubernetes changes, sets explicit resource requests and limits, disables
unused Dex, notifications and ApplicationSet controllers, waits for the
remaining Argo components and Ready node, and applies the `AppProject`.

```powershell
python -m scripts.gcp_lab bootstrap --project <PRIVATE_PROJECT_ID> --zone <REVIEWED_ZONE> --cluster <EXACT_CLUSTER_NAME> --kubeconfig <PRIVATE_KUBECONFIG>
kubectl --kubeconfig <PRIVATE_KUBECONFIG> --context gke_<PROJECT>_<ZONE>_<CLUSTER> get nodes
kubectl --kubeconfig <PRIVATE_KUBECONFIG> --context gke_<PROJECT>_<ZONE>_<CLUSTER> -n argocd get deployments,statefulsets
```

The helper does not create cloud resources. Do not run a second Terraform root
or a broad `gcloud` cleanup command. After validation, destroy only the saved
plan's exact state with the reviewed private inputs, then inspect the exact
cluster, NAT/router, VPC/subnet, nodes, disks and external addresses for
residual resources. The later timed GitHub Actions path will use the same lab
root and an external durable expiry controller; the manual first run does not
claim automated two-hour cleanup.
