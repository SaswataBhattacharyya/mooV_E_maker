# 8. Current gaps and questions for reviewers

This is a review checklist, not a claim that every item is a defect. A reviewer should compare these questions with the desired product and choose which tradeoffs to lock down.

## Product-level questions

1. **What is the canonical end-to-end journey?** Should the main path be Story Builder → artifact approval → image/voice/video pages, or should users enter a multi-page Manual/Semi/Full production wizard?
2. **What is the boundary between project folders and Video Repertoire?** Which outputs are project-owned, globally reusable, or merely temporary? What exactly should deleting a project/job remove?
3. **What does “automation complete” mean?** Is it prompt/artifact creation, generating every asset, editing/retrying, final video assembly, or all of those?
4. **Which steps require explicit user approval?** Current UI exposes editable artifacts and has some approval semantics, but the future plan describes a more deliberate staged Director.
5. **Which provider is intended for which jobs?** Current global selector covers story/director reasoning only. Media generation is ComfyUI/model workflow work. Should the app expose provider/model choice per stage later?

## Story and prompt questions

- Should generated artifacts be allowed to exceed a single model response by using chunked generation and reconciliation? Current stage calls are single structured requests.
- What are the desired length targets for story, characters, scenes, dialogue, and image prompts?
- Which facts are locked canon vs editable suggestions?
- Should the Director review each artifact immediately or only issue a shot plan after all story artifacts exist?
- How should a retry incorporate reviewer feedback, previous failure, and output validation?
- Should the prompt text itself be visible/exportable to the user for every stage?
- Do users need reusable custom story styles imported from PDF/Markdown/plain text? This remains a separate plan from built-in style JSON.

## Generation/workflow questions

- Which ComfyUI workflows are the supported production contract, and who owns their versioning?
- Should a missing/unloaded model block a workflow before submission or allow a job to fail with diagnostics?
- Are character reference packs canonical per project? How many angles, image variants, and identity constraints are expected?
- How should voice, transcript, reference audio, reused dialogue, and generated soundtracks be distinguished in UI and output manifests?
- Does a scene’s video prompt need scene context, previous-shot continuity, first/last frame, character refs, voice refs, or a reference clip? These inputs vary by workflow.
- How should clip duration, resolution, seed, steps/quality, and GPU cost be exposed without allowing invalid combinations?

## Video/audio questions

- Does every analysis run need InternVideo3 full-video and per-clip summaries, or should shorter videos use one-pass analysis and long videos use clip-wise then global reconciliation?
- Which cut detector is authoritative, and should users be able to merge/split scenes manually?
- Which audio products are saved by default: source bitstream, analysis WAV, preview MP3, stems, detected events, isolated SFX, long speaker turns, music regions?
- What counts as a voice example worth saving (e.g., minimum contiguous duration and clean speech threshold)?
- Are sound event classes enough, or should selected classes be isolated into separate SFX files via SAM Audio?
- Should same-label SFX be grouped as candidates but retained as distinct events unless audio is genuinely duplicate?
- Which languages should ASR support, and how should uncertain/mixed-language transcripts be presented?
- Does semantic search rank video, scene, cut, transcript, voice, music, and SFX in one result list or separate tabs/types?
- If the PE-AV query worker is offline, should a request fail closed, auto-start the worker, or clearly fall back to word search?

## Reliability and safety questions

- What is the GPU memory budget and concurrency rule across ComfyUI, Ollama, and analyzer workers? Should one orchestrator reserve the GPU and unload models between jobs?
- Which services should the launcher automatically start/stop? The current launcher starts dependencies if offline but does not establish a complete global GPU lifecycle manager.
- What are retention/cleanup rules for failed runs, temporary SAM previews, cached embeddings, and job logs?
- Can a stop request terminate child/container GPU work reliably? Is delete allowed during a running job or must stop finish first?
- What metadata must be retained to reproduce a generation: exact prompt, style version, provider/model, workflow JSON revision, inputs, seeds, model checkpoint hashes, environment versions?
- Which model/checkpoint licenses and source permissions apply to the user's intended private repository? Code license and weights license may differ.

## Visible copy and implementation mismatches to review

- Home page copy calls Automation “reserved” even though story automation and audio-pipeline APIs/UI exist.
- AppShell labels the Ollama provider “current” although backend metadata returns the configured model; ensure copy identifies actual selected model and default correctly.
- README/legacy docs may describe Hermes/OpenClaw while current reasoning adapter exposes Codex and Ollama; update operational docs from source truth.
- `/video-summariser` and `/video-repertoire` are the same page, although the backend preserves a legacy analysis backend.
- “Reference audio/video” uploads must not imply a mapped workflow consumes them. Current explicit Manual Director graph slots are narrower.
- Video UI may show toggles for stages whose model is unavailable; controls should pair with per-model readiness and honest run status.

## How to submit useful feedback

For each comment, identify:

1. Page/route and user goal.
2. Current behavior you observed (include project/job ID if relevant, but no credentials).
3. Desired behavior and expected output.
4. Whether this is a must-have, default, or optional enhancement.
5. What data should be kept/deleted and what must remain recoverable.
6. Any workflow/model limits or latency/GPU constraints.

