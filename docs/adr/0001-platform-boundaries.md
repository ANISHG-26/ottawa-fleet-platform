# ADR 0001: Platform boundaries and initial shape

- **Status:** Accepted as the initial design direction; implementation and deployment remain unverified.
- **Date:** 2026-10-03

## Context

The portfolio project needs a concrete, reviewable story for a synthetic Ottawa electric robotaxi fleet: a Lansdowne demand surge occurs while telemetry goes stale because ingestion or its consumer is unavailable. The platform should explain operational capacity and data freshness without suggesting that it drives vehicles or makes safety decisions. It should remain practical for a weekend demo and avoid claims unsupported by a running system.

## Decision

Use a small Go service set for deterministic simulation, ingestion, and read APIs; PostgreSQL for append-only events and a sequence-aware latest-state projection; and a compact dashboard, with its UI framework undecided. Treat event delivery as at least once: stable event identities make replays idempotent, and per-vehicle sequence numbers prevent older observations from replacing newer state. Persist accepted events before projection so a consumer can recover by replay.

Target one GKE Standard cluster for a later deployment. Build prebuilt images in GitHub Actions and reconcile Helm releases with Argo CD. Use Backstage as the service catalog and runbook index. Keep Prometheus/Grafana and OpenTelemetry evidence focused on freshness, ingestion and consumer lag, health, and resource use. Terraform is deferred.

The initial AI investigator uses a hosted Groq or Gemini adapter behind a provider-neutral interface. It may issue bounded read-only queries and produce an evidence-linked report. It cannot write to the database, invoke deployment controls, or issue vehicle commands. Synthetic data only is in scope. A CPU-hosted open-source model is a later adapter experiment. GPU scheduling is deferred behind a quota and feasibility gate; the unupgraded GCP Free Trial cannot provision GPUs.

## Consequences

The durable event log and separate projection make recovery and stale-state explanations demonstrable, while requiring explicit replay, deduplication, gap, and retention behavior. PostgreSQL keeps the first version operationally compact but may become a scaling constraint; measurements should drive any later broker or storage split. One cluster reduces demo complexity but is a shared failure domain and is not an availability claim.

Capacity is a transparent, configurable demo classification using freshness, battery, maintenance, and incident signals. Stale or missing input is unknown, not evidence of availability. No component provides real driving safety guarantees. Hosted model use requires data minimization and scrutiny of provider handling; it remains optional and reports must retain source evidence and disclose uncertainty.

All cluster sizes and resource estimates are provisional. No app is running and no cloud deployment is claimed. Cloud work waits for a practical quota, cost, access, and teardown plan.

## Alternatives considered

- **Directly overwrite current state:** simpler, but loses replay evidence and allows delayed events to regress state.
- **Add a message broker immediately:** useful at larger throughput, but unnecessary operational weight for the initial single-cluster demo; durable PostgreSQL events provide a simpler recovery starting point.
- **Allow AI actions:** rejected because the demo's purpose is investigation, and automated changes would exceed its operational and safety boundary.
- **Start with GPU inference:** deferred because it adds scheduling and cost complexity and is infeasible on the current unupgraded trial. Keep a provider adapter so CPU and hosted experiments can be compared later.
- **Provision infrastructure with Terraform now:** deferred until service shape, quotas, and cost/teardown constraints are known.

## Validation and review triggers

The implementation should demonstrate duplicate/reordered delivery, consumer restart and replay, stale capacity labeling, persistent gaps, and report citations using synthetic events. Review this decision when measured load justifies a broker or database change, cloud feasibility is established, hosted-provider data handling is acceptable, or operator/security requirements are clarified. Validation of documentation is limited to link/path and content review; this ADR does not certify an implementation.
