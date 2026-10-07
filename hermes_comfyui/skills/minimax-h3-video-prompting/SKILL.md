---
name: minimax-h3-video-prompting
description: Use when Hermes must write or execute MiniMax H3 text-to-video, image-to-video, first/last-frame video, or image-reference-to-video prompts with synchronized native audio. Route the mode, build a chronological audiovisual prompt, then hand execution to comfyui-media-operator.
license: MIT
metadata:
  hermes:
    tags: [minimax, h3, video, audio, comfyui]
    related_skills: [comfyui-media-operator]
---

# MiniMax H3 Video Prompting

## Select Mode

- Text only: `minimax-h3-t2v`.
- Opening image, or opening and ending images: `minimax-h3-i2v`. Image 1 is first frame; image 2 is last frame.
- Images used as identity, style, object, or environment references rather than timeline anchors: `minimax-h3-r2v`.

## Write the Prompt

Write one chronological audiovisual plan containing:

- visual medium, subject, environment, lighting, and continuity anchors;
- observable action and camera behavior over time;
- exact dialogue and visible text when requested;
- synchronized physical sounds and ambience;
- non-diegetic music with instruments, tempo, and dynamic arc.

For an opening image, state that Picture 1 is fully referenced at 0.00 seconds and describe forward motion. For first/last frames, explain the continuous transition and exact final landing. For reference mode, assign every picture a specific role using `<Picture 1>`, `<Picture 2>`, and `<Picture 3>` in connection order.

Keep complexity proportional to duration: one action or up to three simple shots for 4-6 seconds. Cut timestamps must increase and remain inside the requested duration.

## Execution Handoff

If generation is requested, load `comfyui-media-operator`. Pass prompt, duration, seed, dimensions, and absolute input-image paths through its request contract. Never post the source UI workflows directly.
