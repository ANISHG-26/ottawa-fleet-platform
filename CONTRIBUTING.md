# Contributing

Start with one GitHub issue describing a bounded outcome, acceptance criteria and evidence. Use the Project board to show sequencing and review state.

1. Branch from current main using codex/<issue>-<purpose>.
2. For meaningful service behavior, write a failing test before implementation. Documentation uses proportional validation.
3. Run the same check commands locally and in CI.
4. Open a focused draft PR with issue links, behavior, validation and limitations.
5. Move work into review. Human authorization is required to merge. Do not mark live experiments complete before evidence exists.

Standard hosted Actions runners are free for public repositories; larger runners are billed. Keep artifacts small and short-lived and do not increase cache limits. [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Use hosted runners for public PRs. Do not attach a laptop self-hosted runner to untrusted public pull requests. Local builds can use the same commands without registering a runner.

Subagents own separate files or modules and bounded acceptance criteria. Review their output before integration. Keep credentials, billing identifiers and personal deliberations outside public issues, logs and artifacts.
