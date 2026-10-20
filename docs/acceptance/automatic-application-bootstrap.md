# Fresh automatic application bootstrap

Observed **October 20, 2026**, using the existing user-dispatched
[lab run 39475663557](https://github.com/ANISHG-26/ottawa-fleet-platform/actions/runs/39475663557).
Provisioning finished successfully at 18:48 UTC. The automatic app stage from
[PR #44](https://github.com/ANISHG-26/ottawa-fleet-platform/pull/44) selected
[v0.2.1](https://github.com/ANISHG-26/ottawa-fleet-app/tree/v0.2.1), source
`f91147ce8b7cc997e2bebe371fcdec8a6cc630d2`.

| Measured check | Outcome |
|---|---|
| Argo and migration | Synced/Healthy at the expected source; migration hook recorded Succeeded. |
| Running application | Five pods ready, zero restarts; five runtime image identities match configured digest pins. |
| API trip | 21-point route, two moving positions observed, completed in 8.069176 seconds by Ride timestamps; both events applied. |
| Reuse | A new v1 Ride selected the arrived vehicle; the owned reservation was released. |
| Retry and conflict | Exact manifest replay retained its run; changed replay and a second active run were rejected as expected. |
| Stop and drain | Completed in 9.25 seconds with zero incomplete trips, requests or events. |
| Browser | One-request run restored after refresh and completed both events and its trip. Map tiles loaded; all 20 vehicles remained. |
| Diagnosis | The same test request ID appeared in Ride API and assignment-worker logs. |
| Expiry | Registered task matched the unchanged deadline, 20:32:39 UTC. Cleanup had not occurred at inspection. |

These bounded functional checks establish a successful fresh automatic
application bootstrap and business journey. They do not establish capacity,
worker crash recovery, drift correction, rollback, or today's eventual teardown.
No new infrastructure, release promotion, data reset or lease extension was
performed during verification. Detailed account-specific captures remain private.

The earlier October 9 lab's scheduled teardown was separately observed complete:
its GKE and SQL resources were absent, cleanup succeeded and its active lease
was cleared. Do not infer another run's cleanup from that earlier result.

See the [on-demand runbook](../runbooks/on-demand-ci.md) for the mechanism and
[first deployment](first-application-deployment.md) for the earlier manual journey.
