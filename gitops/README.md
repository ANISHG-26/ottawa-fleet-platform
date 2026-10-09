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

The application has a tagged v0.1.0 build with six GHCR images and a chart
package; see the [release contract](../docs/application-release-contract.md)
for the exact source and trusted workflow. The v0.2.0 chart adds the
simulation-controller image and bounded runtime values. Default chart values
intentionally omit image digests; CI values contain syntax-only placeholders.
Promotion accepts either the six-image legacy contract or the seven-image
contract with the simulation controller. Both require independently verified
release metadata with the exact chart version, full source commit, architecture-specific image references
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
`scenarioRunner` and `web` (each `reference`, `sourceCommit`, `architecture`).
New chart promotions add `simulationController` with the same immutable image
metadata. An optional top-level `runtime` object has exactly
`simulationEnabled` (boolean), `fleetProfile` (`default-six` or `route20synthetic`), and
`backgroundColor` (`green` or `blue`). Runtime settings require all seven images
and chart version 0.2.0 or newer; enabling simulation requires `route20synthetic`.
When present, these settings render only `simulation.enabled`,
`simulation.fleetProfile`, and `web.backgroundColor` as Helm parameters. The
default-six profile and disabled simulation remain chart defaults when runtime
settings are omitted. A `database.existingSecret` field and a `rollback` object containing
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
The [first application deployment runbook](../docs/runbooks/first-application-deployment.md)
describes the reviewed promotion and smoke path. The green/blue theme value is
a visual marker only; it does not enable advanced routing.

The previous compatible version annotation is a rollback pointer, not proof
that rollback works. A migration must be backward compatible and the prior
application artifact set must remain available. Validate application health,
version metadata, user journey and database compatibility during a disposable
cluster run. Drift correction, rollout, rollback and teardown have not yet
been demonstrated.
