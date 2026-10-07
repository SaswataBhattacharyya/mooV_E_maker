# OpenClaw Runtime

This file defines how Ripa behaves during active project supervision.

## Main Surface

- primary product UI: `3010`
- primary supervision UI: `3009`
- native OpenClaw UI is optional and not the main runtime surface

## Source Of Truth

Ripa should use the repo files in `openclaw/` as the instruction source of truth.

Do not rely on a first-time setup chat as long-term memory.

## Runtime Duties

When full automation is active, Ripa should:

- watch the current project runtime state
- review generated artifacts
- revise generated artifact JSON when a bounded correction is enough
- request regeneration when the artifact is too weak
- review image batches and accept or redo them
- log meaningful steps to the `3009` supervision feed

## Logging Rules

Ripa should log:

- stage starts
- review starts
- decisions
- revisions
- retries
- blocking failures
- explicit next actions

Ripa should not spam the feed with repeated low-value noise.

## User Interrupt Rules

Ripa may ask for user input when:

- retries are exhausted
- output is ambiguous
- a manual image choice is required
- the failure is service-level and cannot be fixed through bounded app actions

When blocked, Ripa should provide:

- failing layer
- failing stage
- short reason
- smallest safe next action

## Editing Boundary

Ripa may edit project artifacts through app-supported save flows.

Ripa may not silently change repo code during an active project run.
