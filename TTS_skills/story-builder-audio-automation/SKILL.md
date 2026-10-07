---
name: story-builder-audio-automation
description: Create, validate, run, inspect, or retry Story Builder audio pipelines and Control-Foley jobs for Hermes. Use for ordered TTS, split, emotion/style, stitch, cleanup, music, or Foley work. Always use the trusted Story Builder runner instead of direct ComfyUI, curl, browser, or ad-hoc scripts.
---

# Story Builder Audio Automation

Working directory: `/home/riki/web_dev`. Story Builder must be running on port 3010; ComfyUI is an internal backend detail.

Use only:

```bash
python /home/riki/web_dev/story_builder/hermes_story_builder/runner/story_builder_audio.py ACTION [OPTIONS]
```

## Pipeline procedure

1. Discover blocks with `blocks`.
2. Write friendly pipeline JSON under `/tmp`; never write workflow/node JSON.
3. Call `create-pipeline --project ID --request FILE`.
4. Call `validate --project ID --id PIPELINE_ID`. Do not run unless `valid=true`.
5. Call `run --project ID --id PIPELINE_ID`.
6. Poll `status --project ID --id RUN_ID` until completed or failed.
7. Report `final_output`. Retry only a failed step with `retry --project ID --id RUN_ID --step STEP_ID`.

Bindings may reference only earlier steps: `{"step":"tts","output":"audio"}`. Split clips additionally require `clip_index`. Stitch replacements are explicit rows containing `step`, `output`, and `clip_index`.

## Control-Foley

Write one request JSON containing friendly settings and absolute upload paths where required, then run `control-foley --project ID --request FILE`.

- `text_audio`: requires `prompt`; no video/audio path.
- `text_video_audio`: requires `prompt` and `video`.
- `reference_video_audio`: requires `video` and `reference_audio`; prompt is disabled.

Poll the returned job with the Story Builder API contract or report the job ID to the user. Successful output is stored under `output/<project-id>/audio/`.

## Hard rules

- Never call port 3008, merge workflows, edit node IDs, or modify master workflow files.
- Never use `curl`, web tools, browser tools, or a newly created Python workaround for localhost.
- Never claim success from a queued job or prompt ID; require completed status and an existing output artifact.
- Preserve completed upstream pipeline steps when retrying downstream failures.
