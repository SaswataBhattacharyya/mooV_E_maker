---
name: tts-operate-workflows
description: Inspect, explain, validate, execute, or debug TTS-Audio-Suite ComfyUI workflow JSON, including engines, Character Voices, TTS SRT, Step Audio EditX, scene nodes, models, and outputs. Use for missing nodes/models, invalid wiring, package errors, or determining whether a workflow includes generation versus post-processing.
---

# Operate TTS Workflows

Read `../_shared/references/dialogue-and-voices.md` and `../_shared/references/scene-surgery.md`.

1. Run `scripts/inspect_tts_workflow.py` with the workflow JSON path as its positional argument.
2. Trace Character Voices and engine inputs into TTS Text/SRT, then trace preview/save outputs.
3. State explicitly whether the workflow includes emotion/style editing or only generation.
4. Verify unfamiliar node semantics in source or live `/object_info`; do not infer from display labels.
5. For failures, capture the first causal exception and classify it as source, package, model, voice, language, graph, or resource failure.
6. Re-run the smallest failing import/node before retrying a long generation.

`workflows/ricky/TTS_audio_multichar_timed_wf.json` provides timed multi-character generation. The custom scene scripts/nodes are a separate post-generation route unless wired into another workflow.
