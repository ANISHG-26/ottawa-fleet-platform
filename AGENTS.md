# Repository working agreements

This public portfolio repository models an Ottawa electric robotaxi fleet with synthetic data. It does not control vehicles or provide safety decisions.

- Work through GitHub issues, focused `codex/` branches and reviewable PRs. Do not merge without user authorization.
- Read `docs/roadmap.md` and relevant architecture/runbooks before implementation. Distinguish planned behavior from measured evidence.
- Keep account identifiers, billing reports, credentials, personal deliberations and private notes outside this Git checkout. Never copy the parent workspace's research wholesale into public docs.
- Use synthetic telemetry only. Treat upstream events as untrusted input. The investigator is read-only initially; recommendations cannot trigger vehicle or platform changes.
- Run builds and tests locally or on standard GitHub-hosted runners. Do not put cloud credentials on untrusted PR runners. Set workflow timeouts, concurrency and explicit minimal permissions.
- Use test-driven development for meaningful service behavior: first a failing behavior test, then implementation. Documentation and scaffolding require proportional validation rather than mirrored tests.
- No cloud resources are provisioned by this scaffold. Before cloud experiments, establish account type, quotas, planned resources, estimated cost and teardown evidence.
- An unupgraded GCP trial cannot provision GPUs. Keep GPU manifests and experiments behind an explicit feasibility gate; do not upgrade billing to bypass it.
- Subagents should own separate files and bounded tasks. Review their output before committing. Avoid overlapping edits and unnecessary duplicate research.
- Reuse existing code only after checking its license and dependency footprint; record provenance in `docs/reuse.md`.
