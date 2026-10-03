# Roadmap

The [Project board](https://github.com/users/ANISHG-26/projects/6) tracks review state. These are planned outcomes, not completed functionality.

## Weekend vertical slice

1. Foundation: public docs, private-note separation, layout, documentation CI and issue workflow.
2. Cloud readiness: confirm trial status, APIs, CPU/disk/IP quotas, cluster sizing, estimate and teardown plan. Record account-specific evidence privately.
3. Telemetry contract and simulator: seeded Ottawa zones, event IDs, vehicle sequence, UTC timestamps, battery and state. Demonstrate Lansdowne demand surge.
4. Ingestion and fleet state: validated append-only events, deduplication, sequence ordering, projector replay and stale/unknown capacity.
5. GitOps deployment: immutable prebuilt images, Helm and Argo CD; measure real cluster allocatable resources and footprint.
6. Investigator: bounded read-only queries and inference, evidence-linked reports, explicit uncertainty and model failure handling.
7. Recovery demo: interrupt processing, observe staleness, investigate, restore/replay, verify no state regression and measure recovery.
8. Backstage: catalog services, ownership and runbooks; add live integrations after the core demo fits.

Minimum portfolio evidence: repeatable incident demonstration, architecture, focused PRs, measured resource use and verified teardown. Record partial results honestly if the weekend ends first.

## Follow-on experiments

- CPU-hosted open model: compare memory, latency and evidence quality against hosted inference using identical incidents.
- GPU scheduling: eligibility/quota/cost gate, device plugin, tainted nodes, GPU resource requests, bounded inference concurrency.
- Self-healing: separate diagnosis, policy, approval and execution; begin with service recovery.
- Terraform: add after the deployment shape stabilizes.

An unupgraded GCP Free Trial blocks GPU VMs. Credits do not remove this restriction. [Trial policy](https://docs.cloud.google.com/free/docs/free-cloud-features).
