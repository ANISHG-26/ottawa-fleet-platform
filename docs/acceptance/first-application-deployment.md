# First application deployment acceptance

**Observed 2026-10-09** in the existing bounded GKE lab. This records a measured
deployment and application journey, not a production readiness or performance
claim.

The application was promoted at tag [v0.2.1](https://github.com/ANISHG-26/ottawa-fleet-app/tree/v0.2.1),
source commit [`f91147ce8b7cc997e2bebe371fcdec8a6cc630d2`](https://github.com/ANISHG-26/ottawa-fleet-app/commit/f91147ce8b7cc997e2bebe371fcdec8a6cc630d2),
from [trusted release run 37979235045](https://github.com/ANISHG-26/ottawa-fleet-app/actions/runs/37979235045).
The platform deployment synced and became healthy, its database migration hook
succeeded once, all seven immutable image pins matched the reviewed release, and
the five application deployments were ready with zero container restarts. The
existing CI lab lease (run 37970413080) was scheduled to expire at
2026-10-09 20:01:43 UTC; it was not extended and no infrastructure was added.

## Live journey results

| Check | Observed result |
|---|---|
| Existing inventory | All 20 physical vehicle IDs remained present. No reset or historical record deletion occurred. |
| API simulation | Run `run-ab60f52a37c1112e8d335d53` completed. Its trip took 8.088225 seconds by Ride server timestamps, showed two moving positions across a 21-point route, and applied both start and completion events. All incomplete counters were zero. |
| Arrival and reuse | `vehicle-002` arrived in Centretown and became available. A temporary public-API reservation held the earlier `vehicle-001`; the follow-up Ride then reused `vehicle-002`. Both the hold and follow-up reservation were released. |
| Stop and drain | Run `run-88eaecd09f80f0029cc11872` stopped after its accepted trip was observed in progress. Drain took 9.172 seconds, applied both events, and left zero incomplete trips, requests or events. Ride confirmed the same trip completed; Fleet showed the vehicle available and unreserved in Centretown at the route endpoint. |
| Browser journey | The operator UI displayed 20 vehicles and loaded map tiles. UI-created run `run-761bca4af4f8c78ee88b7a06` used one request, one event per second, a 30-second duration and concurrency one; it completed both events with no incomplete work and its trip completed in Centretown. The controller read positions for 20 vehicles; 19 observations were fresh, with the stale fixture for vehicle-006 behaving as configured. The browser showed the green background marker. |
| Request logs | Sanitized tails showed structured JSON from the Go services and text access/error logs from the web container. The follow-up request ID appeared in Ride API and assignment-worker logs; worker records carried originating and outgoing request IDs. |
| Resource sample | One `kubectl top pods` sample across the five application pods totaled 44 millicores and 25 MiB. This is a single observation, not a baseline, peak or capacity measurement. |

## v0.2.0 issue and historical recovery

The first v0.2.0 rollout was healthy at the pod and readiness level, but the
business probe exposed a missing `FLEET_API_URL` setting in Ride API: simulation
trip start returned 503. The v0.2.1 release corrected that runtime configuration;
the missing-owner-URL regression was reproduced red with the old setting and
passed green after the fix. This is why readiness alone is not counted as
application acceptance.

The earlier stopped run, `run-3f79797000fca2dd11f786bf`, later reconciled after
the setting was corrected. Its Ride trip is completed, both ledger events are
applied, and `vehicle-001` is available in Centretown. The run itself remains
`stopped` with terminal reason `deadline`; its original incomplete snapshot
(one trip, one request and two events) remains unchanged. Recovery did not erase
or rewrite that history.

The live cluster was verified with the green background marker. Green, blue and
invalid-fallback production-Docker-image checks passed against the same image.
Changing the configured background triggers an ordinary web Deployment
rollout, but no blue background promotion was performed in this cluster; no
weighted traffic split, canary or blue-green routing was enabled.

The documented journeys added synthetic simulation runs and rides to the
existing dataset, then released their own temporary reservations. They did not
reset fleet, Ride, job or simulation history. Detailed account-specific
captures remain in private operator records.

See the [first deployment runbook](../runbooks/first-application-deployment.md)
for the repeatable release and verification procedure.
