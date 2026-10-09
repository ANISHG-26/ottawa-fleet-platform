# Contributing to the platform

Read the [delivery workflow](docs/project-management.md) and [application release contract](docs/application-release-contract.md). Application behavior/packaging belongs in the app repo; platform environment and controller changes belong here.

1. Select one bounded issue whose blockers are resolved. Claim ownership and set its review stage to Ready.
2. Branch from current main using `codex/<issue>-<purpose>`. An existing in-review scaffold PR may be updated within its scope.
3. For meaningful behavior, demonstrate a failing test before implementation. Use proportional checks for docs/configuration.
4. Run the same commands locally and in CI; record observations and resource impact.
5. Open a focused draft PR with issue, validation and limitations. Move it to In review.
6. Merge only with human authorization. Mark Done only when accepted evidence exists and delivery is merged.

Standard public hosted Actions runners avoid the public-PR risks of attaching a laptop runner. Keep jobs bounded and artifacts small. Do not add paid runners, capacity or credentials implicitly. Actual usage and provider terms must be checked when changing execution infrastructure.

Keep experiments bounded and record setup, baseline, trigger, result and cleanup. Store private account notes outside source. Logical Application/Platform teams share one human owner; claim an issue when starting rather than assigning the entire backlog.

## Small release follow-through

For a bounded application fix, use a Luna implementation pass with a behavior
regression demonstrated red before green, then request a focused Sol review.
Watch one authoritative release workflow run to completion; verify its source
commit and all seven immutable image identities against the reviewed platform
pins before syncing the existing Argo Application. Run the live API and browser
business journey, correlate sanitized request logs, and save a concise
checkpoint with the source/pin identity, outcomes, cleanup, session handoff and
lease expiry. Do not reset the dataset or extend the lease to make an acceptance
run fit. The
[first-application runbook](docs/runbooks/first-application-deployment.md)
contains the operator steps; dated results belong in
[deployment acceptance records](docs/acceptance/first-application-deployment.md).
