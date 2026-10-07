---
name: tts-audio-suite-router
description: Route work involving this repository's TTS-Audio-Suite, voices, character aliases, multilingual dialogue, emotion/style editing, scene splitting/stitching, ComfyUI TTS workflows, or F5-TTS datasets and fine-tuning. Use when a request spans multiple TTS concerns or the correct specialized TTS skill is unclear.
---

# Route TTS Audio Suite Work

Classify the request, then read and follow the matching sibling skill.

- Story, screenplay, dialogue, timestamps, SRT, or edit manifest: `../tts-author-story-dialogue/SKILL.md`
- New/reference voices, `.txt`, aliases, character mapping, or language: `../tts-manage-voices-languages/SKILL.md`
- Emotion, style, speed, laughter, whisper, or Step tags: `../tts-direct-emotion-style/SKILL.md`
- Split, batch edit, replace a voice, concat, stitch, or preserve timing: `../tts-run-scene-surgery/SKILL.md`
- Inspect, execute, or debug ComfyUI workflow JSON: `../tts-operate-workflows/SKILL.md`
- Dataset preparation or actual model fine-tuning: `../tts-prepare-f5-finetune/SKILL.md`

Use multiple skills when necessary. Default a story-production request to clean timed SRT plus separate edit JSON, then scene surgery. Distinguish reference-based voice cloning from fine-tuning. Never promise fine-tuning for an engine without a repository-supported training path.
