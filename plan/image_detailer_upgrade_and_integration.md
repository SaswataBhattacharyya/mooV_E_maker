# Image Detailer + Video Intelligence Upgrade Plan

**Status:** Core analyzer, shared contracts, asynchronous runs, video-frame integration, reference APIs and Story Builder UI are implemented and smoke-tested; optional specialist expansion and live-corpus quality validation remain graceful/incremental.  
**Scope:** upgrade the Image Detailer, embed it in `video_summariser`, and expose both image and video analysis in Story Builder.

## 1. Outcome

The system will have one reusable visual-intelligence layer:

`image/video input → frame selection/crops → specialist evidence → Qwen 3.6 visual reasoning → structured evidence packet → searchable references and generation-ready prompt`

Qwen 3.6 through Ollama is the primary, inexpensive VLM. It should not be asked to guess pixel-level facts alone. Optional computer-vision specialists provide measurable evidence (boxes, masks, depth, OCR, pose, colour and similarity), which Qwen interprets and reconciles. Hermes/GLM is not required for this plan; it may be added later as an escalation model without changing the contract.

### Implementation status

- **Completed:** reusable Image Detailer facade, Qwen/Ollama analysis, YOLOv8 Medium evidence, docTR OCR with word regions, Florence-2 caption evidence (including Transformers compatibility handling), optional-provider evidence collection, structured fallback output, upload API, Story Builder Image Detailer page, navigation entry, Florence offline guard, Python/build checks, live Ollama smoke test with `plan/image.png`, API upload smoke test, and Playwright page smoke test.
- **Implemented in this pass:** versioned evidence/run contracts, persistent cancellable analysis runs, staged progress/events, generation-brief artifacts, safe artifact serving, project vision-run API, video-asset visual-analysis scheduling, visual-evidence artifacts for retained keyframes, reference search/promotion aliases, and Image Detailer progress/cancel/frame-card UI.
- **Graceful optional boundaries:** masks/depth/pose/embedding providers remain independently optional and are reported as unavailable rather than downloaded or fabricated. Live quality validation still depends on the actual curated videos and model services available at runtime.
- **Now wired:** local Depth Anything V2 Small (`VIDEO_SUMMARIZER_DEPTH_MODEL`), ViTPose whole-body ONNX evidence, DINOv3 embedding hook, and ComfyUI SAM3/SAM3.1 capability detection. SAM3 masks/tracking are routed through the live ComfyUI node contract when that service is available; the analyzer never fabricates masks when it is offline.

## 2. Current baseline and gaps

### Already available

- `video_summariser/src/video_scene_summarizer/models/qwen_vl.py` and the scene/frame/audio pipeline.
- Scene detection, key-frame extraction, continuity metrics, Ollama calls, reports and repertoire artifacts.
- The standalone Image Detailer prototype in `/tmp/image_detailer_review/src/image_analyzer`.
- Existing Story Builder project storage, media-job APIs, ComfyUI integration and Playwright coverage.

### Not yet sufficient

- Image Detailer is a prototype loop, not a stable service contract shared with video analysis.
- A single caption/vision response is not enough for reliable camera, lighting, identity or continuity decisions.
- Specialist outputs are not yet fused into a versioned, provenance-preserving schema.
- Video repertoire does not yet run the full detailer interrogation over selected frames or make those results searchable/reusable by the Story Builder.
- There is no end-to-end Story Builder page for launching, inspecting, approving and exporting visual evidence.

## 3. Canonical data contract (Phase 0)

Create versioned Pydantic/JSON schemas before changing execution code.

- `AnalysisRun`: run id, input SHA-256, source type, model/provider versions, configuration, timestamps, status, errors.
- `VisualEvidencePacket`: dimensions, scene summary, entities/characters, objects, actions, composition, camera/lens/framing, lighting, colour palette, mood, pose, depth ordering, text/OCR, uncertainty and provenance for every field.
- `RegionEvidence`: normalized box/polygon/mask path, label, confidence, crop path and source specialist.
- `ContinuityEvidence`: entity matches, visual embedding distance, colour/camera/lighting deltas and a human-readable explanation.
- `GenerationBrief`: approved facts, references, negative constraints, camera/lighting instructions and unresolved questions; never silently invent missing values.

Every result is immutable and linked to its run. Cache keys are input hash + model versions + specialist configuration, so re-running a frame is deterministic and cheap.

## 4. Phase 1 — upgrade Image Detailer into a reusable analyzer

1. Preserve the useful interrogation loop: broad overview → scene memory → highest-impact unknown → focused question → bounded repeat → reconstruction-ready brief. Add `max_passes`, confidence thresholds and cancellation so it cannot loop forever.
2. Add deterministic preprocessing: EXIF/size validation, letterbox-safe resize, full-frame plus tiled/cropped views, optional face/character/object crops, and perceptual hash.
3. Require structured Qwen output (JSON schema) for scene, characters, objects, action, camera, lighting, tone, composition, text and uncertainty. Keep the raw response for audit and retry invalid JSON once with a repair prompt.
4. Add optional specialist adapters with graceful degradation:
   - Florence-2 for captioning, detection, grounding, segmentation and OCR.
   - GroundingDINO + SAM 2 (or the maintained Grounded-SAM-2 composition) for phrase-grounded boxes and accurate masks.
   - Depth Anything V2 for relative depth and occlusion ordering.
   - PaddleOCR for readable text/signs.
   - MMPose for human pose/keypoints where available.
   - CLIP/DINO-style embeddings for reference search and continuity similarity.
   - Lightweight colour/brightness/edge statistics for palette and lighting evidence.
5. Build an evidence-fusion step: specialists supply facts and confidence; Qwen explains relationships, resolves conflicts, labels uncertainty and proposes the next question. No specialist or VLM may claim a fact without provenance.
6. Produce artifacts per run: `input`, `overview.json`, `passes/pass-*.json`, crops, masks, depth, OCR, embeddings, `evidence.json`, `generation_brief.json`, `report.md` and a machine-readable manifest.
7. Keep generation/similarity restart support, but make generation optional. Analysis must work when ComfyUI is unavailable.

## 5. Phase 2 — integrate the analyzer into `video_summariser`

Add a shared package under `video_summariser/src/video_scene_summarizer/vision/`:

`contracts.py`, `config.py`, `qwen_client.py`, `preprocess.py`, `specialists.py`, `interrogator.py`, `fusion.py`, `cache.py`, and `service.py`.

- Put the existing `qwen_vl.py` behind the new provider interface; preserve current public calls and tests.
- Use configurable `OLLAMA_HOST` and `OLLAMA_VISION_MODEL` (default to the locally installed Qwen vision-capable tag after a startup capability check). Never hard-code a model that is not discovered.
- For each detected scene, select representative, boundary, motion/change and diversity keyframes. Run quick analysis on all selected frames and deep interrogation only on approved/high-value frames.
- Supply temporal context (previous/next frame and timestamps) to the continuity pass, while keeping each frame’s evidence independently auditable.
- Reuse the existing audio extraction/transcription metadata to align speech/music/effects with visual intervals; do not couple this plan to manual audio reconstruction or ACE fine-tuning.
- Keep current direct video summarization behavior as a fallback if specialists or deep analysis are unavailable.

## 6. Phase 3 — video repertoire and reference intelligence

- On imported/downloaded videos, retain source metadata, scene boundaries, keyframes and short preview clips.
- Run Image Detailer on retained keyframes; store `visual_evidence.json`, masks/depth/OCR/pose assets, embeddings and links to scene/time ranges.
- Add searchable facets: character/entity, action, camera/framing, lighting, palette, mood, text, confidence and source timestamp. Use embeddings for semantic search, but show the evidence that justified every match.
- Add “promote as reference” to copy an approved frame/crop/brief into a project reference set. Preserve source attribution and license notes.
- Keep extracted audio and Demucs stems linked to the same timeline; visual analysis must not pretend to understand an audio stem that was not actually analyzed.

## 7. Phase 4 — Story Builder backend integration

Implement asynchronous, cancellable jobs in the existing FastAPI service (do not expose ComfyUI directly to the browser):

- `POST /api/vision/images/analyze`
- `POST /api/projects/{project_id}/vision/runs`
- `GET /api/vision/runs/{run_id}` and `/events` (progress/diagnostics)
- `GET /api/vision/runs/{run_id}/artifacts/{path}`
- `POST /api/video-repertoire/assets/{asset_id}/vision`
- `GET /api/vision/references/search`
- `POST /api/vision/references/{reference_id}/promote`

Jobs report stages (`preprocess`, `specialists`, `qwen`, `fusion`, `continuity`, `export`), progress, warnings and retryable failures. Store under the existing project root, adding `visual_analysis/` and `references/`; final media remains in the established `output/` layout and analysis artifacts remain versioned under `artifacts/`.

When a generation workflow is requested, convert the approved `GenerationBrief` into allow-listed ComfyUI fields and references, validate against live `/object_info`, submit/poll the API graph, and attach the exact input evidence and workflow revision to the job. Analysis itself must remain usable without ComfyUI.

## 8. Phase 5 — Story Builder UI

Add a Visual Intelligence/Image Detailer workspace and integrate compact panels into Video Repertoire and scene generation:

- Select/upload an image, frame or repertoire asset; choose Quick, Balanced or Deep analysis and specialist toggles.
- Show a staged progress timeline, cancel/retry controls and clear fallback warnings.
- Present the image with selectable boxes/masks/depth overlays and synchronized crops. Tabs show Overview, Characters/Objects, Camera & Lighting, OCR, Pose/Depth, Continuity and Uncertainties.
- Show each Qwen question/pass and its evidence; allow the user to edit/approve facts, answer an unresolved question, or mark a fact unknown.
- Provide “Create generation brief”, “Use as reference”, “Compare with scene/frame”, and “Open artifact folder” actions.
- In Video Repertoire, offer timeline thumbnails, semantic filters, evidence-backed search and reference promotion.
- Add an attention queue for low-confidence/continuity failures so one problematic frame does not block unrelated work.
- Implement loading, empty, offline, malformed-model-output, partial-specialist and permission/error states; keep the UI functional when optional models are missing.

## 9. Phase 6 — generation and director hand-off

The approved brief becomes input to existing Qwen image/edit/video and ComfyUI workflows. Camera, lighting and style workflows are generation/edit stages, not substitutes for analysis. The system should:

1. Generate candidate frame(s) from the brief and references.
2. Re-analyze candidates with the same evidence contract.
3. Compare against continuity/reference thresholds.
4. Automatically retry only within a configured budget; otherwise present the discrepancy and ask the user to approve, edit the brief or choose another reference.

This keeps the future director/overseer explainable and fast: cheap Qwen analysis runs first, expensive escalation is only requested for low confidence or disagreement.

## 10. Verification plan

- Unit tests for schemas, normalization, JSON repair, confidence fusion, cache keys and graceful missing-specialist behavior.
- Fixture tests using `plan/` images/videos: exact artifact manifest, crop/mask/depth/OCR links, deterministic reruns and continuity deltas.
- Service tests with mocked Ollama/specialists and failure/retry/cancel cases.
- Playwright tests for upload, mode/toggle selection, progress, overlays, tabs, approval/editing, reference promotion, search, errors and navigation.
- Live smoke tests, one at a time, against Ollama and the existing video pipeline; record model tag, latency, GPU memory and artifact paths. Do not auto-download weights.
- Acceptance: direct image analysis works with Qwen alone; each optional specialist can be disabled independently; video repertoire retains searchable evidence; generation can consume an approved brief; no existing story/audio/repertoire route regresses.

## 11. Manual preparation and open decisions

Before implementation, confirm only these environment facts:

- The exact locally installed Ollama Qwen tag and that its `/api/show` metadata advertises image/vision input.
- Which specialist weights are already installed and their approved filesystem locations; missing specialists remain optional.
- Whether specialist inference should run in-process, as subprocess workers, or through ComfyUI nodes (default recommendation: Python adapters/workers for analysis, ComfyUI only for generation/editing).
- Storage quota and retention policy for masks, crops, embeddings and repeated runs.
- Default mode (recommend **Balanced**) and maximum automatic retry count (recommend 2).

Do not make these prerequisites: manual voice recording, ACE-Step fine-tuning, Control-Foley, Hermes/GLM, landscape generation, or automatic model downloads.

## 12. Definition of done

The upgrade is complete when one uploaded image and one retained video frame can each produce the same versioned `VisualEvidencePacket`; a video asset can populate searchable, evidence-backed references; the Story Builder can inspect/approve/export a `GenerationBrief`; and an existing ComfyUI generation job can consume that brief without breaking current routes or artifacts.

## 13. Director-focused reference intelligence upgrade

This section refines the implementation for the actual production goal: preserving useful visual and motion references without flooding project metadata with verbose or speculative text.

### 13.1 Core principle

`Video is motion truth → frames are composition truth → compact text is the searchable index.`

The system must retain the original short clip and its timestamps. Text must describe how the reference can be reused, not attempt to replace the clip.

### 13.2 Video Summariser output hierarchy

Every repertoire asset must be represented as:

```text
reference video
  → scene/cut
    → action segment
      → keyframe + frame card
```

For each action segment, store:

- source video and provenance/license metadata;
- exact start/end timestamps;
- a short playable clip;
- representative and boundary keyframes;
- aligned audio interval and transcript/effect metadata when available;
- action beats, motion direction, rhythm and camera movement;
- searchable tags and embeddings;
- links to all frame cards and raw analysis artifacts.

Example: a sword-fight reference should preserve the parry/strike sequence as a clip, identify the important contact poses and timestamps, and expose which properties can be reused (parry timing, camera tracking, lighting) versus replaced (characters, costumes, background).

### 13.3 Compact Image Detailer frame card

The normal Image Detailer result must be a small validated frame card, not a long essay:

```json
{
  "frame_id": "fight_003_key_02",
  "timestamp_sec": 12.48,
  "subjects": ["fighter_a", "fighter_b"],
  "action_state": "fighter_a parries an overhead strike",
  "composition": "medium-wide three-quarter shot",
  "camera_motion": "slight rightward tracking",
  "lighting": "cool side light with warm highlights",
  "spatial_facts": ["fighter_a left", "fighter_b right", "blade contact upper-center"],
  "reference_uses": ["pose", "sword contact", "camera angle"],
  "replaceable_parts": ["characters", "background", "costumes"],
  "confidence": 0.88,
  "uncertainties": []
}
```

Store raw model responses and detailed specialist output separately under debug artifacts. They must not be copied into the searchable scene prompt or generation brief by default.

### 13.4 Conditional interrogation loop

Use one fast analysis pass for ordinary frames. Run the deeper Qwen interrogation loop only when one of these conditions is true:

- Qwen confidence is below threshold;
- YOLO, Florence, docTR and Qwen disagree;
- an entity’s identity or position changes unexpectedly;
- camera/action/lighting is ambiguous;
- OCR is important to the reference;
- the frame is being promoted as a high-value reference;
- adjacent-frame continuity fails.

The loop must ask only targeted questions, stop after two or three follow-ups, and record the reason it ran. Example questions include whether two blades actually touch, whether movement is a camera pan or subject movement, or whether an orange region is fire or mouth lighting. It must never run indefinitely or produce repeated prose.

### 13.5 Evidence and uncertainty rules

- Separate measured facts, model interpretation and uncertainty.
- A contradictory low-confidence detector result (for example, a false “traffic light”) must be rejected or marked as a discarded contradiction.
- Transparency, alpha bounds, subject occupancy and crop padding must be measured for cutout assets.
- Camera, lighting and mood must include confidence and provenance.
- No generation prompt may include an unresolved uncertainty unless the user approves it.

### 13.6 Retrieval and director workflow

Add reference search by action, camera, lighting, mood, composition, entity and semantic embedding. Every result must show why it matched and link to its original clip/frame.

The intended workflow is:

```text
script scene
  → identify required action/camera/emotion
  → search repertoire
  → select clip or frame range
  → generate compact frame cards
  → approve reusable and replaceable properties
  → generate new character/background frames
  → compare generated frames against reference intent
  → send first frame + last frame + audio + motion brief to video generation
```

### 13.7 Safe implementation boundaries

This upgrade must not alter or delete existing Story Builder, audio, ComfyUI, project storage, revision, media-job or current video-repertoire behavior. Use additive modules, versioned artifacts and backward-compatible API fields. Existing analysis outputs remain readable; new frame cards and action segments are added alongside them.

The implementation must:

- use feature flags for deep analysis and new retrieval;
- keep optional providers independently disableable;
- avoid automatic downloads during normal application startup;
- preserve current input/output and artifact paths;
- isolate failures to the affected analysis job;
- never block unrelated projects or scenes.

### 13.8 Test and acceptance requirements

Use the supplied images and small video fixtures in `plan/` plus representative sword-fight/action clips.

- Unit-test frame-card schemas, compactness limits, confidence handling, contradiction rejection, alpha measurements and loop stop conditions.
- Test video scene/action segmentation, timestamp preservation, clip extraction and frame-to-clip links.
- Test retrieval filters and embedding results with provenance explanations.
- Test Ollama/specialist failures, retries, cancellation and cache reuse.
- Use Playwright to test upload, analysis modes, progress, compact frame-card display, ambiguity-review prompts, clip playback, timestamp navigation, reference promotion, search and error states.
- Run regression Playwright tests for existing Story Builder, Video Repertoire, Generate, Audio and Automation routes.
- Run live smoke tests against Ollama and the locally installed YOLO Medium, Florence-2 and docTR providers; record model versions and artifact paths.

### 13.9 Completion criteria

This upgrade is complete only when:

1. A normal frame produces a compact validated frame card.
2. Ambiguous frames trigger a bounded targeted loop and ordinary frames do not.
3. A video action segment retains a playable clip, timestamps and linked frame cards.
4. Search returns evidence-backed references rather than unsupported text matches.
5. A director can approve reusable/replaceable properties and export a generation brief.
6. Existing repository behavior and all unrelated routes pass regression tests.

## Recommended references

- [Grounded-SAM-2](https://github.com/IDEA-Research/Grounded-SAM-2) — grounding plus segmentation/tracking.
- [Florence-2 documentation](https://huggingface.co/docs/transformers/en/model_doc/florence2) — captioning, grounding, OCR and segmentation.
- [SAM 2](https://ai.meta.com/research/sam2/) — image/video segmentation and tracking.
- [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) — relative depth.
- [MMPose](https://github.com/open-mmlab/mmpose) — pose/keypoint evidence.
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR.
- [Qwen vision models](https://github.com/QwenLM-corp/Qwen2.5-VL) — local VLM capability reference.
