---
name: tts-run-scene-surgery
description: Safely operate the custom batch audio split, enriched-manifest, Step Audio EditX or voice-change routing, and numbered/timed reassembly pipeline. Use when selected ranges of a generated or existing scene need emotion, style, speed, sound, cleanup, or voice replacement while untouched audio remains intact.
---

# Run Scene Surgery

Read `../_shared/references/scene-surgery.md` and `../_shared/references/emotion-style-catalog.md`.

1. Preserve the original scene and create a new output directory.
2. Validate edit ranges and values with `../tts-author-story-dialogue/scripts/validate_scene_package.py` when an SRT is available.
3. Split the full scene. Confirm the splitter generated leading/trailing and between-edit untouched clips plus enriched JSON.
4. Partition routes when helpful. Run model-backed editing with the ComfyUI Python environment and `--keep-originals`.
5. Build the final clip directory by selecting edited targets and untouched originals in numeric order.
6. Use ordinary concat when clip durations already embody timing; use timed concat only for an explicit gap manifest.
7. Verify order, duration, gaps, transitions, intelligibility, voice identity, and edit strength. Never delete source/intermediate files before acceptance.

The current multi-character SRT workflow is generation-only; this skill supplies the explicit post-generation surgery stage.
