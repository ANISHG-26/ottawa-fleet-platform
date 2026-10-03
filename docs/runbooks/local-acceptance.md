# Local application acceptance evidence

The collector can write an evidence report, but it cannot create the workload,
simulate an outage, read host/container resource use, or manufacture completion
counts. An operator runs the integrated Compose stack and supplies observed
measurements. Mixed native/Docker tests are retained as `partial` reports and
cannot pass Compose acceptance.

## Prerequisites and normal journey

Follow the application repository's [local development runbook](https://github.com/ANISHG-26/ottawa-fleet-app/blob/main/docs/local-development.md)
from a fresh checkout. Use its documented development-only credentials and
synthetic data. Start with `python scripts/dev.py up`, open the UI at
`http://localhost:8088`, submit rides, then run the documented bounded surge
with at most 100 requests and 60 seconds. Confirm the normal UI journey before
starting the outage interval.

Collect the currently published endpoints on loopback only:

| Name | Endpoint |
|---|---|
| `ui` | `http://127.0.0.1:8088/` |
| `fleet-ready` | `http://127.0.0.1:8080/readyz` |
| `fleet` | `http://127.0.0.1:8080/v1/fleet?limit=100` |
| `fleet-metrics` | `http://127.0.0.1:8080/metrics` |
| `ride-ready` | `http://127.0.0.1:8081/readyz` |
| `rides` | `http://127.0.0.1:8081/v1/rides?limit=100` |
| `ride-metrics` | `http://127.0.0.1:8081/metrics` |

The stdlib collector uses a 2-second default timeout and a 256 KiB response
cap, accepts only literal loopback addresses or the `localhost` alias, rejects
redirects, and reads at most 10 endpoints. Calls include no credentials.
Workload bounds are 1–100 rides, 1–8 workers and 1–60 seconds. Resource
measurements, backlog counts, completion/duplicate counts, request failures,
recovery duration and p95 latency are operator attestations from the run. The
collector records those supplied values without independently verifying them
and does not infer missing measurements.

## Capture and validate

From `ottawa-fleet-platform`, provide the measured values and endpoint
addresses. Replace every angle-bracket value with a real observed value:

```powershell
python -m scripts.local_acceptance `
  --mode compose --application-commit <full-app-git-sha> --output acceptance-report.json `
  --rides <submitted-rides> --workers <workers> --duration-seconds <seconds> `
  --completed-rides <completed> --duplicate-ride-ids <duplicate-count> `
  --backlog-before-restart <backlog-while-paused> --backlog-after-restart <backlog-after-recovery> `
  --recovery-seconds <measured-seconds> --request-errors <measured-failure-count> `
  --p95-latency-ms <measured-p95-ms> --cpu-percent <observed-cpu-percent> `
  --memory-mib <observed-memory-mib> --resource-scope compose-app-stack `
  --endpoint ui=http://127.0.0.1:8088/ `
  --endpoint fleet-ready=http://127.0.0.1:8080/readyz `
  --endpoint fleet=http://127.0.0.1:8080/v1/fleet?limit=100 `
  --endpoint fleet-metrics=http://127.0.0.1:8080/metrics `
  --endpoint ride-ready=http://127.0.0.1:8081/readyz `
  --endpoint rides=http://127.0.0.1:8081/v1/rides?limit=100 `
  --endpoint ride-metrics=http://127.0.0.1:8081/metrics
python -m scripts.local_acceptance validate acceptance-report.json
```

A successful acceptance report must contain healthy UI/API responses, readiness,
non-empty fleet and ride data, metrics from both APIs, a unique ride history,
completed work, a measured backlog drain with no duplicate ride IDs, and
resource/latency/error observations. Any missing endpoint, unresolved
limitation, invalid/non-finite number, failed measurement or non-Compose mode
produces a partial report and a non-zero exit. Preserve the partial report and
state the missing evidence; do not edit its status field to claim acceptance.

## Worker outage and recovery

Use `python scripts/dev.py ps` to identify the Compose worker service. Pause
only `assignment-worker` with `docker compose -f deploy/compose.yaml pause assignment-worker`,
continue a short bounded surge, and record the ride backlog shown in the UI and
`/metrics`. Restore that exact service with `docker compose -f deploy/compose.yaml unpause assignment-worker`,
wait for the backlog to drain, then record completed ride IDs and elapsed
recovery time. Inspect `python scripts/dev.py logs assignment-worker` and the UI
for errors. Capture `docker stats --no-stream` for the Compose project service
containers while the workload is active. Sum CPU percentages and memory for
the total-stack scope, or supply the assignment-worker row with
`--resource-scope assignment-worker`; record the sampling point and reported
units alongside the input values.
The workload's `ride_pending_jobs` metric is a point-in-time count, not an SLO.
Do not compare measurements across different ride counts, worker counts,
durations, application revisions or host configurations as if they were one
experiment.

## Cleanup and report limits

Run `python scripts/dev.py down` after the run. Normal shutdown preserves the
named development volume; use the application runbook's separate, explicit
reset if discarding data is intended. Platform reports contain synthetic test
data only. No local workload run, checked-in report template or passing unit
test establishes a Kubernetes rollout, promotion, drift correction, rollback,
or cloud teardown result.
