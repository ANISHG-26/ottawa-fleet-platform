# First application deployment

This runbook describes the reviewed release path for the disposable platform
lab. It is an operating procedure, not evidence that the cluster is currently
available or that a deployment has succeeded. Keep the application chart and
images in the application repository and pin them from this platform repo.

The [on-demand CI application stage](on-demand-ci.md#automatic-application-stage)
prepares this deployment automatically for future fresh labs using the latest
stable tag. Its first automated live run remains pending. The steps below remain
the manual promotion and inspection path.

## Release and review

1. Select a trusted application tag whose CI run completed successfully. Check
   that the run came from the trusted release workflow and inspect its source
   commit, chart version, image metadata and migration compatibility. The
   release should publish the chart and all seven immutable GHCR images,
   including `simulation-controller`.
2. Download the workflow artifacts and verify the digests, architecture and
   source commit for every image. Confirm the chart is version 0.2.0 or newer
   before using runtime settings. Treat release artifacts as inputs for review;
   a successful build alone does not mean the application has been deployed.
3. Prepare the promotion JSON from verified metadata. Include the seven image
   entries and the externally managed database Secret name. If the release
   should enable simulation, set `runtime.simulationEnabled` to `true` and
   `runtime.fleetProfile` to `route20synthetic`. Otherwise omit `runtime` to use chart
   defaults, or provide the complete strict runtime object to select a visual
   theme. `backgroundColor` accepts `green` or `blue`; it is only a visual
   marker, not advanced traffic routing.
4. Check out the exact application source commit in a clean checkout and render
   the platform Application manifest locally:

   ```powershell
   python -m scripts.promote_release promotion.json --app-checkout ..\ottawa-fleet-app --output gitops/environments/local/application.json
   ```

   Review the generated manifest and platform pin change. Verify the chart
   source revision, all seven image digests, runtime values, destination
   namespace and database Secret reference. Submit the platform change for
   review. Do not apply an unreviewed manifest.

## Sync and verify

After review, sync the Argo Application using the lab's documented operator
procedure. The chart runs its migration hook before the application APIs; wait
for that hook and then inspect the workload rollout. The ordinary deployment
uses one worker replica and a rolling update. Do not infer successful migration
or application health from Argo reporting `Synced` or `Healthy` alone.

Use the exact owned cluster context, confirm its registered expiry, and prepare
the `fleet-app` namespace and external database Secret before applying:

```powershell
kubectl --context <owned-lab-context> apply -f gitops/project.yaml
kubectl --context <owned-lab-context> apply -f gitops/environments/lab/application.json
kubectl --context <owned-lab-context> -n argocd get application ottawa-fleet
kubectl --context <owned-lab-context> -n fleet-app get pods
kubectl --context <owned-lab-context> -n fleet-app port-forward service/web 19000:8080
```

Open `http://127.0.0.1:19000` for the operator UI. Argo watches the pinned
application source commit and reconciles its Helm resources; the trusted image
workflow does not contact the cluster. A later promotion changes the reviewed
source/digest pins in this platform repository and reapplies the Application.
Changing only `runtime.backgroundColor` reuses the same image, changes the web
Deployment environment, and performs an ordinary rolling restart. Keep the
existing lab expiry; deployment does not extend its lease.

Check the pods, events, rollout status and application logs in the `fleet-app`
namespace. Confirm each running image resolves to the pinned digest and that
the release/source metadata matches the reviewed promotion. For request-level
diagnosis, first list the pods and inspect their recent container logs:

```powershell
kubectl -n fleet-app get pods
kubectl -n fleet-app logs <pod-name> --all-containers --since=15m
```

Follow a request correlation ID from the web/API logs through the worker logs.
Run the documented readiness and user-journey smoke checks against the deployed
endpoints; record results, observed release metadata and any unresolved limits.
If checks fail, preserve the evidence and use the reviewed rollback procedure
only after checking database migration compatibility.

Go services write structured JSON to stdout. HTTP completion records include
`service`, `request_id`, `method`, bounded `route`, `status`, and `duration_ms`.
Worker records also identify the synthetic ride/job and distinguish an outgoing
Fleet request ID from its originating request ID. Nginx writes access/error
lines. Inspect these directly for the first release:

```powershell
kubectl --context <owned-lab-context> -n fleet-app logs deployment/ride-api --since=10m
kubectl --context <owned-lab-context> -n fleet-app logs deployment/assignment-worker --since=10m
kubectl --context <owned-lab-context> -n fleet-app logs deployment/fleet-api --since=10m
kubectl --context <owned-lab-context> -n fleet-app logs deployment/simulation-controller --since=10m
kubectl --context <owned-lab-context> -n fleet-app logs deployment/web --since=10m
```

Start with one request ID, find the worker's originating request ID, then find
the outgoing Fleet request ID in Fleet's HTTP completion records. The metrics
endpoints remain available on the Go service ports. Trace export activates when
an OTLP endpoint is configured; the first chart deployment uses stdout logs and
the existing metrics without adding a collector stack. See the application's
[telemetry contract](https://github.com/ANISHG-26/ottawa-fleet-app/blob/main/docs/telemetry.md)
for the asynchronous trace-context boundary.

For the compact implementation-to-release review loop, see
[platform contribution guidance](../../CONTRIBUTING.md#small-release-follow-through).
Append dated measured outcomes under
[deployment acceptance](../acceptance/first-application-deployment.md); keep
private lease credentials and unredacted logs outside this repository.
