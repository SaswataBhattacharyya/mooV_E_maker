# Sol follow-up implementation review — 4 October 2026

## Scope and outcome

Reviewed work since `13_SOL_REVIEW_2026_10_04.md`: automatic text-stage progression, identity/voice handoff, canonical revision recovery, guarded provider execution, saved-run/manual-source UI, T2V and cancellation settlement, shot-reference catalog, and the unfinished `generate_resolved_shot_prompt` helper applied immediately before the user requested a pause. Compared current files with the retained review archive and subsequent status/log evidence. This directory has no Git history, so authorship and a complete commit-by-commit comparison cannot be established.

The review and repairs are complete. The implementation goal remains paused at the user's request; this review does not resume it or declare the production plan complete. Current gates remain in `12_CURRENT_STATUS.md`. No delegated-render API gate was opened, and no GPU workload was submitted.

## Confirmed defects repaired

| Priority | Trigger / consequence | Repair and evidence |
|---|---|---|
| P1 | A second accepted story revision in one run reused the previous revision's outline and downstream tasks. A retryable old scene task could be retried instead of outlining the new story. | Scope downstream lookup and retry candidates to the exact `source_revision_id`. Real temporary SQLite regression proves a new outline is queued for the new canon, the old failed task is not retried, and repeated scanning does not duplicate the outline. |
| P1 | Shot drafting accepted provider-authored `reference_map` / concrete asset IDs, allowing self-invented tags to pass lint. A Director content repair was persisted without rechecking the shot schema, so empty prompts, invalid durations or forged wiring could become accepted revisions. | Generated outlines cannot carry executable reference wiring or asset IDs in role intents. Lint uses an empty compiler map at this pre-resolution stage. Revalidate before review and after repair, before canonical persistence. Require declared arrays and structured records; reuse the shared content validator for supported roles and limits, and reject blank intent text. Seven API regressions prove invalid drafts/repairs persist no shot revision. |
| P2 | A generated project-output master without `image_candidate` role and without explicit acceptance appeared in the supposedly approved catalog. Final route validation rejected it, but planning was already using incorrect availability context. | Require explicit approval or the existing completed/accepted-role legacy evidence for generated images. Catalog regression covers the missing-candidate-role case. Catalog context still grants no permission to queue an asset. |
| P2 | The interrupted prompt helper trusted malformed maps, used the caller's mutable map after snapshotting, and could accept omitted/changed dialogue when a provider approved it. Boolean confidence and approval with unresolved issues also passed. | Strict compiler-map structure and paired/speaker consistency; deep-frozen JSON context; deterministic exact dialogue/speaker/order/language checks; finite numeric and strict writer/reviewer schemas; at most one targeted repair followed by review; unresolved issues prevent acceptance. Tests cover real compiler tags including paired audio, immutable IDs, semantic repair, invalid inputs, changed/extra speech and stale corpus. This remains an **unwired GPU-free primitive**, not a durable Full/Semi controller. |
| P2 | Existing story/text Director reviews treated JSON `true` as numeric confidence 1; a list-valued decision caused an unstructured `TypeError`. | Require actual finite numeric confidence and string decision before enum lookup. Four regressions cover both reviewers. These defects predated the unfinished helper and were found while checking its neighboring acceptance branches. |
| P2 | The alternate read-only ComfyUI reconciler omitted the confirmed-interruption flag. A user-cancelled take could settle `failed` even though the main worker/supervisor path handled cancellation correctly. | Share interruption-event recognition with the worker and propagate the flag through the exact saved prompt's history observation. Real ledger regression proves terminal `cancelled`. The existing distinction between cancellation intent and a real render error remains. |

Initial targeted reproduction: **11 failures**. Additional strict-review reproduction: **4 failures**. Final generated-schema reproduction: **3 failures**. All reproduced cases now pass. Successful and negative cases bring the new review regression file to **36 tests**; no ordinary test calls physical GPU, Docker, ComfyUI, or a real reasoning provider.

## Work/gate assessment

- B1–B3 have added durable accepted-stage progression and task-matched canonical recovery since the first review. CPU subprocess tests demonstrate executor fencing and local guarded CLI exit; real configured Codex inference/remote-result reconciliation remains unaccepted.
- Identity handoff, seeded automatic voice bindings, the saved-run selector and manual-source canon path are implemented and tested. These do not constitute complete image/render orchestration.
- H3 worker restart recovery and owned cancellation, Direct Video Repertoire cancellation, live dialogue FLAC and saved candidate playback have retained evidence in current status. The two cancellation CSV files are still present. This review does not repeat those live tests or replace their limitations.
- Full/Semi initial reference selection, durable prompt preparation/initial take dispatch, complete review/retake/browser integration, D5 two-scene/two-character/two-cut acceptance, human dialogue listening and final release/walkthrough remain open. Preserve completed baseline H3 evidence.
- The external Codex rules file still contains **181 NUL bytes**. User authorization covers inspection and a minimal repair proposal only. It was not modified, and no provider substitution was made.

## Context continuity configuration

The user requested automatic compaction around 60% context used, plus global guidance. Added `model_auto_compact_token_limit = 155040` and `model_auto_compact_token_limit_scope = "total"` at the top of `/home/riki/.codex/config.toml`. The installed model catalog records Sol/Luna windows of 272000 tokens with 95% effective capacity: `272000 * 0.95 * 0.60 = 155040`. No model/window value was changed. This is a fixed token threshold for these models, not a percentage setting that adapts to every possible model.

Created `/home/riki/.codex/AGENTS.md` with the 60%-used preference and a concise milestone-handoff requirement. It explicitly forbids claiming that a prose summary compacted the runtime or inventing usage percentages. Global instructions are already being loaded into this chat. TOML validation and the installed `codex features list` command pass; no inference was started. The exact automatic trigger in this already-running chat was not exercised; the runtime must reload/honor configuration for it to apply.

Official configuration reference: [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference), documenting the compaction token threshold and full-context scope.

## 2026-10-05 continuation update

The interrupted helper was subsequently wired into a durable SQLite `controller:resolved_shot_prompt` task, with accepted-shot/run/provider/corpus/compiler-map/fingerprint snapshots, fenced worker revalidation and optional exact task binding on human take submission. Production Workspace now creates/polls/restores this task, exposes the accepted result for human review/edit, revalidates the final prompt before queueing and includes the task ID only for an unchanged result. The focused mocked browser journey and complete mocked browser suite pass (**21 passed, 1 skipped**; opt-in live playback was unset). Latest backend checkpoint is **511 passed**.

Per-shot catalog-ID resolution is now connected to the fenced prompt task: it snapshots and rechecks the approved catalog, runs a CPU-only provider selector, validates the output against the registry/compiler, and returns exact request/map data to the browser. Mocked real-SQLite worker acceptance passes; configured-provider acceptance is unverified. The next gates are automatic Full/Semi initial take scheduling/dispatch, exact task binding for Director-owned take creation, one-shot-at-a-time progression, restart/replay, review/retake and D5 acceptance. The reviewed primitive and human UI do not open the delegated-render gates. Real configured-provider inference/restart remains blocked before inference by the unchanged Codex rules-file NUL problem; no GPU work occurred in this coding continuation.

## Validation and execution scope

Final maintained backend suite: **508 passed**, four existing FastAPI lifecycle deprecation warnings. Frontend typecheck/production build pass; Vitest **11 passed**; ESLint **0 errors / 13 existing warnings**; full mocked Playwright **21 passed, 1 skipped**. The skipped test is opt-in live saved-take playback with unset environment variables, not a passed live release gate. A legacy ManualDirector React list-key warning appeared during navigation; this review did not establish a new source defect behind it. No frontend source changed in these repairs.

Commands used the existing `react` Python environment and installed npm dependencies. Host permission was used for localhost test fixtures, build output and the temporary Vite server. Backend fixtures use real temporary SQLite/files; provider/ComfyUI responses are controlled fakes. The temporary Vite session was stopped after the browser suite.

```sh
PYTHONDONTWRITEBYTECODE=1 /home/riki/miniforge3/envs/react/bin/python -m pytest -q -p no:cacheprovider
npm run build
npm run lint
npm test
npm run dev -- --host 127.0.0.1 --port 4180 --strictPort
./node_modules/.bin/playwright test --workers=3 --output=/tmp/story-builder-sol-followup-browser-20261004
codex features list
```

Read-only authorized host check: **50°C, 2% utilization, 2086 MHz**, ComfyUI **0.30.0 on port 3008**, empty running/pending queues. This is an idle snapshot, not render supervision or diagnosis of the earlier PC shutdown. Live policy remains 83°C intervention, 85°C maximum, 2100 MHz clock ceiling, exact prompt ownership and continuous telemetry.

Logs: `/tmp/story-builder-sol-followup-backend-final-20261004.txt`, `/tmp/story-builder-sol-followup-build-20261004.txt`, `/tmp/story-builder-sol-followup-lint-20261004.txt`, `/tmp/story-builder-sol-followup-vitest-20261004.txt`, `/tmp/story-builder-sol-followup-playwright-20261004.txt`. Browser artifacts: `/tmp/story-builder-sol-followup-browser-20261004`. Codex parse check: `/tmp/story-builder-sol-followup-codex-config-check.txt`.

## Backup and restoration

Pre-edit archive: `/tmp/story_builder_sol_followup_review_preedit_20261004.tar.gz`, SHA-256 `288c54fcfb7a1e36adad46f50371d04ef680a88d5a0e353277ef5223239df5fe`. It contains affected original source/tests, project instructions/status/log, and the original global config as `global/config.toml`. Verify with `sha256sum`, inspect with `tar -tzf`, then restore **selected project-relative entries only** with `tar -xzf <archive> -C /home/riki/web_dev/story_builder <entry>`, after comparing later changes. The newly created review/test/global-instruction files are not in the archive. Restore global config separately through a temporary extraction of `global/config.toml`; do not extract the entire archive into either root.

The interrupted helper was applied before pause without recorded tests/log or its own recorded pre-edit backup. This review backs up that exact paused state, repairs it and supplies the missing evidence; it does not invent an earlier restore point.

## Status entry-point maintenance

Shortened `12_CURRENT_STATUS.md` from 90 KB to the current review, gate table and next coding sequence. The complete preceding snapshot is retained in `15_STATUS_EVIDENCE_HISTORY_2026_10_04.md`, explicitly labelled historical. This reduces restart context consumption without dropping evidence. The project entry point routes historical lookup through focused search.

## Luna restart instructions

Resume only when the user explicitly resumes the implementation goal. Read this file, current status, the quality gates and the relevant D2/B3 task requirements.

1. Treat the approved catalog as context only. Resolve actual per-shot IDs against the registry and immutable route policy, including run-bound voice excerpts and accepted same-scene previous-cut tails. Fresh scenes reset video references. Keep asset-selection authority separate from prompt-writing authority. Shot validation now rechecks registered media roles; voice excerpts must match the bound source-master hash and current run.
2. Use the GPU-free map-only shot-validation mode to obtain tags from the selected, registry-checked ordered slots before final prompt generation. Its result is explicitly not final prompt validation and the take queue refuses it. The `controller:resolved_shot_prompt` task pins the map/fingerprints, accepted shot-content hash, source-story hash, run config/provider and corpus snapshot; its worker revalidates and saves the reviewed result in fenced SQLite. Human-controlled take submission can require that task and rejects a substituted prompt or changed references. Real provider inference/restart remains unverified.
3. Full/Semi catalog selection, durable prompt preparation, exact preparation binding, initial idempotent take dispatch, and the queued-take browser consumer are implemented with CPU/SQLite and mocked browser evidence. One accepted shot at a time is now scheduled; same-scene children bind the immediate accepted parent and hash-verified canonical video, and a new scene resets both. Preserve tests for stale plan, wrong scene, unknown/duplicate/unsettled take, forged/missing media and changed parent replay. Do not treat this as live acceptance.
4. Fresh retake preparation and replay-safe decision resolution now have CPU/SQLite coverage. Continue with actual configured-provider/worker acceptance, render-time process restart/reconciliation, browser review/decision/retake polling and playback, and supervised GPU acceptance. Use real local SQLite and registry files for success/restart/negative tests. Keep both delegated-render 409 gates closed until the entire producer-to-browser path passes. Do not bypass the still-unrepaired user-level Codex rules file or switch providers without authorization.
5. Only then run the configured-provider/live gates, once the external rules repair is explicitly authorized and verified. GPU tests require healthy admission and independent continuous prompt-owned monitoring. Complete the remaining card/release gates without substituting a mock pass or an unwired helper for live acceptance.

Record the milestone handoff and review error/restart branches before advancing each capability. Create the compressed backup before the first edit, including a bounded partial change that might be interrupted.
