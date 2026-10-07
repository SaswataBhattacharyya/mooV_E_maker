# Sol completion review — 6 October 2026

Scope: Luna's recent retry/recovery/image-review changes and the four original remaining acceptance packages. This is a completed local code review with repairs and actual configured-provider execution; no claim that a spawned independent Sol reviewer ran this turn. Original scope remains fixed.

## Confirmed defects and repairs

1. `scripts/retry_durable_text_stage.py` treated any socket OSError as proof the API was stopped. Permission errors, timeout and network uncertainty now fail closed; only connection refusal proves the listener is absent.
2. The same runner reported exit0 for a completed but Director-held stage. Success now requires the accepted canonical revision with matching project/run/stage/revision/task/request hash/provider/model and matching durable completion provenance.
3. Image reassessment replay bypassed the saved image hash after a crash between decision persistence and acceptance. Both pending replay and accepted reassessment readback check bytes. The regression interrupts acceptance, reopens SQLite, changes the file, verifies both replay paths stay held with no inference, restores it and completes once.
4. Video Director acceptance had the same replay omission. Saved decisions with byte provenance now verify the video before promotion; changed bytes stay held with the immutable decision pending. Reopened real-ledger regression passes without a second inference.
5. A complete shot-plan stage could remain held after one unit exhausted its built-in content repair, leaving no targeted continuation that preserved four approved siblings. Added explicitly requested `repair_from_revision_id` path through the ordinary lease/fence worker: require latest held complete shot plan before takes, select only held units, preserve identities, pass exact old content/issues, validate final content, merge approved siblings unchanged into a new immutable revision. The operator tool is dry-run-first and uses one stable spent key. No automatic extra retry or whole-story replay. Added writer/repair instruction to mark inferred actions, camera and ambience explicitly.

Verification: retry/image suites72passed; API/generation/Director/task143passed; video Director/worker35passed. Four existing FastAPI lifecycle warnings in API suites. No frontend source change. Backups were taken before affected edits; source is not a functioning Git checkout.

## Actual progress

The explicitly authorized stage-only Sol attempt saved five generated units and four approvals. Targeted repair of the fifth was separately approved and succeeded: task `aaac19c9-d390-4c46-8da5-2a99e5ba8bdc`, accepted `shot_plans-e6672616eca3`. Real canonical provider/model/task hash persisted. Accepted source text stages and four siblings were reused. Both processes settled; no GPU work or normal API startup occurred.

This durable run is Direct H3. Reference-built image-to-take remains a separate existing run, not an excuse to replay the passed Direct text chain. The four completion packages remain as listed in current status. D5 cut01 audio has contradictory user/ASR evidence, so playback and accepted badges cannot close its release gate. Keep navigation default-off. Do not count fictional fixture media as live provider/GPU evidence.

## Instructions for Luna and the next continuation

Use current status, exact task/revision and stable key; never replay either spent operator retry. Task completed is not Director accepted. Uncertain host probes are not successful checks. A saved media decision applies to exact reviewed bytes and must be verified again before recovery side effects. Preserve approved units; repair only held ones in a new parent-linked revision. Record closed artifacts/gates and concrete next exits rather than only test totals. Stop adding scope or repeating passing suites when another gate is waiting. A new pending provider-flow question is permission scope, not evidence of unavailable hardware.

## Backups and restoration

- `/tmp/storybuilder_sol_retry_review_20261006.tgz`, SHA256 `8ded4dc40df381c1484a5f6c701da2048a9f8c3d4c6b868569837ebe94c9c415`.
- `/tmp/storybuilder_image_review_replay_preedit_20261006.tgz`, SHA256 `39af84960ed0e6a1248827897fc161ad3282f711fda358a571e8efe00b3d363f`.
- `/tmp/storybuilder_targeted_shot_repair_preedit_20261006.tgz`, SHA256 `bf9e0f1f4e61c970cefc73b30fc61e32db5344f4d17f51932f1305dd8b3d6b8c`.
- `/tmp/storybuilder_video_review_replay_preedit_20261006.tgz`, SHA256 `4f75a5836b686359af70155eba3e9ce0dee7bf39f6b02bce79b3afb0fd9e180a`.

Compare newer changes, then extract selected relative entries with `tar -xzf <archive> -C /home/riki/web_dev/story_builder <relative-entry>`. The new helper and runner have no pre-existing version; preserve their newer evidence before removing them if rolling back. No media or live ledger was reverted.
