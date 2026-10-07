# story_builder Workflows

This folder is the repo-local source of truth for media workflows used by the story builder ecosystem.

Subfolders:

- `templates/`: API-stable or canonical workflow templates
- `image/`: still-image and image-edit workflows
- `video/`: image-to-video, text-to-video, and sequence workflows
- `audio/`: TTS, SRT timing, and audio-related workflows

Initial workflow set copied from `Art_ist_min`:

- `templates/gsl_starter_1_1_api.json`
- `image/image_qwen_Image_2512.json`
- `image/02_qwen_Image_edit_subgraphed.json`
- `video/video_ltx2_3_flf2v.json`
- `video/video_ltx2_3_ia2v.json`
- `video/video_wan2_2_14B_i2v.json`
- `video/video_wan2_2_14B_t2v.json`
- `audio/TTS_audio_multichar_timed_wf.json`
- `audio/audio_SRT_timing.json`

Rules:

- Do not rename or mutate copied upstream workflows casually.
- If Hermes or app code needs parameterized variants, create derived copies with clear names.
- Keep repo docs in `story_builder/docs/media-composer/` synchronized with this folder.
