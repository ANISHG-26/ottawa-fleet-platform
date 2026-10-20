---
name: project-learning-guides
description: Maintain concise project refresher guides, root README architecture diagrams and short recorded application scenarios for a maintainer returning after a break. Use when updating learning documentation as a project grows; not for implementing features or declaring unmeasured milestones complete.
---

# Project learning guides

Help a maintainer returning after one or two weeks answer: what does this do,
how do the parts fit, what works today, and what should I do next?

## Establish the current picture

- Read repository agreements and existing root guides. Inspect current source,
  branches, relevant issues/PRs and dated evidence. Preserve unrelated changes.
- Identify the actual user journey and ownership boundaries. For multiple repos,
  keep application behavior with the app and infrastructure/lifecycle with the
  platform. Link across them instead of copying full runbooks.
- Compare current code, captured release and accepted evidence. A green build,
  deployment manifest or healthy pod is not proof of a completed business journey.
  Use explicit dates and distinguish implemented, measured, next and future work.

## Refresh the smallest useful entry points

- Put a two-minute refresher near the top of the root README. Explain the user
  outcome first, then a few visible capabilities and the next learning step.
- Keep a short root quick guide when the app needs a screen-by-screen tour.
  Link deeper architecture, setup and operating runbooks rather than restating them.
- Use a small Mermaid diagram to show the real connections and ownership. Label
  important edges and explain the diagram in plain language. Keep planned systems
  outside the current architecture or visibly marked as future.
- Include the data/lifecycle boundary when it changes how someone operates the
  system: durable work, safe retries, stale observations, or temporary lab expiry.
  Avoid a glossary of tools unless those terms help the next action.

## Record behavior when a short clip teaches it better

- Prefer the repo's existing Playwright recorder/tests and installed dependency
  versions. Use a real, authorized synthetic environment for integration claims;
  label fixture-only demonstrations clearly. Do not provision or extend a lab
  solely because a documentation task needs a recording.
- Choose a few short scenarios around observable user outcomes. Add readable
  on-screen captions and intentional reading time; keep clips understandable
  without audio. Assert the displayed result and relevant service state.
- Respect existing data. Preflight active work, bound any new scenarios, retain
  their history and clean up only owned temporary work. Record failure as failure.
- Save small intentional demo videos/posters in a stable repo location, with
  public-safe capture date, actual deployed source identity and scenario outcomes.
  Keep failed recordings, traces, credentials, cookies and raw logs out of Git.
- Link videos from the root guide. Offer a local HTML player if the repository
  host cannot play relative video links. Explain how to regenerate the clips.

## Verify and hand off

- Run the existing documentation/link checks. Render or parse diagrams and
  visually inspect the guide. Play every new clip; verify readable captions,
  correct final state, file size/duration and no sensitive information.
- Check related README summaries for contradictions introduced by the update.
  Keep historical records dated; do not turn this into an unrelated documentation
  rewrite or mark an outcome Done without its required acceptance.
- Follow the repo's issue/branch/PR workflow where required. Document what changed,
  what was actually verified, remaining limits and the next concrete step.
- For a returning-maintainer handoff, point to the short guide and diagram first.
  Suggest refreshing them when visible behavior, architecture or accepted progress
  changes; do not rerecord unchanged clips on every documentation edit.

For Ottawa Fleet, the app entry points are `README.md`, `QUICK_GUIDE.md`,
`WATCH.html`, `videos/recordings.json` and `web/guides/record.mjs`. Platform's
`README.md` is the architecture/progress entry point; dated acceptance records
live under `docs/acceptance/`. The shared board is the queue, not a substitute
for measured evidence. Keep this versioned skill and its installed copy aligned
when the skill itself changes.
