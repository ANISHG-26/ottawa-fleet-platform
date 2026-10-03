# Platform repository working agreements

This repository belongs to the Platform team. Application source, Docker/Compose and the application Helm chart belong in `ANISHG-26/ottawa-fleet-app`. This repo owns infrastructure, controllers, GitOps environment values/release pins and operating evidence. Synthetic workloads only; no vehicle control or safety decisions.

- Work through GitHub issues, focused `codex/` branches and reviewable PRs. Do not merge without user authorization.
- Read `docs/roadmap.md`, `docs/project-management.md`, `docs/application-release-contract.md` and relevant architecture/runbooks. Phase 1 is local; distinguish plans from measured evidence.
- Keep account identifiers, billing, credentials and personal deliberations outside both public checkouts. Never copy the parent workspace's research wholesale.
- Initial AI diagnosis is read-only. Later actions require separately reviewed policy/executor design and activation. Inference hosting is a separate future project.
- Run checks locally or on standard hosted runners. Public PR jobs have no cloud/cluster credentials. Workflows use explicit minimal permissions, timeouts and concurrency.
- Use failing behavior tests before meaningful implementation. Documentation/scaffolding needs proportional validation, not mirrored tests.
- No cloud provisioning before current eligibility/quotas, resource inventory, estimate and teardown are reviewed. Never upgrade billing to bypass a gate. Verify current GPU restrictions in the separate AI project.
- Subagents, if authorized, own separate files and bounded tasks; review before committing. Avoid overlapping edits and duplicate research.
- Check licenses/dependencies before reuse and record provenance in `docs/reuse.md`.
