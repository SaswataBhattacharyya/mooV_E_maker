# Phase 1 — dynamic local MiniMax H3 workflows (build first)

This phase is deliberately **backend/workflow only**. It proves the hardest uncertainty before story/UI work. Do not alter the existing production runner, Manual Director or Ricky UI graphs while building it. A successful HTTP `/prompt` is not acceptance; inspect a real decoded video **and audio**.

## Baseline and concrete integration points

| Existing file | Current fact | Action |
|---|---|---|
| `workflows/api/minimax_h3_r2v_api.json` | Static API graph: H3 Ref2VA node 136, three `LoadImage` inputs, text encoder, video/audio VAEs, sampler, decoders, `CreateVideo`, `SaveVideo`. | Keep unchanged as regression fixture. Create a versioned clean base under `workflows/api/generated_templates/` or a named module constant, with all optional reference links generated from a typed plan. |
| `workflows/ricky/vid_minmax_h3_r2v.json` | UI export with two images. | Read-only design reference, **not** the backend API source. |
| `workflows/ricky/vid_minmax_h3_r2v_crazy.json` | UI export with three images, one video-frame link, one video-audio link, two standalone audios, 0.4 MP. Video and paired audio currently originate at different `VHS_LoadVideo` nodes. | Use its sampler/decode intent as a reference but **not** its unsafe paired-loader connection. |
| `services/media_jobs.py` | `submit_and_wait`, `collect_outputs`, and best-effort `release_comfyui_models_if_idle` exist. | Reuse/extend these cautiously; do not unload during another user's queued/running ComfyUI job. Improve bounded logging without dumping payloads. |
| `services/manual_director.py` | Static whitelist; no audio/video R2V. | Keep existing mapping until live success; then add a separately versioned workflow option, not an in-place semantic change to `minimax_references`. |

## Build a safe graph compiler, not an LLM JSON editor

The Director's only output to this layer is a **typed `ReferencePlan`**, validated against project assets and a live capability manifest. Suggested fields:

```json
{
  "schema_version": 1,
  "project_id": "...", "run_id": "...", "shot_id": "...",
  "workflow_family": "minimax_h3_r2v_local_v1",
  "prompt_revision_id": "...", "prompt": "...",
  "resolution_preset": 0.98, "aspect_ratio": "16:9",
  "duration_seconds": 10.0, "steps": 20, "scheduler": "validated_value",
  "ref_image_size": "match_or_max", "seed": 123,
  "images": [{"asset_id":"...","role":"character_identity","intent":"..."}],
  "videos": [{"asset_id":"...","start_sec":0,"end_sec":4,"role":"previous_cut_state","intent":"...","include_paired_soundtrack":true,"audio_intent":"..."}],
  "standalone_audios": [{"asset_id":"...","speaker_id":"S1","role":"voice_timbre","intent":"..."}],
  "audio_output_policy": "keep_native_and_sidecars"
}
```

The `role` values are controlled enums plus free-text `intent`; intent text is **never** interpreted as a filesystem path or graph key. `asset_id` resolves only through approved project/repertoire indexes, with content hash, MIME probe, duration and authorization. Before implementation, capture the exact local ComfyUI `object_info` for `MiniMaxH3ReferenceToVideo`, video/audio loaders, Resolution Selector or its API equivalent, decoders and SaveVideo. Pin node names/versions and required model IDs in a capability manifest; a missing loader disables that route with a precise message.

Create `services/minimax_h3_graph_compiler.py` (name may vary only with an explicit plan note). It deep-copies an immutable API base, allocates collision-free node IDs, adds **only allowlisted** `LoadImage`, video decode/resample and `LoadAudio` nodes, and connects sequential autogrow slots. Keep model, text encoder, VAEs, sampler, joint latent decode, `CreateVideo` and SaveVideo topology. No Director/Codex response may contain arbitrary `class_type`, node ID, URL or filesystem path to splice into the graph. Validate all edges and input/output types before submitting.

### Slot rules

- `images`: 0–9, connected as sequential `ref_images.ref_image_0..8` from one `LoadImage` each.
- `videos`: **0–3 total**. Each has one video loader whose IMAGE frames feed `ref_videos.ref_video_N`; **if** its soundtrack is selected, **that same loader's AUDIO output** feeds `ref_video_audios.ref_video_audio_N`. There are not three silent videos **plus** three extra video-with-audio videos. A loader must not be left connected to `ref_video_audio_N` without its matching video frames.
- `standalone_audios`: 0–3, connected sequentially as `ref_audios.ref_audio_0..2`. These are chosen voices/performances or an explicitly justified other audio reference; optional BGM/SFX production sidecars do not occupy these slots by default.
- Empty optional slots add **no** loader and **no** link. A zero-reference shot routes to the separate `minimax_h3_t2v_local_v1` graph (`workflows/api/minimax_h3_t2v_api.json`); that compiler rejects any supplied media. Its own installed-node/model preflight, video+audio smoke artifact and feature flag gate availability independently from dynamic R2V. The installed text graph is validated for 5–10 seconds; referenced R2V remains 5–15 seconds. Do not call zero-reference T2V an R2V combination.
- Hosted H3 request limits and local-node slot counts are different contracts. Enforce local slot counts and measured local reference-duration/VRAM budget here; if a hosted adapter is later added, apply its own total file/duration limits separately. Never silently drop a user-selected asset to fit a budget.

The compiler must return a `ResolvedReferenceMap` **after wiring**, e.g. one paired video plus two standalone voices means `<Video 1>` = selected MP4 frames, `<Audio 1>` = its paired soundtrack, `<Audio 2>` = S1 voice and `<Audio 3>` = S2 voice. Without the paired soundtrack those voices become `<Audio 1>` and `<Audio 2>`. Pictures number in selected image order. `(S1)`/`(S2)` are stable *speaker identity* IDs and are not synonymous with `<Subject 1>` or asset array indexes. Include a prompt lint step that rejects undefined tags, unused connected references, wrong S-to-voice mappings, or a prompt claiming `fully_copy` as a guaranteed post-production action.

### Media/time and render settings

H3's local node treats reference video as **24 fps** and aligns output frames to its supported `17k+5` grid. Preflight actual source fps/duration with FFprobe; use a tested 24-fps input conversion or validated loader `force_rate=24`, with synchronized audio excerpt from the **same source interval**. When the source is 30/60 fps, do not let the image batch silently run at the wrong effective speed. Choose a short approved tail for same-scene continuity; the node trims reference frames beyond requested output length. A missing soundtrack, speech/music contamination, A/V offset or wrong time range should give a specific validation result. Temporary conversions must have a job-owner manifest and bounded cleanup.

Ricky's Resolution Selector note maps `0.98` to **1344×768** at 16:9 and `0.4` to **864×480**. Use 0.98 as proposed final preset, subject to a real smoke/VRAM result. It is **not** a quality score. Steps, scheduler, sampler, seed, `ref_image_size` (`match` vs `max`) and render tier are distinct settings. The selected API graph's wired width/height wins over the H3 node's displayed widget defaults; tests must inspect the final submitted numbers. Offer a lower preview tier, but never label it a final 0.98 render. Benchmark `max` before enabling it for many references because reference tokens can be costly.

### Staging and provenance

Keep canonical project assets once under `output/<project_id>/` (generated) or a scoped project input path (user uploads); Video Repertoire sources remain there. ComfyUI may need temporary readable files in its input tree. Stage with a unique `project/run/shot/attempt` namespace; use hardlink only when safe and allowed, otherwise a bounded temporary copy. Hash and record staged files, never accept a client absolute path, and clean **only this job's** temporary files after no queued dependency needs them. Do not delete ComfyUI outputs owned by another job. Archive the exact compiled JSON, asset map and hashes, output file probe, prompt ID, model/checkpoint versions, GPU/time measurements, and explicit cleanup outcome alongside the run manifest. Do not log the entire private story or audio bytes.

## Small execution slices and pass gates

1. **D1: Read-only baseline.** Record hashes of static API and Ricky graphs; inspect local `/object_info`, model file presence, FFmpeg, ComfyUI health and GPU memory. Unit test current static graph untouched. If ComfyUI is offline, implement parser/unit work but do not claim live readiness.
2. **D2: Typed plan + validation.** Add strict schema, safe asset resolver and output contract. Test 0/1/max counts, wrong types, missing files, path traversal, duration/fps and budget failures. No submission yet.
3. **D3: Deterministic graph compiler.** Add allowlisted nodes/links and resolved tag map. Golden tests for 0/1/9 images; 0/1/3 videos; paired/unpaired; 0/1/3 audio; mixed references. Verify original files' hashes unchanged and matched video/audio loader identity.
4. **D4: Prompt/tag and parameter check.** Compile the same reference plan twice and require byte-stable graph/reference-map apart from explicit job IDs; validate 0.98 final size, preview size, duration grid, prompt tags and all node types against live `object_info`.
5. **D5: Real smoke.** Run short disposable shots in increasing complexity: text baseline; audio-only R2V if supported; one image + one voice; one video without audio; same video with paired audio; video soundtrack plus two voices. Play the result, inspect both streams, speaker mapping, motion, sync, speed, runtime and peak GPU. Stop at an actual model/runtime failure and report it; do not bypass a failed case with fabricated success.
6. **D6: Register capability.** Expose new workflow as `minimax_h3_r2v_dynamic_v1` only for combinations that passed. Keep `minimax_text`, `minimax_references`, current I2V/WAN and Manual Director behavior unchanged. Add a feature flag or catalog state and an honest failure reason.

**Phase gate:** at least one real dynamically compiled R2V shot using video frames + **that same video's optional audio** + standalone voice produces playable local H3 video/audio, with a correct reference map and 0.98 final size or a documented resource-limited fallback. If no live smoke passes, do **not** proceed to a UI that claims the dynamic path works. Record the blocker and leave the old site operational.
