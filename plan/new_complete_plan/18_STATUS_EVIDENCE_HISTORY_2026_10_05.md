# Current implementation status — 2026-10-05 22:07 UTC

## Host recheck while resuming implementation — 2026-10-05 22:07 UTC

Host-level read-only verification: Story Builder API health is HTTP 200 and its existing launcher/backend/frontend processes are already running; do not start duplicate services. ComfyUI `/system_stats` responds and `/queue` is empty. NVIDIA reports **44°C / 2% / 2086 MHz**; the only compute process is ComfyUI PID 4112 (170 MiB). This is an idle point sample, not a render trace. The user reapplies the 300–2200 MHz lock after each power cycle; never change it, and keep Story Builder's stricter observed admission ceiling of 2100 MHz, intervention at 83°C and hard stop at 85°C.

Read the exact D5 run `65d3884b-0a07-4da6-9d02-21db48921336` in project `disposable-d5-two-scene-continuity-acceptance-2026-10-05-dedfec5c`: correction take `41f2cbf3-ef42-5305-aeb7-293dd44523e7` is still `recovery_required`, reserved prompt `e986422f-2d83-59d8-b8b3-9f3d4a9ac641`, with no registered hashes or Director review. ComfyUI queue and exact prompt history both show no record. These checks do not establish whether an unregistered local output exists or whether the operator confirms no usable output, so preserve the explicit recovery hold; do not retry yet. No GPU workload or service restart occurred.

Re-ran the maintained CPU backend suite against current source: **568 passed, 1 deselected, 4 existing FastAPI lifecycle deprecation warnings** in 29.54 seconds. The launcher suite was excluded because the user's services are already running; the detached-watchdog loopback test was deselected because sandbox socket creation is denied. No product test failed. Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/riki/web_dev /home/riki/miniforge3/envs/react/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_run_story_builder_launcher.py -k 'not detached_watchdog_survives_spawner_exit_and_interrupts_owned_prompt'`.

Pre-edit docs backup for the 22:07 status and handoff correction: `/tmp/storybuilder_acceptance_recheck_docs_preedit_20261005_2210.tar.gz`, SHA-256 `902ccd01e311bba632476e9a0b3d28e787871c412de52ced45005a90105e1cd6`.

## Latest dialogue-integrity regression follow-up — 2026-10-05

### Configured-provider dialogue → shot-plan acceptance — 2026-10-05 21:57 UTC

Ran the patched production API on a fresh disposable fictional project using the configured Codex provider (`codex` / `gpt-6-luna`), with project/storage/output isolated under `/tmp/storybuilder-dialogue-shotplan-acceptance-*`. Dialogue revision `dialogue-c2fa0e814f8d` was persisted and Director-accepted. Shot-plan revision `shot_plans-429ffcb14553` was also persisted and Director-accepted. Comparing the canonical saved revisions confirms the accepted line `{speaker_id: char-mira, text: "The water is rising."}` is copied exactly into the matching shot plan. Run: `12f39fc5-2eca-4da9-94af-395d1d745d51`; project: `disposable-dialogue-shot-plan-acceptance-040a3743`. No GPU, ComfyUI, real user story or existing project was used.

The first acceptance harness used the API's 8,000-character default and correctly failed before provider submission because its 6,456-character context left too little room for the structured prompt contract. Retried with the production controller's configured 16,000-character batch bound; both stages passed end-to-end. Treat this as harness configuration, not a product failure.

Provider-evidence docs pre-edit backup: `/tmp/story_builder_dialogue_provider_validation_docs_preedit_20261005.tar.gz`, SHA-256 `bc07c780ce0d5469b4e0c1f7ea1ee878e0c69a31d78984158634fbcec60d0c61`.

### Process-restart readback — 2026-10-05 21:58 UTC

In a separate Python process, reopened the same temporary project and ledger, queried the run and stage-revision APIs, and verified one accepted dialogue revision and one accepted shot-plan revision remained readable with the exact same speaker/text line. Ledger events include both `dialogue_revision_created`/`director_dialogue_review` and `shot_plans_revision_created`/`director_shot_plans_review`. This proves durable file/ledger readback across an application-process boundary for these stage artifacts. It does **not** prove worker task recovery, a live HTTP server restart, or browser restoration; those B1–B3 integration checks remain open. The observed run status is `draft` because this harness intentionally entered at the accepted-canon/text-stage boundary instead of starting the controller from the user's source story.

Pre-edit docs backup: `/tmp/story_builder_dialogue_process_restart_docs_preedit_20261005.tar.gz`, SHA-256 `24877dc4b0d600bf18a269d5a6849a83f7a40ec60ef9cebd98a935216086f3ce`.

The non-empty configured-provider run exposed an important input defect: each per-shot dialogue request still received a scene-wide `summary`/`dramatic_turn` and all shot beats, and one persisted candidate used `character` instead of the required stable `speaker_id`. The Director held that candidate, so it was not accepted and no downstream render was started. Updated dialogue context to contain only the matching stable shot beat plus bounded scene facts, and added validation before review/persistence requiring exact requested-shot coverage, allowed line fields, non-empty text/delivery, and a `speaker_id` present in that shot's stable character list. Updated the controller test fixture with matching shot IDs and added regression coverage for shot-scoped context and malformed speaker rows.

Verification: focused controller/chunk/API suites **132 passed**, 4 existing FastAPI lifecycle deprecation warnings. Maintained backend suite excluding launchers: **568 passed, 3 deselected**; the one loopback watchdog test was denied socket creation by the sandbox, then passed **1/1** when rerun with local loopback access. Combined: **569 passed, 3 deselected**. A first focused run caught two stale controller fixtures missing the new shot records; they were corrected, then the focused suite passed. No GPU work was submitted. No provider run was repeated yet; next verify non-empty dialogue with the configured provider, inspect the stored accepted revision, and keep any Director repair hold intact.

Clock note confirmed by user: after every power cycle, the user reapplies `sudo nvidia-smi --lock-gpu-clocks=300,2200`. Treat this as an operator prerequisite; do not change clock settings. Check telemetry immediately before and throughout any GPU workload, intervene at 83°C, and stop admission at 85°C.

Source/test pre-edit backup for this follow-up: `/tmp/story_builder_dialogue_scope_validation_preedit_20261005.tar.gz`, SHA-256 `2cd10ef81f5667ec1f032a7b74fc7c364b3ced73a5e30b7061dd75bbe6a9d3e7`. Restore selected files with `tar -xzf ... -C /home/riki/web_dev/story_builder <relative-file>`. Documentation pre-edit backup: `/tmp/story_builder_dialogue_validation_docs_preedit_20261005.tar.gz`, SHA-256 `987eeabefc918ce73c2ad2e495c3384f1aad7083f83d2f0e1d6305626c66ff21`.

Start with [00_READ_ME_FIRST.md](00_READ_ME_FIRST.md), this handoff, [16_SOL_REVIEW_2026_10_05.md](16_SOL_REVIEW_2026_10_05.md), and the relevant row in [11_IMPLEMENTATION_QUALITY_GATES.md](11_IMPLEMENTATION_QUALITY_GATES.md). Historical evidence is in [15_STATUS_EVIDENCE_HISTORY_2026_10_04.md](15_STATUS_EVIDENCE_HISTORY_2026_10_04.md) and the chronological implementation log. The implementation goal is active.

## Current coding milestone — shot-scoped dialogue integrity — 2026-10-05 21:18 UTC

Review of the persisted synthetic Full-mode provider run exposed a real producer/consumer mismatch: accepted dialogue had been generated scene-wide, while shot-plan validation required `content.dialogue` per stable shot ID. The shot-plan request exposed only a dialogue revision ID, so the provider had no accepted lines to copy and the durable task failed with `shot_plan_output_invalid` for missing `dialogue`. A prior attempt to pair scene beats and shots by list order was rejected after the fixture showed an extra departure beat; positional mapping is unsafe.

Changed the controller to request dialogue per planned shot, using its stable `unit_id`, shot outline and bounded scene context. The shot-plan task now receives those accepted lines directly, requires exact copying, and server validation restores the accepted `speaker_id` and text. Binding rejects missing/extra/duplicate shot IDs and cross-scene links. The prompt explicitly blocks later-scene events. Quality gates now require this producer-to-consumer contract and its edge cases.

Focused suites: **128 passed**, 4 existing FastAPI lifecycle deprecation warnings. Maintained backend suite excluding launchers: **565 passed, 3 deselected**, 4 warnings. At that point, configured-provider verification remained pending; see the newer evidence below. No GPU workload or telemetry check was needed or performed. The user reapplies `sudo nvidia-smi --lock-gpu-clocks=300,2200` after each power cycle; verify actual clock before supervised GPU admission.

Source/test backup: `/tmp/story_builder_shot_dialogue_preedit_20261005.tar.gz`, SHA-256 `30b7fcb2a540ea574b53ff336a3c3c1c2af4bda2de78105c5c09803bb82aceb8`. Restore a file with `tar -xzf /tmp/story_builder_shot_dialogue_preedit_20261005.tar.gz -C /home/riki/web_dev/story_builder <relative-file>`. Documentation backup: `/tmp/story_builder_dialogue_contract_docs_preedit_20261005.tar.gz`, SHA-256 `821f0f67a902a82bcac7928d010d2208e4f4538705486e75fd4d6ea82bec660f8`; restore the three archived paths from that archive.

## Configured-provider dialogue and shot-plan persistence — 2026-10-05 21:35 UTC

Ran a disposable synthetic Full-mode task using saved provider `codex` / `gpt-6-luna`, isolated under `/tmp/storybuilder-dialogue-contract-provider2-20261005-k7ozmikm`. Run `fbf34a0b-41cd-4017-a17e-bd5c675796c6` completed accepted scene, dialogue and visual-brief revisions; the shot-plan task completed and persisted `shot_plans-4d3df9e311d6`. Canonical revisions prove exact set equality across 4 planned shot IDs, dialogue unit IDs and shot-plan unit IDs, and each shot-plan `content.dialogue` exactly equals the accepted shot-scoped dialogue. All four dialogue arrays were empty, so this live-provider check verifies no-speech mapping; non-empty line preservation remains covered by API/controller tests and needs a live provider case for full acceptance.

The shot-plan revision remains `pending_director_repair`: the Director held shot-001-02 for blurred event order/underspecified blocking and shot-002-02 for unsupported connective actions. This review hold was not overridden. The flow stopped before prompt preparation or GPU rendering. A first synthetic run with weaker location wording was held by identity reconciliation; its single bounded retry repeated the same failure, so that run did not reach dialogue. No D5 content, live API process, ComfyUI queue or GPU workload was touched.

Next: the later acceptance recorded below has already verified a persisted, non-empty dialogue line copied exactly into its Director-accepted shot plan, so do not repeat that narrow test. Continue B1–B3 with a genuine durable controller run from a fictional source story through all required stages, preserving every Director hold; then exercise the changed worker/restart/replay and browser journey against persisted API/SQLite state. The older shot-plan repair hold above remains valid evidence and must not be bypassed. Keep D5 story content out of provider requests until the required authorization is explicit.

## Configured-provider run and real browser restoration — 2026-10-05 20:39 UTC

Used the explicitly synthetic C2 fixture with the saved configured provider (`codex` / `gpt-6-luna`) for one text-only story-detail task. Run `022e2cbd-b072-4bfb-82ae-1601d96f88b0`, task `f4787af0-f8c5-41e7-980f-2d0729645ced`, persisted revision `story-canon-80c604e40422`; the proposal is still `pending_review` and was not accepted. A real Playwright session on system Chromium reopened that persisted run in the live Production Workspace at 390×844, verified the exact saved synthetic text, pending-review state and visible review action, and reported no page errors. This proves provider task persistence and browser restoration for the story stage only; it does not prove decision replay after process restart or downstream stage acceptance. No D5 content or GPU work was used.

## Latest regression recheck — 2026-10-05 20:34 UTC

Re-ran the maintained CPU-only backend suite after the recovery loop and bounded event-history changes: **560 passed**, four existing FastAPI lifecycle deprecation warnings, 31.11 seconds. Launcher tests were excluded because the user’s Story Builder server is already active on port 3010; no service was restarted.

Host-level read-only check: GPU **45°C / 7% / 2086 MHz**, sole compute process ComfyUI PID 4112; ComfyUI `http://127.0.0.1:3008/queue` is empty and Story Builder health is 200. No GPU work was submitted. User reapplies `sudo nvidia-smi --lock-gpu-clocks=300,2200` after every power cycle; agent does not change clocks.

The D5 run `65d3884b-0a07-4da6-9d02-21db48921336` still has three accepted takes and correction take `41f2cbf3-ef42-5305-aeb7-293dd44523e7` in `recovery_required` with prompt `e986422f-2d83-59d8-b8b3-9f3d4a9ac641`. Preserve the hold until the requested operator confirmation is received; no retry was submitted.

## Latest coding milestone

### Recovery event loop and unbounded run-history read — 2026-10-05 20:21 UTC

Live persisted-ledger inspection found that the missing reserved ComfyUI prompt for take `41f2cbf3-ef42-5305-aeb7-293dd44523e7` had generated about **3.8 million** identical `comfy_state_reconciled` events. The recovery worker queried history without checking the queue, recorded unchanged “absent” observations on every pass, and skipped its idle backoff whenever reconciliation observed a candidate. This could misclassify a still-queued prompt and caused heavy SQLite/WAL growth and API contention.

Fixed the worker to validate both ComfyUI queue lists before history, defer on malformed/unavailable queue responses, retain queued prompts as owned, make unchanged reconciliation idempotent, and back off when no take/review work is active. Run-detail reads now return only the newest 500 events in chronological order and expose `event_history_truncated`; SQLite retains the full event history. Focused ledger/worker/reconciliation tests: **46 passed**. Maintained backend suite excluding launchers: **559 passed, 1 failed**; the remaining real-socket watchdog test is blocked by sandbox `PermissionError` creating a localhost listener, not by a product assertion.

Live verification: the old 3010 server had been running the pre-fix code, using about 41% CPU, and a D5 run GET timed out after 8 seconds. Read-only ledger checks found no active/queued take or durable stage task, ComfyUI queue was empty, and telemetry was 47°C / 1% / 2086 MHz. Restarted Story Builder through `run_story_builder.sh` using the project `react` Python environment; ComfyUI and Ollama stayed running. The fresh API health check returned 200, and the same D5 GET now returns HTTP 200 in **0.010 seconds** with 500 events and the truncation flag. Two reads three seconds apart returned the same latest event timestamp (`2026-10-05T20:15:37.367881+00:00`), confirming the reconciliation event flood stopped after reload. Latest telemetry: **45°C / 1% / 2086 MHz**; ComfyUI queue remains empty. Current API PID 1077394. Historical event rows remain preserved; do not purge or vacuum this 2.45GB database as part of the feature fix.

Source/docs backup before the bounded-history change: `/tmp/story_builder_event_window_preedit_20261005.tar.gz`, SHA-256 `d0dcd6760e35f3baed5a2834cab1503c0d4cb194f356cfcc09de96c0984c808`. The earlier reconciliation source backup is recorded in the implementation log. User reapplies the 300–2200 MHz lock after power cycles; do not change clocks. No GPU workload was submitted.

### D5 saved-output integrity and browser playback — 2026-10-05 20:28 UTC

Checked the three existing accepted outputs without rendering: each canonical file exists, its SHA-256 matches the ledger, and `ffprobe` reports a 5.167-second H.264 video plus stereo 32-kHz AAC audio. The existing live playback Playwright test incorrectly required an “Accept take” button even for an already accepted take; made that assertion status-aware (reviewable candidates require it; accepted takes must show accepted state and no acceptance action). Real browser test against cut-03 with system Chromium: **1 passed**, including narrow viewport, saved run/take restoration, registered video playback advancing by >0.2 seconds, and no page/API errors. The cached Chromium lacks H.264/AAC and correctly skips this codec-gated check. The test file backup is `/tmp/story_builder_live_playback_test_preedit_20261005.tar.gz`, SHA-256 `e44dad4bcf043362bbde02eec06eac48b83070a1b1fd476f39ce149b61ffc903`.

This verifies only the existing accepted cut-03 playback and output integrity; the correction take for cut-02 remains `recovery_required` pending explicit confirmation that the exact reserved prompt produced no usable output. Do not retry it until that confirmation and a fresh supervised GPU preflight. There is no GPU workload running.

The saved take snapshots also prove D5 lineage: accepted cut-02 references the accepted cut-01 tail `[3.167, 5.167]` seconds with `previous_cut_tail`; accepted cut-03 begins the new scene with no parent take and an empty video-reference map. Same-scene continuity and fresh-scene reset are therefore verified from the submitted snapshots, independently of visual quality. The cut-02 dialogue/audio concern still needs the bounded correction and human review.

Shot-plan generation now receives the exact supported role keys from the same registry used by validation. Its prompt requires an exact listed key and permits an empty `asset_intents` array. Generated shot-output validation now names the unit and invalid fields, and marks provider-generated schema/role/H3-lint failures retryable. After a durable failure, the controller may create one new task with the identical frozen request and a new idempotency key; a second failure remains held. No media side effect or revision is retried.

Verification: focused suites **134 passed, 4 existing FastAPI lifecycle warnings**. Maintained backend suite excluding live-launcher tests **554 passed, 4 warnings**. The unfiltered suite had 3 launcher failures because they detected the user's existing Story Builder backend on port 3010 and correctly refused duplicate startup; that service was left untouched.

## Persisted configured-provider evidence

Fictional text-only runs were used; no D5 user story was sent and no GPU render was queued. v14 stopped at Director review because an unnamed keeper could not be linked to a stable identity. v15 accepted the story/outline but Director held the scene revision; after dialogue and visual briefs completed, shot-plan generation failed on required output fields under the earlier non-diagnostic handler. v16 likewise stopped at a Director scene-quality hold and did not reach shot plans. These runs are not end-to-end acceptance. The new invalid-field retry is verified by the SQLite controller regression, but not yet live-provider verified. Isolated v16 API was stopped after the run; see the archived handles and evidence in the implementation log.

## GPU and clock handling

The user manually applies `sudo nvidia-smi --lock-gpu-clocks=300,2200` after power cycles. Do not set or change clocks. Latest read-only sample at 19:49 UTC: **46°C, 3% utilization, 2086 MHz**; only ComfyUI PID 4112 was listed as a compute process (170 MiB). No GPU workload ran during this milestone. This is a point-in-time idle sample. Before any GPU work, recheck temperature, utilization, actual graphics clock, process owners and ComfyUI queues continuously; keep the plan's 83°C intervention trigger, 85°C hard ceiling and 2100 MHz observed-clock admission limit.

## Remaining original plan gates

| Workstream | State and next evidence |
|---|---|
| A0–A5, B4, C1, C3, D1, D3, E1 | Foundation gates are implemented with recorded tests; retain them in the final release sweep. |
| B1–B3 | Durable queue/controller foundations and CPU tests pass. Complete configured-provider acceptance through review, restart/replay and browser persistence; preserve any Director hold. |
| C2, C4 | Candidate/TTS/sidecar foundations and saved-output evidence exist. Remaining live worker/review/restart and human audio-quality checks remain; do not infer them from CPU tests. |
| D2, D4 | Manual worker/recovery foundations and baseline live cancellation/restart checks are recorded. Complete changed controller/provider restart, persisted browser decision/retake journey, and human listening where required. |
| D5 | Reuse the existing disposable two-scene fixture. Reconcile its current ledger and exact prompt before any retry; then complete supervised same-scene continuity, scene reset, playable output/audio, provenance and review. Do not recreate the fixture or send D5 story content to a provider unless separately authorized. |
| E2–E3 | Re-run affected release checks after remaining changes and finish the operator walkthrough. Keep the existing navigation/migration feature switch behind D5 acceptance. |

Use the four bounded work packages and **10–20 focused-hour planning estimate** in the Sol review; do not add optional features. Preserve existing completed H3 evidence and rerun it only for changed paths or required release acceptance.
