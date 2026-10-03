# Future AI SRE and inference boundary

AI is Phase 4, after measured platform evidence and runbooks. No model integration, runtime or remediation is implemented.

## Investigator in this project

Platform owns bounded evidence tools and a provider-neutral inference client. Diagnosis starts read-only: parameterized allowlisted queries, time/result/call/token bounds, deadlines, bounded retries and citations. Telemetry and model output are untrusted; no arbitrary SQL or shell execution is exposed.

On failure, return collected evidence and label unavailable conclusions. Identify provider/model provenance and uncertainty. Verify actual provider eligibility, limits, data handling and prices when selecting an adapter.

## Hosting in a separate future project

CPU/GPU hosting needs its own repository, capacity/lifecycle planning, model license review and evaluation when activated. No third repository or model runtime is created now. This platform consumes an authenticated bounded endpoint.

CPU/GPU backlog tickets preserve the learning goals and handoff. Later experiments verify provider eligibility/quotas, measure memory/latency and quality, and prove teardown. Credits do not establish GPU access or authorize billing upgrades.

## Staged remediation

After diagnosis, explore one service-recovery action. Separate evidence, diagnosis, policy, approval, execution and verification in the audit record. Use a narrow allowlist, least-privilege identity, cooldown, attempt cap, kill switch and rollback. Resolve conflicts with Argo/KEDA ownership.

Start supervised. Automatic execution requires a separately reviewed activation decision after failure-path tests. No vehicle actions or unconstrained commands are in scope.
