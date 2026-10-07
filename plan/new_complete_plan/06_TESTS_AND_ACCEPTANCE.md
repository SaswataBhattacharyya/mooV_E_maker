# Verification matrix, live fixtures and release criteria

Test every changed layer at the boundary where it can actually fail. A passing unit test does not establish that ComfyUI loaded a model; a playable MP4 does not establish correct character/voice mapping; a Playwright click does not establish the backend preserved a queued job after restart. Record test command, date, environment, result, artifact paths, known failures and next action in `new_complete_plan/IMPLEMENTATION_LOG.md` during execution.

## Baseline before code edits

1. Read current changed/dirty files and preserve unrelated user work. Make compressed backup of the affected website source/config/API workflow JSON before modifications, excluding models and large media; record archive and explicit restore procedure. Do not delete/replace existing media.
2. Run existing relevant backend suites: `tests/test_manual_director.py`, `test_media_jobs.py`, `test_video_repertoire.py`, `test_video_references.py`, `test_audio_tts.py`, `test_audio_effects.py`, `test_story_revisions.py`, `test_reasoning_provider.py`, and any production/story tests added later. Record pre-existing failures rather than attributing them to new code.
3. In `frontend/app`, run the existing build and current `e2e/manual-director.spec.ts`, `e2e/video-repertoire.spec.ts`, `e2e/video-audio-assets.spec.ts`, `e2e/phase-2-3.spec.ts`, plus Story Builder/Automation route smoke. Use `PLAYWRIGHT_BASE_URL` set to the *actual* Vite port. The current Playwright config looks under `frontend/app/e2e/`.
4. Read-only ComfyUI snapshot: `/system_stats`, `/object_info` for H3/loaders, model file names, queue status, GPU free/used, workflow hashes. Do not launch a heavyweight GPU smoke without checking available memory and other jobs.

## Backend unit/contract suites to add

### Dynamic graph — first release gate

- `tests/test_minimax_h3_graph_compiler.py`: reference count boundaries; 0/1/max image/video/audio; no disconnected optional loader; one same-video loader supplies paired IMAGE+AUDIO; invalid cross-loader pair rejected; sequential local slot names; stable node IDs/serialization; immutable source templates; allowlisted class types; safe file IDs and paths.
- `tests/test_minimax_h3_reference_map.py`: `<Picture>/<Video>/<Audio>` labels from **actual compiled connections**. One paired video+two standalone voices produces Audio 1 soundtrack, Audio 2 S1, Audio 3 S2; no paired audio produces Audio 1 S1, Audio 2 S2. Reorder/removal updates mapping and invalidates stale prompt. A connected reference without a role and a referenced nonexistent tag both fail.
- `tests/test_minimax_h3_media_preflight.py`: 24-fps conversion or forced loader rate; 30/60-fps source not silently slowed; segment time range sync; video/audio from same source and interval; absent soundtrack; overlong input; wrong MIME; corrupt file; combined local reference budget/VRAM; no permanent staging duplicate.
- `tests/test_minimax_h3_params.py`: 0.98 selector gives the resolved final width/height, 0.4 is visibly preview, length snaps correctly to local 17k+5 grid, steps/scheduler/seed/ref image sizing independent; no hidden lower-quality fallback after OOM.
- Golden API graph examples committed as small JSON fixtures for text+voice, image+voice, video alone, video+paired audio+two voices, and max-slot validation (not necessarily render max refs). Compare graph structure, not randomized prompt IDs.

### Story/Director/assets/jobs

- Story is required in all modes, including Manual. Short story is expanded without losing source facts; inferred detail is labelled and revisions preserved. Stage chunking preserves all planned character/scene/dialogue IDs even when a provider truncates a unit; retry touches only that unit.
- Provider-neutral Director tasks include resolved production type/style, canon, making route, workflow capability, prompt corpus version and reference map. No new story stage accidentally calls Ollama; unrelated Ollama pages remain unchanged. Refine returns proposal/diff and never changes selected refs or executable JSON; changed asset order makes prompt stale.
- All six existing production types and IDs remain valid; each Director behavior pack is distinct. Nested style variants and `.pdf/.md/.txt` evidence provenance work; video cannot become a narrative-style source.
- Manual, Semi and Full gates are tested separately from Direct/Reference-built/Hybrid routes (matrix of 3×3 using mocks, then representative live flows). Direct skips image generation; Reference-built requires only its declared masters; Hybrid adds only selected ones. Four image candidates in Manual/Semi when requested; one plus bounded retake in Full.
- Project image browser indexes generated/imported project images without physical duplication. External Video Repertoire asset IDs resolve to source paths but deletion of a project never deletes those source videos or their analyzed media. User uploads are project-scoped with type/size/path containment.
- Voice binding manual audition, missing transcript/eligible pool, seeded random one-time Full choice, stable S1/S2 across cuts, local recorded-take conversion retaining source, wrong-speaker report, no unsolicited hosted clone upload. Optional music/SFX sidecars do not occupy standalone voice-ref slots.
- Durable queue/idempotency: double click, HTTP retry, process restart, lease expiry, output collection retry and parent retake do not create duplicate accepted media or duplicate ComfyUI submission. Manual child auto-submits after accepted parent **only when draft/reference/prompt revision hashes match**; otherwise it waits for review. Cancellation affects only the owned prompt/job.
- Every persisted media result has correct project/run/shot/take/asset IDs, safe content URL, checksum, provenance, native audio disposition, and cleanup outcome. Logs give actionable stage/error codes but redact secrets/private payloads.

## Live GPU acceptance — disposable project only

Do not use an existing user's production project as a destructive fixture. Start with a deliberately short story such as: “In one apartment, Maya warns Arjun about a storm; after a pause they leave for a station. Maya speaks first; Arjun answers.” Its two locations and two voices make continuity observable while leaving creative details for the Director.

**Workflow smoke sequence (stop at a failing stage):**

1. Prove current static T2V/API graph still works and existing Manual Director is unchanged.
2. Test dynamic R2V with **voice-only** (Direct H3); if local R2V cannot do audio-only, record that and use tested T2V or a minimal approved image, without pretending the shortcut works exactly as planned.
3. Test dynamic one image+voice; then one 24-fps video without its soundtrack; then the *same loader's* IMAGE+AUDIO paired video; then paired video plus S1 and S2 standalone voices. Inspect both audio and video, not just filename/status.
4. Build a same-scene two-cut chain: Cut 2 waits for Cut 1 accepted output, uses a short tail, paired sound only if relevant, and tags remain correct. Start a fresh scene and confirm it does **not** inherit the prior-scene MP4 by default.
5. Run final 0.98 preset and a low preview; use FFprobe to record actual width, height, frame rate, duration, audio presence/channels. Record steps, seed, `ref_image_size`, runtime, peak GPU and OOM/recovery evidence. Do not conflate exact rendering specs with qualitative cinematic quality.
6. Review visual identity, location geography, expected action/camera, actual spoken words, S1/S2 voice assignment, clipping/silence and A/V sync. A human may judge subjective quality for the release gate even though Full automation later uses a Director rubric; document failures and bounded retakes.
7. Test one verified Qwen 2512 base, one Z-Image base, one Qwen Edit 2511 **only if its new exported API adapter passes preflight**, and one FL2VA first/last shot. Missing 2511 is a clearly disabled option, not a mislabeled 2509 render.

Collect small manifest/log files and safe previews under a dedicated disposable project. Outputs remain under that project's canonical output root. Cleanup of the disposable project is a separate, scope-checked action after the user has reviewed results; it must not touch YouTube downloads or other projects. Keep no massive temporary reference conversion after all dependent jobs finish.

## Playwright/browser acceptance

Add focused specs under `frontend/app/e2e/` with stable test IDs and mocked/deterministic API responses for failure/edge cases; add one separate live browser smoke against a disposable backend/ComfyUI run. Exercise:

- Story mandatory; short story detailing; Manual user-authored versus Director-generated scene drafts; Back/Next and reload state.
- Control mode and making route are independent; Semi's four switches; Direct optional character generation; Reference-built required masters; Hybrid shot override.
- Project image browser, existing Video Repertoire search and saved-audio audition; scoped upload and no duplicate source file; keyboard and drag/drop alternative.
- Reference composer card add/remove/reorder limits (9/3/3); a paired soundtrack switch changes visible Audio numbering; Refine shows diff, accept/edit/discard; change after Refine marks prompt stale.
- 0.98 final-res selector and separate preview/steps/ref-image-size controls; unsupported Add Guide/ControlNet/2511 path clearly disabled with reason.
- Generate & Next queues and advances; child shows `waiting_for_predecessor`; accepted predecessor releases unchanged draft; changed draft becomes `Needs review`; cancel/retry/retake and Back dependency warning.
- Progress stage rail, job queue rail, active-spinner/button press feedback, toast and field-level failure details. Test loading, empty, offline ComfyUI, missing voice, invalid media, OOM/timeout and output missing. No click should fire two jobs.
- Output player shows video **with native audio**, standalone optional sidecars, job provenance and retake comparison.
- Desktop, tablet/narrow/mobile layouts; no overflow; labels, focus, keyboard operation, dialog focus restoration and reduced motion.

Run existing Playwright suites on **every touched route**, not only the new page. A build passing is not enough; changed Story Builder, Automation Studio, Manual Director, Video Repertoire, Audio Studio and launcher-visible status require relevant regressions. Record actual frontend/backend ports, screenshot/trace paths and console errors. Do not claim Playwright validated native model quality; that is the live GPU gate.

## Release/no-regression gate

The feature is complete only when: dynamic R2V graph really consumes requested refs; story and all three control/making modes work as stated; users can inspect and queue shots safely; project/repertoire storage ownership is correct; source video downloads remain untouched; launcher and old pages still work; backend/build/Playwright tests pass or known pre-existing failures are clearly distinguished; and a disposable two-scene project yields playable, reviewed clips with audio and reproducible manifests. Any optional advanced model not installed is marked unavailable, not represented as done.
