# Local LGTM telemetry runbook

This experimental local stack supports the Ottawa Fleet synthetic application. It runs Grafana, Loki, Tempo, Mimir, and Alloy as single-process Compose services. It is a developer learning setup, not a production deployment or proof of the platform acceptance ticket. The current P2 platform issue is [#19: Prepare bounded local LGTM telemetry configuration](https://github.com/ANISHG-26/ottawa-fleet-platform/issues/19); the application instrumentation change is [app #15](https://github.com/ANISHG-26/ottawa-fleet-app/issues/15).

## Components and pinned provenance

The Compose file pins Grafana `13.2.2`, Loki `3.7.0`, Tempo `3.0.3`, Mimir `3.2.1`, Alloy `v1.20.1`, and the small BusyBox `1.37.0` ownership initializer. Grafana, Loki, Tempo, and Mimir are AGPL-3.0-only; Alloy is Apache-2.0 and BusyBox is GPL-2.0. App instrumentation uses OpenTelemetry Go `v1.43.0` under Apache-2.0 and sends traces through the OTLP/HTTP exporter. These upstream binaries/configuration interfaces are referenced; no component source is vendored.

- Grafana [Docker image docs](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/) and [13.2.2 release](https://github.com/grafana/grafana/releases/tag/v13.2.2).
- Loki [local Docker setup](https://grafana.com/docs/loki/latest/setup/install/docker/), [3.7.0 release](https://github.com/grafana/loki/releases/tag/v3.7.0), and [retention/filesystem guidance](https://grafana.com/docs/loki/latest/operations/storage/filesystem/).
- Loki 3.7.0 [image Dockerfile](https://github.com/grafana/loki/blob/v3.7.0/cmd/loki/Dockerfile) sets the container user to UID 10001.
- Tempo [local Compose guidance](https://grafana.com/docs/tempo/latest/docker-example/), [3.0.3 release](https://github.com/grafana/tempo/releases/tag/v3.0.3), and [recommended versions](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/recommended-versions/).
- Tempo 3.0.3 [image Dockerfile](https://github.com/grafana/tempo/blob/v3.0.3/cmd/tempo/Dockerfile) sets the container user to UID/GID 10001.
- Mimir [single-binary mode](https://grafana.com/docs/mimir/latest/references/architecture/deployment-modes/), [3.2.1 release](https://github.com/grafana/mimir/releases/tag/mimir-3.2.1), and [retention settings](https://grafana.com/docs/mimir/latest/configure/configure-metrics-storage-retention/).
- Alloy [release v1.20.1](https://github.com/grafana/alloy/releases/tag/v1.20.1) and [`prometheus.scrape` reference](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.scrape/).
- Alloy `otelcol.exporter.otlp` [v1.20.1 component source](https://github.com/grafana/alloy/blob/v1.20.1/internal/component/otelcol/exporter/otlp/otlp.go) defines `sending_queue` and `retry_on_failure` as exporter-level blocks beside `client`.
- BusyBox [1.37.0 release](https://busybox.net/) and [license](https://git.busybox.net/busybox/tree/LICENSE) (used only for a one-shot named-volume ownership setup).
- OpenTelemetry Go [v1.43.0 release](https://github.com/open-telemetry/opentelemetry-go/releases/tag/v1.43.0) and [Go exporters guide](https://opentelemetry.io/docs/languages/go/exporters/).
- Project license declarations: [Grafana](https://github.com/grafana/grafana/blob/main/LICENSE), [Loki](https://github.com/grafana/loki/blob/main/LICENSE), [Tempo](https://github.com/grafana/tempo/blob/main/LICENSE), [Mimir](https://github.com/grafana/mimir/blob/main/LICENSE), [Alloy](https://github.com/grafana/alloy/blob/main/LICENSE), and [OpenTelemetry Go](https://github.com/open-telemetry/opentelemetry-go/blob/main/LICENSE).

## Start and stop

Follow the app's [local telemetry instructions](https://github.com/ANISHG-26/ottawa-fleet-app/blob/main/docs/telemetry.md): start the base app once to create the external `ottawa-fleet-app` bridge, apply the app telemetry overlay to create and initialize the external log volume, then start this platform Compose stack. The app's one-shot log-volume initializer sets the exact shared named volume to UID/GID 10001; Alloy consumes it read-only. The app can start its optional exporter before Alloy is up; OTLP export is best-effort and its queue is bounded. Set a non-empty `GRAFANA_ADMIN_PASSWORD` in the current shell before starting the stack:

```powershell
docker compose -f observability/compose.telemetry.yaml up -d
```

Grafana is at [http://127.0.0.1:3000](http://127.0.0.1:3000). The password is provided through the shell and is not stored in repository files. Only Grafana and Alloy's optional OTLP/HTTP listener have host bindings, both on loopback. Mimir, Loki, and Tempo remain on the telemetry bridge. Alloy uses the external application bridge to scrape `/metrics` and receive application traces. It reads only three explicit JSONL paths mounted read-only; the collector does not use the Docker socket.

Stop the stack while in the platform repository:

```powershell
docker compose -f observability/compose.telemetry.yaml down
```

This keeps named volumes containing Grafana state and telemetry. On startup, the one-shot `telemetry-data-init` service changes only the Loki, Tempo, and Mimir volume roots to UID/GID 10001 before those services start. Loki and Tempo use that non-root image identity; Compose explicitly runs Mimir as UID/GID 10001. The image Dockerfiles and CI writable-volume smoke check cover those ownership assumptions. `down -v` removes platform history; run it only when that is intended. The application JSONL files are in the external Docker volume `ottawa-fleet-app-telemetry-logs`, capped at 8 MiB per service. When a service's file reaches its cap, later logs continue on stdout but are no longer collected by Alloy. Remove the app volume only after stopping the overlay and only when intentionally discarding those files; its init service will recreate permissions on the next start.

## What is collected

Alloy scrapes Fleet API `:8080/metrics`, Ride API `:8081/metrics`, and assignment worker `:8082/metrics` every 15 seconds and remote-writes to Mimir. The Grafana dashboard uses current exported series: `ride_pending_jobs` and `assignment_completed_total`. Alloy tails the app's capped JSONL files and pushes logs into Loki with fixed `job` and `service` labels; severity is parsed from the structured JSON line. Request completion and assignment processing logs contain trace/span IDs without using them as Loki labels. Loki provides a TraceID link to Tempo, and Tempo searches Loki by trace/span ID. App stdout remains available through `docker compose logs`.

When `OTEL_EXPORTER_OTLP_ENDPOINT` is configured, the APIs and worker emit bounded OTLP traces. HTTP server spans and worker outbound Fleet HTTP calls use W3C Trace Context. Worker Fleet calls are child spans of an `assignment.process` span. The durable asynchronous job record does not store a trace context, so the worker trace cannot continue the originating Ride API request trace; use existing request-ID log fields to relate those events. HTTP span names use templated routes, and span attributes exclude raw URL paths, query strings, bodies, ride IDs, and job IDs.

## Resource and data limits

Compose configures steady-service CPU and memory ceilings that total 3 CPU and 2,176 MiB: Grafana 0.5/384 MiB, Loki 0.5/384 MiB, Tempo 0.5/384 MiB, Mimir 1/768 MiB, and Alloy 0.5/256 MiB. The short-lived ownership initializer is separately capped at 0.1 CPU/32 MiB. These are unmeasured experimental limits, not a resource baseline. Docker Compose's enforcement behavior depends on the host engine and must be confirmed during live acceptance.

Loki retention is 48 hours; Tempo and Mimir retention is 24 hours. The Alloy trace queue and remote-write queue are bounded, as are app file logs and the OTLP trace batch queue. Retention removes old backend data asynchronously; filesystem volumes have no portable Compose hard-size cap. Therefore this configuration does not guarantee a maximum disk footprint. Check free disk before long scenarios and remove retained telemetry volumes deliberately when resetting the experiment.

No Docker registry pull, stack startup, data ingestion, dashboard query, end-to-end trace, CPU/memory measurement, cluster deploy, cloud resource, or production readiness is claimed here. Run `docker compose config` before starting; a live data-flow check is still required when the pinned images are available locally or the registry is reachable.

## Bounded single-node GKE stack

`observability/kubernetes/` contains the same pinned single-process backends and dashboard for the disposable GKE lab. It requests 400m CPU and 1,056 MiB memory across five pods (Grafana, Loki, Tempo, Mimir, Alloy); limits are 1,300m CPU and 1,408 MiB memory. These are scheduling budgets, not measured capacity. Each backend has one replica, filesystem data lives in capped `emptyDir` volumes, and restarts or teardown discard telemetry history. It is intended for one low-volume synthetic workload, with no persistence or availability guarantee.

Before applying, ensure the `fleet-app` namespace and app services exist and create the Kubernetes Secret `observability/grafana-admin` with key `password` through the approved secret path. Do not put the Grafana password in Git. The v0.1.0 application chart has no telemetry environment-value input. The first manual lab uses a reviewed environment patch setting `OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy.observability.svc.cluster.local:4318` on Fleet API, Ride API and assignment worker. Argo's exception is restricted to that one named environment entry in the exact three deployment/container pairs, with `RespectIgnoreDifferences=true`; do not ignore all environment entries or entire workload specifications. This temporary configuration is not an automated release path. Add a reviewed chart input before claiming repeatable CI deployment. Apply the stack and then bind Alloy's read-only pod log access in the app namespace:

```powershell
kubectl apply -k observability/kubernetes
kubectl apply -f observability/kubernetes/alloy-rbac.yaml
```

The gateway serves Grafana at `/grafana/` and preserves that prefix to `grafana.observability.svc.cluster.local:3000`. After its public IP is known, replace the placeholder in Grafana's external URL and let its deployment restart:

```powershell
kubectl -n observability set env deployment/grafana "GF_SERVER_ROOT_URL=https://${GATEWAY_IP}/grafana/"
```

Alloy scrapes the three existing `/metrics` endpoints every 15 seconds, reads application JSON stdout through Kubernetes' pod log API, and sends logs to Loki. The app's existing OTLP/HTTP trace exporter targets Alloy; Alloy forwards traces to Tempo. Grafana's provisioned Mimir, Loki and Tempo sources feed the bundled pending-jobs, completed-jobs and recent-logs dashboard, with the existing trace/log links. The Alloy role in `alloy-rbac.yaml` grants `get`, `list` and `watch` only for pods and pod logs in `fleet-app`.

This overlay shares the small node with Argo CD, GKE system pods, the gateway and the app. Confirm the rendered requests against current node allocatable capacity before apply. It does not claim live ingestion, successful UI access, or measured runtime fit until those are checked in the lab.

Grafana keeps its image-bundled data-source plugins by setting `GF_PLUGINS_PREINSTALL_AUTO_UPDATE=false`. The first live run reproduced the background updater unloading those plugins and then failing to replace files on the read-only root filesystem; queries failed even while Grafana's health endpoint was ready. This setting preserves the read-only filesystem and makes plugin upgrades part of the reviewed image change. See the [upstream failure report](https://github.com/grafana/grafana/issues/132528) and [version-pinned configuration defaults](https://github.com/grafana/grafana/blob/v13.2.2/conf/defaults.ini).
