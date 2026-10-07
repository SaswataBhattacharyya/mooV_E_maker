# Story Builder film-production upgrade — execution contract

**Status:** active implementation. Start with [12_CURRENT_STATUS.md](12_CURRENT_STATUS.md) for current completion/evidence and unfinished gates. No feature is considered shipped until its phase gate passes. This folder is the authoritative handoff for this upgrade; `plan/story_generation_director_and_style_system_plan.md`, `plan/prompt.md`, and `plan/full_review/` are background/source history where they differ.

## Read order

Before editing, read [11_IMPLEMENTATION_QUALITY_GATES.md](11_IMPLEMENTATION_QUALITY_GATES.md) and [12_CURRENT_STATUS.md](12_CURRENT_STATUS.md), then the relevant detailed card documents below. The earlier dynamic R2V smoke is preserved and need not be repeated as a baseline. The user permits targeted H3/T2V regression and release tests when relevant, with continuous temperature, utilization, and graphics-clock monitoring; continue the remaining coding and acceptance gates.

1. [01_DYNAMIC_H3_FIRST.md](01_DYNAMIC_H3_FIRST.md) — **first implementation phase**, dynamic reference graph and real smoke tests.
2. [02_STORY_DIRECTOR_AND_MODES.md](02_STORY_DIRECTOR_AND_MODES.md) — mandatory story, Director, prompt rules, two independent mode axes.
3. [03_ASSETS_AUDIO_AND_STORAGE.md](03_ASSETS_AUDIO_AND_STORAGE.md) — image/voice/world/audio paths and one-copy ownership.
4. [04_PRODUCTION_UI.md](04_PRODUCTION_UI.md) — complete pages, shot composer, interaction/feedback design.
5. [05_API_JOBS_AND_RUNTIME.md](05_API_JOBS_AND_RUNTIME.md) — routes, durable queue, ComfyUI and launcher lifecycle.
6. [06_TESTS_AND_ACCEPTANCE.md](06_TESTS_AND_ACCEPTANCE.md) — unit, integration, live model, Playwright and regressions.
7. [07_LUNA_TASK_CARDS.md](07_LUNA_TASK_CARDS.md) — small ordered implementation tasks and stop/go gates.
8. [08_STYLES_AND_PROMPT_GOVERNANCE.md](08_STYLES_AND_PROMPT_GOVERNANCE.md) — production-type behavior, narrative style variants and source evidence.
9. [09_CONTRACT_EXAMPLES.md](09_CONTRACT_EXAMPLES.md) — concrete versioned payload examples for implementation/tests.
10. [10_IMPLEMENTATION_LOG_TEMPLATE.md](10_IMPLEMENTATION_LOG_TEMPLATE.md) — copy to `IMPLEMENTATION_LOG.md` when execution begins.

Execute cards in order. **Complete, test and record each gate before the next card.** Do not interpret the existence of a model file, UI graph or API endpoint as proof a workflow produces correct output. Update this folder with actual results, changed assumptions and failure evidence as work proceeds; do not silently mark a missing capability implemented.

**Handoff instruction for Luna:** use the current-status file and [13_SOL_REVIEW_2026_10_04.md](13_SOL_REVIEW_2026_10_04.md) to select the next unfinished gate and work one card at a time. Inspect the current repository, make the smallest compatible change, test the real producer-to-consumer path and relevant error/concurrency/restart behavior, and update current status plus the implementation log. Preserve completed H3 evidence; the user permits relevant H3 tests with continuous GPU supervision. Review each integrated milestone before proceeding and do not advertise unavailable controllers. Ask only when a documented stop condition applies; otherwise resolve in-scope issues with measured tests and preserve working paths.

## User decisions locked for this build

- A **story is mandatory** for every production project. It may be brief; the Director can expand it while preserving the user's facts and distinguishing inferred creative detail from source fact. Manual is *not* a blank-shot escape hatch.
- **Control mode:** Manual, Semi or Fully automated. **Making route:** Direct H3 (default for *new* projects), Reference-built, or Hybrid. These are independent. Preserve existing projects' behavior until migrated explicitly.
- Manual may author/edit the story and scene/shot material or ask the Director to generate it. Direct H3 Manual does not require a character/world image phase, but offers optional character-image generation. Reference-built Manual requires accepted visual masters for the shots that use them.
- Semi has independent human-decision gates for story/scene review, image creation/selection, voice selection, and video references/rendering. If every gate is enabled it is effectively manual media control, while the Director can still draft text and prompts. Fully automatic keeps human interaction non-mandatory after the starting story/consent/policy choices.
- Full-auto voice choice is one **seeded, saved random choice from eligible local voices per character**, not semantic matching by default. Manual/Semi users can audition/bind voices.
- A shot may use up to **9 reference images, 3 reference videos total (each may optionally have its paired soundtrack), and 3 standalone reference audios**, subject to the actual local model/graph, duration and GPU preflight. These are ceilings, not targets. `0.98` is a Ricky Resolution Selector preset mapping to 1344×768 at 16:9, **not a quality score**.
- A same-scene later cut may reference a short accepted previous-shot tail and *optionally* its paired audio. A fresh scene has no prior-scene MP4 by default. The Director still carries global story/character/world/voice facts. Ordinary R2V is reference guidance, not guaranteed seamless continuation.
- Every media reference has a separate **intent note** (“use this for appearance/camera/voice/etc.”). The Director generates the main H3 prompt from the story, shot and intent notes; Refine proposes an editable diff and never silently overwrites user text or changes selected assets.
- A Manual shot's **Generate & Next** may queue behind a still-running predecessor. If the approved draft and input revisions remain unchanged, it submits automatically after that predecessor is accepted. Otherwise it waits for review. Back/Next preserve drafts.
- H3's native video+audio output is kept. Optional separately generated dialogue, music and SFX stay timestamped as project assets for future Hyperframes editing. Do not feed separate BGM/SFX into standalone *voice* slots by default, do not pretend prompt `fully_copy` guarantees exact audio, and do not implement final film stitching in this upgrade.
- The image browser is initially **project-scoped**. It indexes project output/imports; external Video Repertoire references are linked, not copied into a second permanent library. Global cross-project image sharing can be a later explicitly designed promotion feature.
- Prompt/source style ingestion remains text-only (`.pdf`, `.md`, `.txt`); visual references are a separate production concern. Keep distinct Director behavior profiles for the six existing production types and any selected style variant.

## Safety and compatibility rules

1. Preserve working Story Builder, Automation Studio, Manual Director, Audio Studio, Video Repertoire, analyzer, existing ComfyUI graphs/models, Conda environments and Docker projects. New behavior is additive behind a capability/feature gate until live acceptance proves replacement. Touching any of them requires targeted regression tests.
2. Before website/code changes, create a **compressed backup of affected website source/config/workflow files** (exclude large models and generated videos); record path and restoration steps. Do not run broad deletion or overwrite the Ricky workflow files. Preserve user changes and inspect the working tree/file timestamps first.
3. Generated project files have one canonical home under `output/<project_id>/`; project state and small manifests/checkpoints are under `storage/projects/<project_id>/`. Keep source/analyzed video in `video_repertoire/`. Stage temporary ComfyUI inputs under per-job ownership and clean them only when safe. Never delete a YouTube download while deleting a production job.
4. Code must be **verbose where it aids debugging**: explicit typed validation; stage and asset IDs in logs; model/workflow version, file hash, slot map, prompt IDs, duration/resolution, GPU preflight, retries and structured failure reason. Do not print API keys, full private story text, raw voice/audio or unbounded model output in routine logs.
5. Codex CLI is the initial configured text worker under a provider-neutral Director contract. Do not force Ollama into the new story route or remove it from unrelated pages. The Director may propose prompt improvements, not silently edit executable code at runtime.
6. Every new UI action needs loading, success, failure, disabled, retry/cancel where relevant, keyboard/accessibility and mobile behavior. Show progress for long work; a button animation never substitutes for a truthful job state. Confirm destructive actions with exact scope.
7. Do not install/upgrade ComfyUI or add model checkpoints just because the documentation mentions a feature. Advanced Add Guide/Fun ControlNet and hosted MiniMax Speech are separate future capability gates. Existing local H3 R2V is the immediate target.

## Current-state warnings a small implementation agent must not miss

- `services/production_runner.py` is a two-scene demonstration path using `plan/image.png` as three fixed references, an MP3 fixture fallback and audio muxing. **Do not route the new production UI into it and claim success.** Replace the call only after the new run path has its own tests and migration gate; retain the old path temporarily for regression.
- `services/manual_director.py` currently maps H3 text, 1–3 image R2V, and WAN first/last. Audio/video UI slots exist but its mapped R2V API graph does not consume them. Do not expose the new capability there until Phase 1 smoke passes.
- `workflows/ricky/*.json` are UI graphs, not necessarily runnable API graphs. `gsl_starter_1_1` uses **Z-Image Turbo**; current `workflows/api/qwen_edit_api.json` uses **2509**, not Ricky's **2511**. Ricky's crazy R2V graph connects a reference video's frames and purported paired audio from two *different* loader nodes, and its 0.4 MP Resolution Selector overrides the H3 node's displayed size.
- Local ComfyUI has the `MiniMaxH3ReferenceToVideo` image/video/paired-audio/standalone-audio input code but the inspected installation does **not** have `MiniMaxH3AddGuide`; Fun ControlNet prerequisites were not found. Do not promise them in the first release.
- `run_story_builder.sh` already health-checks/starts Ollama and ComfyUI without restarting reachable instances, then starts FastAPI/Vite. It does **not** guarantee free frontend/backend ports or that the selected Python contains `uvicorn`. Plan launcher changes surgically and test no duplicate services.

## References and evidence hierarchy

Read actual code/API JSON, live ComfyUI `/object_info`/`/system_stats`, and real output first; official docs provide design intent, not proof of local installation. Primary sources: [MiniMax H3 generation](https://platform.minimax.io/docs/guides/video-generation), [ComfyUI native H3](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native), [ComfyUI R2V node inputs](https://github.com/Comfy-Org/embedded-docs/blob/main/comfyui_embedded_docs/docs/MiniMaxH3ReferenceToVideo/en.md), [H3 prompt guide](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide). Recheck current limits at implementation time. The embedded R2V node page identifies itself as AI-generated, so cross-check with installed source.
