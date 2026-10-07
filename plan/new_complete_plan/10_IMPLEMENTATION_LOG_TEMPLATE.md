# Implementation log template — copy to IMPLEMENTATION_LOG.md when coding starts

Do not mark a card passed based on code review alone. Record reproducible evidence and keep failed/optional gates visible. This template is not a claim that implementation has begun.

## Baseline and safety

- Date/time, operator, repository/worktree state:
- Backup archive, included paths, restore command, checksum:
- Existing website/backend/ComfyUI/Conda/Docker health:
- Baseline tests and results:
- Local H3 model, node and `/object_info` versions:
- Feature-flag/rollback state:

## Per-card record (repeat for A0 through E3)

### Card ID and title

- Status: not started / in progress / passed / failed / unavailable (reason)
- User-visible behavior intended:
- Changed paths (and any unexpected touched paths):
- API/graph/schema versions and migrations:
- Tests run (exact commands) and pass/fail counts:
- Live output paths and FFprobe facts, where required:
- Playwright spec/browser/trace/screenshots, where required:
- GPU peak, wall time, model unload result, where required:
- Regression checks for every touched working feature:
- Failure evidence, diagnosis, mitigation and remaining limitation:
- Rollback procedure verified:
- Next card unblocked? yes/no, with reason:

## Final acceptance table

| Gate | Evidence path/command | Result | Limitation or owner |
| --- | --- | --- | --- |
| Dynamic H3 same-video frames + paired audio + standalone voice | | | |
| Reference-number map and no unused/miswired slots | | | |
| Mandatory story and Director chunk completeness | | | |
| Manual, Semi and Full modes | | | |
| Direct H3, Reference-built and Hybrid routes | | | |
| Project assets, voice bindings and one-copy storage | | | |
| Two-scene/two-character/two-cut live generation | | | |
| Frontend build and affected backend regressions | | | |
| New and existing Playwright suites | | | |
| No changed ComfyUI/Conda/Docker or unapproved model install | | | |
| Cleanup, GPU unload, rollback and operator instructions | | | |

Finish with a concise list of what is live, what remains capability-gated, and any action required from the user. Never say “complete” while a mandatory gate is only mocked or untested.
