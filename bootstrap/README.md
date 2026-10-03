# Disposable local cluster bootstrap

This is plan-first tooling for issue #13. It does not create or delete a
cluster unless an operator later runs the printed commands. Bootstrap owns the
`fleet-app` and `argocd` namespace objects. Argo owns its installed controller
resources and its `Application` resources; Terraform does not own Kubernetes
objects. There are no credentials in the manifest or CI.

The selected local distribution is kind, which runs Kubernetes nodes as
containers. The cluster name and context are `ottawa-fleet-lab` and
`kind-ottawa-fleet-lab`. Its two-node configuration pins a Kubernetes node
image version and SHA-256 digest. The currently selected kind release and
compatibility should be rechecked against kind's [official releases](https://github.com/kubernetes-sigs/kind/releases)
before the first local creation. A provisional preflight floor is 6 Docker
CPUs and 8 GiB RAM; `docker info` settings are operator supplied. This is a
scaffold floor, not a measured laptop baseline or evidence that the cluster
fits this machine.

Generate the no-side-effect plan after checking Docker Desktop's allocated
resources with `docker info`:

```powershell
python -m scripts.local_cluster plan --expected-context kind-ottawa-fleet-lab --docker-cpus <observed-cpus> --docker-memory-gib <observed-GiB>
```

Argo CD uses a fixed version tag from the official [release list](https://github.com/argoproj/argo-cd/releases)
and the upstream non-HA install manifest, appropriate only for a disposable
lab. The installer includes broad controller permissions; the AppProject at
`gitops/project.yaml` constrains application source and destination to the app
repository and `fleet-app` namespace and denies cluster-scoped app resources.
Review that boundary and the upstream manifest before installation. Confirm
the `argocd` namespace exists using `bootstrap/namespaces.yaml` first.

To prepare the manifest, supply a SHA-256 from an independently reviewed copy
of the same pinned upstream release manifest. The command downloads only the
fixed `v3.5.3` URL, rejects redirects, caps the body at 8 MiB, compares SHA-256,
and writes a versioned file only on a match:

```powershell
python -m scripts.local_cluster verify-argo --sha256 <reviewed-64-character-sha256>
```

Then inspect and execute the generated commands individually. Every kubectl
command names the expected context. Bootstrap is not complete until the
operator confirms that context and the exact owned namespaces/resources.

Teardown is similarly plan-only:

```powershell
python -m scripts.local_cluster delete-plan --cluster-name ottawa-fleet-lab --confirm-name ottawa-fleet-lab
```

It prints deletion for that exact kind cluster. Before execution, check the
active context, cluster name and ownership labels; inspect generated resources
and local volumes individually. The script does not delete a cluster, volumes,
or any other resources. No fresh setup, controller deployment or teardown has
been executed or evidenced by this scaffold.
