# Concrete contracts and state examples (implementation guide)

Use these examples as **schemas to refine**, not as proof the current backend already stores them. Keep old `ProjectStore` artifact fields compatible. Use Pydantic/TypeScript declarations with constrained enums, IDs, revision numbers and bounded strings; never accept client-chosen absolute paths or raw graph JSON.

## 1. Run snapshot

```json
{
  "run_id": "prod2-...", "project_id": "story-...", "schema_version": 1,
  "status": "running", "current_stage": "shot_composer",
  "control_mode": "semi", "making_route": "direct_h3",
  "semi_gates": {
    "story_scene_review": false, "image_choice": false,
    "voice_choice": true, "video_choice_render": true
  },
  "story_revision_id": "story-r3", "canon_revision_id": "canon-r7",
  "provider": {"adapter": "codex_cli", "model": "gpt-6-luna", "version": "..."},
  "style": {"production_type": "story_film", "variant_id": null, "resolved_version": "..."},
  "visual_treatment_id": "...", "h3_rules_version": "...",
  "capability_snapshot_id": "...", "created_at": "...", "updated_at": "..."
}
```

`control_mode` answers **who decides**; `making_route` answers **whether visual masters are prepared**. A short story string already exists in the project and is mandatory before this run can be created. A switch of mode/route is a versioned run event, not mutation of old accepted shots.

## 2. Project asset record

```json
{
  "asset_id": "asset-uuid", "project_id": "story-...", "kind": "image",
  "role": "character_master", "character_id": "char-uuid", "scene_id": null,
  "source": "generated_project", "owner_root": "project_output",
  "canonical_relative_path": "characters/char-uuid/master-v2.png",
  "sha256": "...", "mime": "image/png", "bytes": 12345,
  "width": 1536, "height": 1536, "duration_seconds": null,
  "workflow_id": "qwen_2512_t2i_v1", "model_id": "...", "seed": 42,
  "creation_prompt_revision_id": "imgprompt-r2", "input_asset_ids": [],
  "accepted": true, "revision": 2, "created_at": "..."
}
```

An external `video_repertoire` item instead stores its **repertoire asset ID and allowed content URL**; it is not copied to the project output. Temporary ComfyUI staging is not a new canonical asset. User uploads have project-owned input paths and explicit source/consent provenance.

## 3. Shot plan versus reference plan

`ShotPlan` is the Director's **creative/narrative** decision. `ReferencePlan` is the validated **media wiring** decision for one take. Keep them separate so Refine can change language without changing a file connection, and a reference reorder can invalidate the prompt before submission.

```json
{
  "shot_id": "scene-001-cut-002", "scene_id": "scene-001", "plan_revision": 5,
  "making_route": "direct_h3", "workflow_family": "minimax_h3_r2v_local_v1",
  "duration_seconds": 8.0,
  "characters": ["char-maya", "char-arjun"], "world_state_id": "apartment-night-r1",
  "speaker_bindings": {"S1": "voice-maya", "S2": "voice-arjun"},
  "dialogue": [{"speaker_id":"S1","language":"English","text":"We have to leave.","start_sec":1.5,"end_sec":3.0}],
  "shot_intent": "continue Maya's warning inside the apartment",
  "camera": "slow medium push-in", "light": "cool window light",
  "previous_accepted_take_id": "take-scene-001-cut-001-v1",
  "main_prompt_revision_id": "h3prompt-r4", "review_rubric": ["same Maya voice", "apartment geography", "no copied old line"],
  "reference_plan_revision_id": "refs-r3", "status": "validated"
}
```

```json
{
  "reference_plan_revision_id": "refs-r3", "shot_id": "scene-001-cut-002",
  "images": [{"asset_id":"asset-maya-still","role":"character_identity","intent":"Use her face and coat; not the background"}],
  "videos": [{"asset_id":"asset-prior-take","start_sec":5.0,"end_sec":8.0,"role":"previous_cut_state","intent":"Continue camera direction and current body positions","include_paired_soundtrack":true,"audio_intent":"Carry room tone but do not repeat the spoken sentence"}],
  "standalone_audios": [{"asset_id":"voice-maya-excerpt","speaker_id":"S1","role":"voice_timbre","intent":"New dialogue in this timbre"}],
  "resolution_preset":0.98,"steps":20,"ref_image_size":"match","seed":42,
  "validated_against": {"capability_snapshot_id":"...","shot_plan_revision":5,"input_hash":"..."}
}
```

The compiler's result must then explicitly say: `<Picture 1>` = Maya still; `<Video 1>` = prior take interval; `<Audio 1>` = the *same* prior take's paired soundtrack; `<Audio 2>` = Maya voice excerpt (`S1`). The Director's final H3 prompt must agree. If `include_paired_soundtrack` becomes false, Maya voice becomes `<Audio 1>` and the old prompt is **stale**, not silently reused.

For a fresh scene, omit `previous_accepted_take_id` and that prior video unless a deliberate match-cut exception is recorded; retain the global character/world text canon and optional accepted stills. For a Direct H3 first shot, `images` may be empty and standalone voice refs may be present; this combination needs live R2V smoke before being advertised.

## 4. Asset intent and Refine result

The per-asset `intent` above is **not** a second H3 prompt. The main H3 prompt is one authored document. A Refine request names prompt revision, shot plan revision, reference plan revision and an optional user instruction (“Make the dolly-in slower; use Picture 1 only for Maya's coat”). The result is:

```json
{
  "proposal_id":"...", "base_prompt_revision_id":"h3prompt-r4",
  "proposed_prompt":"...", "change_summary":["..."],
  "lint":{"ok":true,"warnings":[]},
  "input_revision_hash":"...", "provider_model":"...", "h3_rules_version":"..."
}
```

UI shows diff and Accept/Edit/Discard. Nothing about this response directly modifies the graph, asset order or accepted prompt. If the input hash changed while the provider was thinking, return `stale_proposal` and request another refinement.

## 5. Dependency queue example

```text
Cut 1: running (ComfyUI prompt p1)
Cut 2: waiting_for_predecessor (approved Manual draft hash h2; not submitted)
Cut 3: draft (user may edit)

Cut 1 → needs_review → accepted as take t1
  → Cut 2 binds approved t1 tail, recompiles references and tags
  → if its approved draft hash is still h2 and validation passes: queued → running
  → otherwise: waiting_for_user / needs_review, no GPU submission
```

The **Generate & Next** button for Cut 2 authorizes this conditional future submission. A parent retake produces a new take ID and invalidates the child binding; it never silently overwrites t1 or changes a running child. The backend stores idempotency keys and submitted ComfyUI prompt IDs so browser retries/restarts do not duplicate work.

## 6. Error example

```json
{
  "code":"PAIRED_AUDIO_MISSING", "message":"Video 1 has no audio track. Turn off ‘Include this video's audio’ or choose a source with sound.",
  "stage":"reference_validation", "asset_id":"asset-prior-take",
  "retryable":false, "correlation_id":"...", "details":{"slot":"ref_video_audio_0"}
}
```

Use equivalent typed errors for `VOICE_NOT_ELIGIBLE`, `REFERENCE_FPS_MISMATCH`, `PROMPT_TAG_STALE`, `PREDECESSOR_NOT_ACCEPTED`, `MODEL_UNAVAILABLE`, `GPU_BUDGET_EXCEEDED`, `COMFYUI_NODE_MISSING`, `OUTPUT_AUDIO_MISSING`, etc. The UI turns these into inline guidance and a toast; routine logs never expose an API key or raw personal audio.
