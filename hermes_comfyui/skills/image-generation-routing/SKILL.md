---
name: image-generation-routing
description: Use when Hermes must create, refine, or execute an image-generation prompt with the repository's Z-Image Turbo, Qwen Image 2512, Qwen Image Edit 2511, or Qwen refine workflows. Select the model family, produce its prompt, then hand execution to comfyui-media-operator.
license: MIT
metadata:
  hermes:
    tags: [image-generation, prompting, z-image, qwen-image]
    related_skills: [comfyui-media-operator]
---

# Route Image Generation

## Routing

- Existing image that must be changed or preserved: `qwen-image-edit-2511`.
- Existing image used for a guided refinement pass: `qwen-image-refine-2512`.
- Text-only anime, illustration, portrait, fashion, or straightforward photorealism: `z-image-turbo`.
- Text-only exact typography, many relationships, or complex spatial instructions: `qwen-image-2512`.

Honor an explicit model choice unless it cannot perform the requested operation.

## Prompt Construction

For Z-Image, write concise visual prose: subject, action, shot, setting, lighting, medium, palette, and essential constraints. Avoid generic quality-word piles.

For Qwen text-to-image, use explicit natural-language relationships, positions, exact quoted text, foreground/background, and camera geometry.

For Qwen edit, begin with `Change ONLY...`, list preservation constraints, assign each input image a role, and describe the requested change. Do not ask it to vaguely combine references.

## Execution Handoff

If the user asks only for a prompt, return the workflow ID and final prompt. If generation is requested, load `comfyui-media-operator`, create its request JSON, and run its fixed command. Do not execute ComfyUI directly.
