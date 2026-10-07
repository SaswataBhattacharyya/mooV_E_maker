# Project assets, image workflows, voices, sound and one-copy storage

Asset preparation is optional in Direct H3 and required where Reference-built/Hybrid ShotPlans declare it. All assets are addressed by **stable IDs plus a role and provenance**, never by a browser-supplied absolute filesystem path. The browser sees safe content URLs and metadata.

## Image workflow reality and staged rollout

| User-facing choice | What it actually is now | New adapter/preflight task |
|---|---|---|
| **Qwen Image 2512** | `workflows/api/qwen_2512_t2i_api.json` is a text-to-image API graph using `qwen_image_2512_bf16.safetensors`. | Reuse after live model/input/output smoke. Expose text prompt, aspect/size, steps, seed and candidate count through a typed image-job schema. |
| **Z-Image Turbo** | `workflows/ricky/gsl_starter_1_1.json` and `workflows/api/gsl_starter_1_1_api.json` use `z_image_turbo_bf16.safetensors`; it is not Qwen. | Give it its own clear label and readiness check; use only for generation when its actual output is suitable. |
| **Qwen Image Edit 2511** | `workflows/ricky/qwen_image_edit_2511.json` is a UI/subgraph export; existing `workflows/api/qwen_edit_api.json` selects **2509** and its Lightning LoRA. | Produce a **new** versioned 2511 API export/adapter; inspect loader/model availability, input-image count, prompt nodes and output, then smoke on a disposable source image. Keep 2509 working. Do not rename the 2509 graph and pretend it runs 2511. |
| **H3 first/last frame** | `workflows/api/minimax_h3_i2v_api.json` exists; the Ricky `vid_minmax_h3_i2v.json` is a UI graph with subgraphs. | Add a typed FL2VA adapter only after real API smoke. Generate first/last images through the selected image model and pass them only to this validated family, not simultaneously into an unsupported hosted R2V request. |

The Director prepares model-specific prompts. Manual/Semi image review can generate **four candidates** per requested asset; Full generates one and may retake within a saved budget. Candidate files and an accepted master are *distinct records*, not ambiguous overwrites. Qwen Edit variants derive from an accepted master and must be checked for face, clothing, room layout, entrances, prop placement and color consistency. A multi-panel character sheet is an option, not a mandatory way to consume every H3 image slot; benchmark it against one clear shot-specific crop.

### Asset roles

- `character_master`, `character_angle`, `expression`, `costume_state` — stable character identity and state. The long route builds accepted master sheets; Direct H3 can create one on demand.
- `world_master`, `location_angle`, `lighting_state`, `prop` — stable world geography and shot-relevant variants. **Text world-state canon exists in every route**; visual boards exist only where requested.
- `scene_board` — composition/look reference for one scene, distinct from an H3 first/last frame.
- `first_frame`, `last_frame`, `keyframe` — explicit FL2VA/verified timeline-anchor inputs; not generated for all shots.
- `action_reference_video` and `previous_cut_tail` — different origins/purposes. Only an explicit action-reference selection may borrow external choreography; previous-tail selection is derived from a project's accepted cut.
- `voice_master`, `voice_excerpt`, `dialogue_take`, `music_candidate`, `sfx_candidate`, `h3_native_audio` — separate audio roles. A clean 30-second voice example is not automatically an H3-compliant short reference; make a non-destructive derived excerpt when needed.

The project asset browser lists **project images** (generated/accepted, candidates where relevant, and user imports) and links Video Repertoire video/audio references where the user selects them. `frontend/app/src/pages/ManualDirector.tsx` currently lists repertoire videos/audio and manual uploads but has no dedicated project-image repertoire. Build a common `ProjectAssetBrowser` component with tabs/filters for Characters, Worlds & props, Scene boards/frames, Voices/dialogue, Videos, Music, SFX, and External Video Repertoire. Browse/select/preview without copying into a second permanent folder. A future global image library may explicitly promote an approved image; **not** in this phase.

## Voice and dialogue

The project has existing `services/audio_tts.py`, `services/audio_catalog.py`, `services/audio_effects.py`, `services/audio_automation.py`, and Audio Reconstruct. Inventory their live capabilities rather than reimplementing them. The initial voice inventory in `plan/voice_catalog/` is descriptive metadata, not proof every file is clean, consented, transcript-ready, or accepted by TTS.

- At character approval, store immutable `character_id`, mutable display name, voice brief, stable `speaker_id` for H3, and a versioned `voice_binding` with source/backend/eligibility evidence. A voice sample's file name is not proof of the speaker's gender, age or identity. Offer audition and user-supplied descriptions.
- **Full auto:** choose one eligible local voice **randomly but reproducibly** per character/run. Save eligible-pool version, seed, selected ID and reason for exclusions. Do not reroll every line or every shot. Do not automatically clone or upload any voice to an external service.
- **Manual/Semi:** choose/audition manually. One can record the exact words and use the existing local voice-changer with a target reference; RVC requires an installed RVC model/index, not just any arbitrary WAV. Keep original and transformed takes, exact transcript and timing evidence; failed conversion should not replace a good original take.
- **Optional hosted MiniMax Speech voice clone:** separate API, credentials/cost/privacy/consent preflight, clean 10-second–5-minute MP3/M4A/WAV source and provider `voice_id`; never silently upload bundled or repertoire voices. This is not needed to complete the local production route. Check [MiniMax's guide](https://platform.minimax.io/docs/guides/speech-voice-clone) again before implementing.
- For an H3 shot, choose **voice timbre reference**, **pre-generated exact dialogue** as reference/guide, or **H3 native generated speech** explicitly. Prompt `fully_copy` is intent, not an exact waveform lock. Keep stable `(S1)`/`(S2)` mapping and inspect wrong-speaker outcomes. Separate original dialogue takes allow a future final edit to preserve exact speech even when H3's native voice drifts.

For `ref_audios` use clean, relevant short clips; with a paired reference-video soundtrack the standalone voices' `<Audio N>` numbers shift. Do not allow a UI that labels “Audio 1 = Maya voice” when the graph labels the previous video's soundtrack Audio 1. Show the compiled mapping at submission and in the output history.

## Music/SFX and future editing

H3 outputs video with native sound, including possible dialogue, music and effects. The Director prompts the desired on-shot sound but must not claim H3 has yielded separate editable stems. If the production asks for extra music or SFX candidates, generate them **separately** through existing ACE-Step/Control-Foley or other *preflighted* audio workflows and save timestamped standalone assets. Do **not** plug those candidates into H3's standalone voice-reference slots by default and do not irreversibly mux them over the native soundtrack merely to produce a preview. Hyperframes composition/editing is out of scope; ensure future editors can locate every source by ID and time.

Audio rendering and video rendering may use the same GPU; queue/resource policy in [05_API_JOBS_AND_RUNTIME.md](05_API_JOBS_AND_RUNTIME.md) must prevent memory contention. When ComfyUI is idle after a job, request model unload using the existing guarded helper; do not clear another user's active queue or promise literal 0 MiB GPU because desktop/other services may remain.

## Canonical storage proposal (migrate additively)

```text
storage/projects/<project_id>/
  project.json                         # existing project compatibility contract
  artifacts/                           # existing story/character/scene/dialogue JSON
  production/                          # small manifests and durable run state only
    runs/<run_id>/run.json
    shots/<shot_id>/plan.json           # revisions/refs/accepted take IDs
    assets.json                        # project-scoped index, aliases, hashes, URLs
    canon.json                         # approved text facts/world/character state
  inputs/                              # user-imported source files, not generated outputs

output/<project_id>/                   # only canonical generated media
  characters/<character_id>/...
  worlds/<world_id>/...
  scenes/<scene_id>/boards-or-frames/...
  voices/<character_id>/...
  audio/dialogue|music|sfx/...
  shots/<shot_id>/takes/<take_id>/video.mp4
  shots/<shot_id>/takes/<take_id>/native_audio.*   # only if separately extracted/needed

video_repertoire/                     # existing shared source/analyzed library, not production output
ComfyUI/input/<owned-temp-prefix>/     # temporary staging, tracked and cleaned safely
```

Do not blindly migrate existing project `media/inputs`, `media/outputs` or old output files. Add new manifests and resolve legacy records read-only until explicit migration tests pass. The current `/api/media/upload` is a broad shared upload path; **new production uploads must be project-scoped**, MIME/size checked and path-contained. The current `/api/projects/{project_id}/files/{relative_path:path}` should be reviewed for traversal before it serves new media; new routes must resolve and enforce allowed roots explicitly.

Use stable IDs and content hashes. A generated image/video/audio has one canonical output file and metadata may point to it from many pages. A selected Video Repertoire item stays there and is referenced by ID. Temporary ComfyUI staging and model-generated ComfyUI output files need a per-job ownership/cleanup rule; never remove another user's ComfyUI files or a YouTube source while deleting a project take. Deletion shows dependencies and source-vs-derived scope. A cancelled/failed job keeps small diagnostic manifest/logs even when temporary media is cleaned.

## Phase acceptance

Prove one Qwen 2512 image, one Z-Image image, one **real** Qwen Edit 2511 variant or a clearly unavailable 2511 state, and one optional FL2VA shot. Prove project-scoped image browsing, an eligible local voice audition/binding, a two-speaker R2V prompt map, H3 native audio retained, optional separate music/SFX saved once, and no copied Video Repertoire source. The Direct H3 route must work without generating any character/world image.
