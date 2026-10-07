# Small, ordered execution cards for an implementation agent

**Resume instruction:** first read [12_CURRENT_STATUS.md](12_CURRENT_STATUS.md) and [11_IMPLEMENTATION_QUALITY_GATES.md](11_IMPLEMENTATION_QUALITY_GATES.md). The cards below retain their original requirements; their order does not instruct you to repeat already completed H3 work. A foundation/mock pass and a live website/release pass are separate evidence categories.

Also read [13_SOL_REVIEW_2026_10_04.md](13_SOL_REVIEW_2026_10_04.md). Review each integrated milestone before the next card; cover cancelled/failed recovery and live-owner fencing, not only successful clicks. H3 regression/release tests are permitted with continuous temperature, utilization and clock monitoring under the shared admission/watchdog policy.

Read [00_READ_ME_FIRST.md](00_READ_ME_FIRST.md) and the relevant detailed document **before each card**. Work in small changes; run tests at every gate. Record filenames, commands, results and live capabilities in `IMPLEMENTATION_LOG.md` (copy [10_IMPLEMENTATION_LOG_TEMPLATE.md](10_IMPLEMENTATION_LOG_TEMPLATE.md) when execution begins). Use [09_CONTRACT_EXAMPLES.md](09_CONTRACT_EXAMPLES.md) as illustrative fixtures, then verify them against actual code and model inputs. Do not mark a card complete because code exists: prove its exit condition. If a card fails, fix it or mark that capability unavailable and keep the old site usable. A later card must not assume an optional failed capability works.

**Host access prerequisite:** follow the host execution checklist in `AGENTS.md`. Use the configured ComfyUI port 3008 and API port 3010; verify on the host before claiming an outage. GPU admission and its monitor must share real host device/loopback access. Follow the latest direct human pause/resume instruction and the latest handoff in `12_CURRENT_STATUS.md`; do not retain a stale pause or infer resumption from automatic goal bookkeeping. The 6 October direct request renews full-plan implementation intent, with the exact D5 correction recovery hold preserved separately. Use the maintained text-only acceptance runner in AGENTS and advance named gates instead of repeating unchanged broad tests.

## Phase A — dynamic H3 **first**, no website change

**A0 — Protect baseline.** Inspect current files/dirty worktree, hash `workflows/api/minimax_h3_r2v_api.json` and both Ricky R2V graphs, back up affected source/config/workflow files to a compressed archive with restore instructions. Run current backend/manual/video/audio tests and frontend build/Playwright smoke. Read local H3 node source and live `object_info`. **Done when:** baseline, backup and installed capability record exist; no modified ComfyUI/env/media.

**A1 — Typed reference contract.** Add `ReferencePlan`/`ResolvedReferenceMap` validation in a small new service module with project-scoped asset resolution. Add tests for IDs, roles, count/duration, format, safe paths and speaker binding. Do not submit jobs. **Done when:** invalid plans fail with typed actionable errors and old tests pass.

**A2 — Graph compiler.** Add the deterministic `minimax_h3_graph_compiler.py` against a copied/versioned R2V base. Add only allowlisted loaders, wire sequential images/videos/paired soundtracks/standalone audios, compute tags from the final graph, keep model/sampler/video+audio decode chain. Do not overwrite source graphs. Add golden graph tests including same-loader video AUDIO+IMAGE proof. **Done when:** graph JSON validates, max/boundary cases pass, original workflow hashes unchanged.

**A3 — Media preprocessing and render settings.** Add safe temporary ComfyUI input staging, FFprobe, 24-fps reference conversion/loader rate, exact interval/audio sync, 17k+5 output frame calculation, 0.98 final and explicit preview settings; test cleanup ownership. **Done when:** 30/60-fps inputs cannot silently change speed; wrong/missing audio and 0.4-vs-0.98 mismatch are caught before submission.

**A4 — Live dynamic smoke.** With ComfyUI online and GPU checked, run the disposable matrix from [06](06_TESTS_AND_ACCEPTANCE.md). Inspect output streams and report VRAM/time/quality. **Done when:** at least one video+its own paired audio+standalone voice render passes; otherwise stop the dynamic capability release and record exact blocker. Do not advance to an advertising UI on a failed A4.

**A5 — Capability registration.** Add a new `minimax_h3_r2v_dynamic_v1` capability record/validation endpoint behind a feature flag; keep `minimax_references`, old Manual Director and old production runner unchanged. Add API contract tests. **Done when:** old and new catalog entries are distinguishable and truthful, rollback is one flag/config change, old tests pass.

## Phase B — durable story/director foundation

**B1 — Durable project production ledger.** Add scoped run/task/job/event records, idempotency and restart reconciliation without replacing `project.json` or old artifact files. Tests: double-click, crash after ComfyUI submission, parent-child dependency, cancel/retake. **Done when:** no accepted media or external submission duplicates across retry/restart.

**B2 — Mandatory story and chunk-safe text.** Keep `story_input` required; implement source-fact preservation, sparse-story elaboration, stage chunks, completeness validators and revisioned accepted canon. Manual may author or ask Director to generate scenes/prompts. Tests include truncated provider output and one very long dialogue scene. **Done when:** no missing scene/dialogue IDs, old projects/artifact editors load.

**B3 — Director contract and H3 corpus.** Add provider-neutral bounded task adapter (Codex initial), Director briefs/checks at each stage, versioned H3 rules/examples, prompt lint and Refine-proposal diff contract. No runtime code edits by model. **Done when:** a mock provider and Codex smoke yield valid shot plans; wrong tags/S1 mapping fail before H3; Refine never silently changes selected assets.

**B4 — Production types and narrative styles.** Follow [08_STYLES_AND_PROMPT_GOVERNANCE.md](08_STYLES_AND_PROMPT_GOVERNANCE.md): preserve six base IDs and distinct Director behavior profiles; add nested variants, text-only PDF/MD/TXT evidence, immutable versions and shared picker only after backend/style tests. **Done when:** legacy style selection still resolves, a variant has its own behavior and evidence, keyboard/mobile picker Playwright passes. This card can be split further into backend and picker tasks if needed.

## Phase C — project assets and audio

**C1 — Project asset registry/browser API.** Build IDs, hashes, typed roles, safe scoped upload/content endpoints and one-copy references. Index existing project outputs and external Video Repertoire references without copying. Review path containment of new and touched file-serving routes. **Done when:** browser can list/preview project images and source video/audio safely; project deletion cannot remove shared YouTube media. **Status (2026-10-05): complete for this card.** Backend/API tests exercise upload/content/path/dedup/link and shared-media-safe deletion; Production Workspace Playwright exercises project image/video/audio previews and linked Video Repertoire video/audio previews. Keep both suites in final release checks; the live playback test remains separately gated.

**C2 — Image generation adapters.** Add distinct tested Qwen 2512 and Z-Image Turbo options; export/version a **new** Qwen Edit 2511 API graph, not the existing 2509 file; preflight exact model/node/input contract. Add four-candidate Manual/Semi and one+bounded-retake Full policy; optional Direct H3 character image button. For Full, carry a validated active canon identity and saved provider through the request and durable job; CPU-preflight that provider before GPU admission; persist Director evidence/decision before acceptance or retake; make retake enqueue deterministic and replay-safe; atomically assign accepted master identity. Follow the precise provider and fail-before-GPU checks in [11_IMPLEMENTATION_QUALITY_GATES.md](11_IMPLEMENTATION_QUALITY_GATES.md). Test the actual API→SQLite→worker→asset registry→status API→browser path, including backend restart and unavailable callback behavior. **Done when:** output files have prompt/model/seed/source hashes; Manual/Semi selection works; Full is either fully integrated with bounded retry evidence or explicitly unavailable; 2511 is live-proven or disabled with reason; 2509 regression passes. Passing reviewer/compiler/store tests alone does not close C2.

**C3 — Character/world state and optional frames.** Add text bibles in all making routes, generated masters in Reference-built/selected Hybrid, and FL2VA first/last frames only when shot plan calls for them. Use existing I2V API only after smoke. **Done when:** Direct H3 does not generate images by requirement, Reference-built blocks a dependent shot until its declared master is accepted, Hybrid only builds selected assets.

**C4 — Voice/dialogue and optional audio sidecars.** Add eligibility/audition, stable S1/S2 binding, seeded saved Full random choice, local TTS and recorded-take conversion paths, optional music/SFX sidecars and native H3 audio ownership. Hosted clone stays opt-in/separately gated. **Done when:** two-character dialogue works with stable bindings, no double-speech claim, optional BGM/SFX never silently enter H3 voice refs.

## Phase D — shot jobs and UI

**D1 — ShotPlan/revision/refine API.** Expose exact shot contract, asset intents, resolved reference map, validate endpoint, Refine proposal/diff, optimistic revision and safe content URLs. Tests: stale prompt, reordering refs, invalid slot, user edit preservation. **Done when:** same saved plan compiles to same graph/map and errors identify asset/stage.

**D2 — Dependency-aware shot worker.** Submit one validated take asynchronously; waiting child, accepted parent, unchanged-manual-draft auto-release, changed-draft human hold, retry/cancel/retake, output collection and idle ComfyUI model unload. When the Director owns render approval, preflight the immutable run provider on CPU before staging or GPU admission; preserve the claim heartbeat and fail with no prompt ID if unavailable. Keep the Full/Semi render API gate closed until the durable Director video decision, replay, bounded retake and browser path work end to end. **Done when:** restart, two shots in flight, parent retake and ComfyUI error tests pass; no external duplicate submissions.

**D3 — New production workspace shell.** Add route, stage rail, independent control/making selectors, mandatory story page, conditional asset page, voice page and saved navigation. Keep old routes untouched. Playwright after each page. **Done when:** reload/back restore state and all old page smoke tests pass.

**D4 — Shot composer.** Add prompt and Refine diff, project/repertoire shelves, asset cards/+ buttons, 9/3/3 limit UI, video paired-sound switch, exact tag display, workflow parameters, Preview validation, Generate & Next, queue rail, review/player/retake. Responsive/keyboard/error/animation states from [04](04_PRODUCTION_UI.md). **Done when:** mocked Playwright matrix passes, no console errors/overflow, live one-shot backend result renders in UI.

**D5 — Make new path primary only after acceptance.** On a disposable project, compare existing story planning and new story→shot output. Change Story Builder/Automation “production” navigation to the new run route behind a flag, preserving legacy `production/start` for old clients until migration tests pass. Do not remove old code just because new UI renders. **Done when:** real two-scene/two-character/two-cut test passes with outputs, audio, manifests, one-copy storage and no regressions.

## Phase E — launcher, broad regression and handoff

**E1 — Surgical launcher readiness if needed.** Verify current `run_story_builder.sh`; add Python/port preflight and strict frontend port behavior only if the new worker/start flow needs it. Preserve “already running ⇒ do not restart” for Ollama and ComfyUI. Test two simultaneous launch attempts and a missing `uvicorn` environment. **Done when:** exact URL/port is printed, failure is actionable, no duplicate services, old startup works.

**E2 — Full test sweep and Playwright.** Run new unit/integration suites, existing affected backend suites, frontend build/lint/test, existing and new Playwright specs, live two-scene acceptance from [06](06_TESTS_AND_ACCEPTANCE.md), GPU/resource audit. Fix regressions within scope. **Done when:** pass/fail table, screenshots/traces, output locations, peak GPU, limitations and rollback method are recorded.

**E3 — UX/documentation cleanup.** Error copy, tooltips, disabled reasons, confirmation dialogs, accessibility/mobile, progress states, help for Audio-numbering and Direct-vs-Reference-built trade-off. Update README/operator instructions and keep no unused empty folders or permanent staging copies. **Done when:** a new user can create a short story, select voice, refine a shot and play the resulting asset without reading the code.

## Stop/ask conditions

Stop before a materially different choice or external change: ComfyUI package update, model download/install, hosted MiniMax voice upload/payment, destructive migration/deletion of shared media, or changing existing generated outputs. A failing local model is not a reason to silently choose another workflow. Report exact failed command/node/model, safe alternatives and impact. Continue independent safe work while a single optional feature is blocked, but do not label the blocked feature complete.

## Final delivery checklist

Provide changed-file list, phase pass table, actual compiled graph example with reference tag map, live video/audio preview location, two-scene test output and logs, backend/build/Playwright results, no-regression findings, remaining optional gates, GPU/resource observation and any required user step. The final UI must point to real output paths in `output/<project_id>` and preserve shared Video Repertoire source files.
