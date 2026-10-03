# GitOps application boundary and promotion

The app repository remains the sole owner of its Helm chart. This repository
owns the Argo `AppProject`, environment release inputs, and promotion tooling.
`gitops/project.yaml` allows only the application Git repository, a single
`fleet-app` destination and a short namespaced-resource allowlist. It does not
allow cluster-scoped app resources or additional destinations.

The upstream Argo controller install itself grants broad cluster permissions.
The `AppProject` restricts intended application reconciliation; it does not
reduce controller ServiceAccount permissions or isolate the controller from a
cluster compromise. Use this setup only in the disposable local lab.

## Prepare an immutable promotion

The application currently documents its Helm chart as not yet released and
its chart values as containing syntax-only image placeholders. Do not promote
those placeholders. A real release must first exist and must provide the exact
chart version, full source commit, six architecture-specific image references
with non-placeholder SHA-256 digests, each image's matching source commit, and
the externally managed database Secret name. Check chart/schema compatibility
and verify backward-compatible migrations before recording the previous
compatible version. The chart must order its migration Job before the APIs at
Argo sync wave `-1`, delete completed/old jobs with
`BeforeHookCreation,HookSucceeded`, and make Job identity change with the
`dbInit` source commit. Required database/ServiceAccount resources precede the
Job; APIs follow it at wave `0`. These are prerequisites for preparing a
promotion, not evidence that a migration or rollback has succeeded.

Create an operator-reviewed JSON input using actual release metadata. It has a
`chart` object (`repository`, `name`, `version`), a `source` object (`repository`,
`revision`), an `images` mapping for `dbInit`, `fleetApi`, `rideApi`, `worker`,
`scenarioRunner` and `web` (each `reference`, `sourceCommit`, `architecture`),
a `database.existingSecret` field and a `rollback` object containing
`previousCompatibleVersion` and `migrationBackwardCompatible`. The image
source commit must match the chart source commit; the architecture must be
explicit. See `scripts/promote_release.py` for exact checks.

Check out the released application commit in a clean local app repository.
Promotion verifies that its full Git `HEAD` matches the input revision and
that `Chart.yaml` at that revision has the requested version. Then prepare a
manifest without contacting Kubernetes:

```powershell
python -m scripts.promote_release promotion.json --app-checkout ..\ottawa-fleet-app --output gitops/environments/local/application.json
```

The rendered Application selects the app-owned chart path at the immutable Git
commit, sends image digests, source commits and architecture metadata to Helm, uses the
pre-existing database Secret, and targets only `fleet-app`. Commit the
promotion as a reviewed change after the app artifacts and chart version have
been independently verified. Argo reconciliation is a separate operator step.

The previous compatible version annotation is a rollback pointer, not proof
that rollback works. A migration must be backward compatible and the prior
application artifact set must remain available. Validate application health,
version metadata, user journey and database compatibility during a disposable
cluster run. Drift correction, rollout, rollback and teardown have not yet
been demonstrated.
