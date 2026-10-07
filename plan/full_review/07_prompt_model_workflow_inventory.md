# 7. Prompt, model, and workflow inventory

## Prompt sources

| Prompt family | Source | What it controls |
|---|---|---|
| Stage guardrails and JSON schemas | `services/story_pipeline.py` | Story, characters, scenes, subscenes, dialogue, and image jobs. Includes continuity constraints and required JSON shapes. |
| Style contracts | `prompts/styles/*.json`, style loader in services | Text-based production/story tone carried into generation calls. Current catalog is a small set of built-in styles, not user-ingested PDF style books or image/video style references. |
| Director shot planning | `services/director_pipeline.py` | Shot-level camera, lighting, tone, blocking, dialogue/audio cues, endpoint briefs, and checks. |
| Story assistance | API/service call for `/api/story/assist` | Focused story summary/questions/recommendations/revision; inspect request handler for exact prompt. |
| Image-detailer interpretation | `services/image_detailer.py` and configured local vision models | Image description/evidence. Actual model readiness is optional/runtime-dependent. |
| Video scene/clip summaries | Analyzer pipeline and InternVideo3 stage/captioner | Direct-video clip/full-video descriptions when checkpoint/runtime is available; manifest records model/stage status. |
| Codex identity review | `video_audio_analyzer/src/video_audio_analyzer/codex_director_review.py` | Compact evidence-only decision on identity/link candidates and provenance; does not replace video summary. |
| ComfyUI positive/negative prompts | Workflow graph JSON files and inferred UI defaults | Text encoded into each particular image/video/audio workflow. These can differ substantially by workflow. |

## Current story style behavior

Production style JSON is text context. The future style-ingestion library (PDF/MD/TXT, extracted rules/retrieval pack/knowledge graph) is described in `plan/story_generation_director_and_style_system_plan.md`; do not present it as already shipped. Likewise, using style/reference video frames to guide image/video generation needs dedicated reference-image/video UI and compatible workflows. A text style name alone cannot guarantee a visual style in a downstream model.

## Models and runtimes (selected examples)

| Capability | Current code/runtime pattern | Readiness caveat |
|---|---|---|
| Story reasoning | Codex CLI `gpt-6-luna` default; Ollama selectable | CLI or Ollama service/model must exist. This is a reasoning backend, not a media generator. |
| Video caption/summary | InternVideo3 adapter/checkpoint in `video_audio_analyzer` | Requires model weights and supported runtime; see manifest and worker logs for a particular run. |
| Semantic video/audio retrieval | PE-AV embeddings/query worker | Query worker must be online and index must have real PE-AV vectors; otherwise semantic mode unavailable while keyword search may continue. |
| ASR | faster-whisper adapter | Requires locally prepared model path and compatible runtime. Language detection/transcription quality varies with source audio. |
| Sound events | HTS-AT/PANNs adapters | Availability/checkpoint determines labels. Detection is not the same as sound separation or saved reusable SFX clips. |
| Diarization / speaker identity | NeMo/ECAPA adapters and optional TalkNet | Model availability and audio quality matter; speaker clusters are not named characters without evidence. |
| Source separation | Demucs | `AUTO` policy or selected stem mode; stems do not map one-to-one to semantic SFX. |
| On-demand isolation | SAM Audio worker | Optional gated model and large GPU memory requirement; only selected isolation tasks should run. |
| Music features | librosa/Essentia-related feature code | Measured tempo/energy/spectral features are different from robust mood classification. |
| Image detailer | Qwen/local CV, optional depth/segmentation/OCR components | Each component has separate install/checkpoint/readiness. |
| Media creation | Local ComfyUI workflows (e.g., image, H3, WAN, ACE-Step, TTS/Foley) | Workflow nodes/models determine actual inputs, limits, parameters, and outputs. |

## Workflow catalog rules

- A UI catalog entry is metadata; actual workflow availability and backend validation are separate.
- The dynamic Media Composer catalog scans supported JSON workflow files and infers prompts/assets/parameters.
- Manual Director uses an explicit allow-listed workflow map and explicit accepted/required reference slots.
- For each workflow, reviewers should ask: what exact graph file is used, which node receives each prompt/ref, what limits are enforced, what models/custom nodes must be loaded, and where outputs land?
- H3 product/API capabilities should not be assumed to exist in the locally installed graph. The current Manual Director mapping specifically excludes audio/video refs for its mapped H3 image-reference graph.

## Prompt quality and observability questions

For each model call, a reviewer can evaluate:

1. Is the prompt visible and stored for reproducibility?
2. Does the schema enforce complete output, or can a partial result be silently accepted?
3. Are upstream artifacts and style rules included without overwhelming context limits?
4. Are timestamps, IDs, and speaker identities consistent across assets?
5. Can the user edit/regenerate one stage without invalidating approved downstream work unexpectedly?
6. Does output metadata record provider/model/version, prompt version, inputs, seed, workflow, and runtime?
7. Are retries corrective (with error/evidence) or simply repeat the same prompt?

