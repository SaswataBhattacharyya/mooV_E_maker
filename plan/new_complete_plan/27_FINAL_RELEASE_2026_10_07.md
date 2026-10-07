# Original plan release — 7 October 2026

The required upgrade is implemented and its representative live acceptance gates passed. The final audit is [FINAL_PLAN_ACCEPTANCE_20261007.json](evidence/FINAL_PLAN_ACCEPTANCE_20261007.json). Historical failed/interrupted attempts remain preserved and are not counted as release outputs. This release keeps optional unverified models disabled; it does not include final-film stitching or rendering every planned shot.

## Original execution cards and exit evidence

| Cards | Implemented requirement and evidence |
| --- | --- |
| A0–A3 | Baseline archives and original graph protection in IMPLEMENTATION_LOG; typed project-scoped references, deterministic loader/tag compiler, same-loader paired audio, media timing/presets/owned cleanup. test_minimax_h3_graph_compiler.py, test_minimax_h3_media.py, smoke cleanup/recovery suites. |
| A4–A5 | Retained live voice-only/image+voice/video-no-audio/mixed/paired-video-two-voice and same-scene smokes; feature-gated truthful capability tests. Actual paired example below. |
| B1 | SQLite idempotency, durable claims, dependency/recovery/cancel/retake and owner fencing: production ledger/reconciliation/job-worker suites plus actual restart/browser evidence. |
| B2–B3 | Required story, chunk completeness, accepted canon revisions, configured Codex text/shot/prompt path; typed Director/Refine contracts. story-revision/stage-task/text-controller/chunked-generation/director-contract/refine suites and accepted Full manifests. |
| B4 | Six legacy styles, immutable sourced variants and Director profiles; style catalog/library/source/automation tests and maintained picker browser regressions. |
| C1 | Scoped assets, hashes, safe content/upload paths, one-copy Repertoire links/shared deletion preservation: asset/route suites and persisted-assets browser evidence. |
| C2 | Distinct Qwen2512/Z-Image/QwenEdit2511 graphs, exact preflight and retained live smoke hashes; actual Full three-master durable review/assignment. Image workflows/jobs/director/worker suites and Reference manifest. |
| C3 | Independent Direct/Reference/Hybrid master requirements and world/character state; actual Direct no-master and Reference accepted-master paths. FL2VA explicitly disabled/unverified. |
| C4 | Stable eligible local voices and saved seeded choice, local dialogue TTS/recorded take and optional sidecar contracts with native H3 audio preserved. Voice binding/excerpt, dialogue TTS/API, audio sidecar and legacy audio suites; actual paired-two-voice smoke and D5 reviewed speech. Hosted cloning remains separately gated. |
| D1–D2 | Revision/refine/reference validation, immutable provider preflight, accepted predecessor/changed draft holds, bounded review/retake/cancel/recovery. Actual Full continuation/replay and real worker/browser restart/cancellation plus shot-plan/validation/runtime/video-director suites. |
| D3–D4 | Story/assets/voices/composer/queue/review/player and saved navigation; deterministic maintained browser tests, actual persisted native playback/reload, mobile/keyboard/legacy regression coverage. |
| D5 | Real two-scene three-cut acceptance, native audio, scene reset and corrected-parent compatibility: D5_RELEASE_20261006.json. New navigation enabled only after all release gates passed; legacy retained. |
| E1 | Maintained Python and strict ports, simultaneous launch/missing-runtime regressions; three launcher tests and actual healthy normal launch with ComfyUI/Ollama reuse. |
| E2–E3 | Final803backend/14frontend unit/24browser plus separate actual acceptance; typecheck/build/lint, real flags and normal navigation; README/operator/current handoff/rollback updated. |

Test module names refer to `tests/` in this repository; suite-level proof is distinct from native model quality. Detailed phase logs, backups and earlier reviews remain in IMPLEMENTATION_LOG,13/17/21/24 checkpoints and historical status archives.

## Actual compiled graph and media

Paired video plus two standalone voice example:
`output/disposable-h3-reference-smoke/runs/phase-a-20261003T043800Z-877abe79/compiled_graph.json` and adjacent `manifest.json`. Video1 and Audio1 are the same selected video interval0.2–5.2s; S1→Audio2 and S2→Audio3 are the standalone voices. The compiler uses one video loader's image/audio outputs;17nodes retain native video/audio decode/save. Other retained matrix results and exact original graph hashes are recorded in the implementation log.

Release manifests contain actual output paths, hashes, stream details, accepted decisions, browser and monitoring artifacts:

- [D5_RELEASE_20261006.json](evidence/D5_RELEASE_20261006.json): three5.167s native clips, corrected first cut, compatible preserved second, fresh-scene third.
- [FULL_DIRECT_ACCEPTANCE_20261006.json](evidence/FULL_DIRECT_ACCEPTANCE_20261006.json): representative8s Direct clip and accepted controller continuation.
- [FULL_REFERENCE_ACCEPTANCE_20261006.json](evidence/FULL_REFERENCE_ACCEPTANCE_20261006.json): representative8s corrected Reference clip, accepted three masters, exact-file human speaker/name evidence, normal Director acceptance and scene reset.

D5 and Direct media remain under canonical repository output roots. Reference media/ledger live in its disposable acceptance root `/tmp/storybuilder-full-controller-acceptance-20261006-nlmgwm4y`; preserve it and its browser/review/controller reports. Temporary disposable roots are not claimed as permanent production storage. Test continuation tasks are intentionally held before generating additional shots; those holds do not invalidate proved continuation/replay behavior.

## Final checks and runtime

Backend command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/riki/web_dev /home/riki/miniforge3/envs/react/bin/python -m pytest -q -p no:cacheprovider` —803passed53.82s; four existing FastAPI lifecycle warnings. Targeted new review suite114passed13.56s. Frontend14unit tests/4files; lint0errors13existingwarnings; TypeScript/Vite1695module build passed with existing build warnings. Full browser24passed8skipped: opt-in real specs are covered by their separate saved actual checks, and flag-off by explicit rollout tests. No claim that mock tests establish native quality.

Real rollout/browser artifact roots: `/tmp/storybuilder-release-navigation-20261007` (4passes), `/tmp/storybuilder-release-frontend-sweep-20261007` (full suite/log), `/tmp/storybuilder-normal-release-navigation-20261007` (2passes against normal site). Final build `/tmp/storybuilder-release-build-final-20261007`. Native playback/restart, UI cancellation and worker recovery artifacts are linked in the release manifests and implementation log.

Normal site ready at http://127.0.0.1:8081/production; API3010, launcher session83317 left running. Healthy ComfyUI3008/Ollama11434 reused. Startup did not dispatch new work. No further user approval or technical intervention is needed for release. Human speaker evidence means Mira speaks to Arun/Aaron, not that Aaron is the speaker; accepted pronunciation must not trigger further retries.

No new GPU render during final completion. Retained accepted render telemetry peaked78–82°C, graphics2080–2086MHz, no watchdog trip. Continue independent temperature/utilization/clock supervision with83°C intervention below85°C maximum and operator2100MHz lock ceiling. Recheck after powercycle; no clock settings were changed here.

## Changes and rollback

The final review repair changed `services/production_ledger.py`, `services/production_video_director.py`, and `tests/test_production_video_director.py`. Earlier timed evidence integration changed `services/production_temporal_video_evidence.py`, its tests and Director integration. Final rollout added `frontend/app/.env.local`; documentation changed README, current status, operator/quality guidance and implementation log, plus this final record and audit. Earlier complete upgrade source/workflow changes and their backups are enumerated by phase in IMPLEMENTATION_LOG; no Git checkout is present, so no invented Git diff is provided.

Navigation rollback: explicitly set `VITE_STORY_BUILDER_NEW_PRODUCTION_NAV=false`, restart/rebuild Vite; merely unsetting the shell value leaves `.env.local` enabled. Existing routes/code remain available. Code backups: `/tmp/storybuilder_speaker_confirmation_preedit_20261007.tgz`, `/tmp/storybuilder_temporal_integration_preedit_20261007.tgz`. Final docs backup `/tmp/storybuilder_final_release_docs_preedit_20261007.tgz`. Compare subsequent edits first, extract only selected affected files from the appropriate archive, then run the relevant checks. Never restore/delete a production ledger or generated media as code rollback. No models, ComfyUI packages, shared downloads or accepted output bytes were changed.
