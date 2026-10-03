# Reuse inventory

No historical private project source, personal research, or application chart
templates have been copied into this repository. Platform tooling is Python
standard library plus declarative upstream installation/configuration
references. Recheck release pins and license provenance when updating them.

| Source / version | License and permission | Files/reference | Purpose | Dependencies | Validation |
|---|---|---|---|---|---|
| [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0) | Apache-2.0 ([license](https://github.com/kubernetes-sigs/kind/blob/main/LICENSE)); upstream project, no source copied | `bootstrap/kind.yaml`; pinned kind node image | Disposable local Kubernetes nodes in Docker | Docker, kind, kubectl; none bundled | Offline config and pin checks. No cluster started. |
| [kind node image v1.35.8](https://github.com/kubernetes-sigs/kind/releases) | Kubernetes components Apache-2.0 ([license](https://github.com/kubernetes/kubernetes/blob/master/LICENSE)); upstream image, not redistributed here | immutable `kindest/node` reference in `bootstrap/kind.yaml` | Pin Kubernetes node contents by digest | Docker pulls image only when operator creates kind cluster | Pin syntax checked; pull/cluster unverified. |
| [Argo CD v3.5.3](https://github.com/argoproj/argo-cd/releases/tag/v3.5.3) | Apache-2.0 ([license](https://github.com/argoproj/argo-cd/blob/master/LICENSE)); upstream manifest prepared on demand and verified against operator-supplied SHA-256 | `scripts/local_cluster.py`; generated versioned manifest | Disposable-lab GitOps controller | Kubernetes/kubectl; no vendored dependency | Fixed URL, no redirect, 8 MiB cap, SHA-256 comparison; no manifest retrieved or installed. |
| Python standard library (runtime recorded in CI) | Python Software Foundation License ([terms](https://docs.python.org/3/license.html)) | `scripts/*.py`, `tests/*.py` | Local evidence validation, bounded HTTP reads, promotion metadata checks | No third-party modules | Offline `unittest`; no external services. |

Argo's standard installation includes cluster-level permissions for its
controller. This is accepted only for a disposable local lab and is kept
distinct from the application `AppProject`, which limits intended source,
destination and app resource kinds but is not controller-level isolation. The
upstream install manifest is not checked in before its checksum is reviewed.

