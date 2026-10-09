# First application deployment

This runbook describes the reviewed release path for the disposable platform
lab. It is an operating procedure, not evidence that the cluster is currently
available or that a deployment has succeeded. Keep the application chart and
images in the application repository and pin them from this platform repo.

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
