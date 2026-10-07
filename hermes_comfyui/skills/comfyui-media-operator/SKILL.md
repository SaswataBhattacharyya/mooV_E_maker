---
name: comfyui-media-operator
description: Use when Hermes must execute an approved image or MiniMax H3 video workflow through local ComfyUI, save generated media, inspect an execution failure, or retrieve outputs. Always use the bundled deterministic runner instead of curl, web tools, browser access, MCP, or newly written scripts.
license: MIT
metadata:
  hermes:
    tags: [comfyui, media, image, video, local-runner]
    related_skills: [image-generation-routing, minimax-h3-video-prompting]
---

# Operate ComfyUI Media Workflows

## Overview

Use the repository runner as the only execution boundary. It performs localhost communication inside trusted Python code and writes durable outputs and manifests to `output/comfyui/<run-id>/`.

## Procedure

1. Select a registered workflow using `references/workflow-contracts.md`.
2. Use the related routing skill to create the final prompt.
3. Write one request JSON outside the skill folder, normally under `/tmp`.
4. Execute exactly:

```bash
python /home/riki/web_dev/story_builder/hermes_comfyui/runner/comfyui_runner.py run --request /absolute/path/request.json
```

5. Parse the single JSON object printed to stdout.
6. On success, read the returned `result.json` and report its absolute output paths.
7. On failure, report `error_type` and `error`. Fix the stated prerequisite or request; do not create another runner.

Completion requires `status=completed`, at least one returned output, and an existing `result.json`.

## Hard Rules

- Never use `curl`, `web_fetch`, browser tools, or direct localhost tools for ComfyUI.
- Never create an ad-hoc Python script to replace the runner.
- Never submit UI-format workflows or arbitrary workflow paths.
- Never edit master workflow JSON.
- Never claim generation succeeded merely because submission returned a prompt ID.
- Do not retry an identical model/node error.

## Common Failures

- `RequestError`: correct the request fields or selected workflow.
- `ComfyUIError` mentioning connection: start or repair ComfyUI on port 3008.
- Rejected workflow: inspect the first missing node/model in the returned ComfyUI detail.
- Timeout: report the prompt ID and inspect ComfyUI runtime state before retrying.
