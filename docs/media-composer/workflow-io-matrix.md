# Workflow Input/Output Matrix

This file summarizes the practical input and output shapes of the current workflow library.

## API Workflows

| Workflow | Required Inputs | Optional Inputs | Outputs | Notes |
|---|---|---|---|---|
| `api/gsl_starter_1_1_api.json` | text | seed, size, negative prompt via wrapper | image | stable image API template |
| `api/qwen_2512_t2i_api.json` | text | seed, size, negative prompt | image | direct Qwen text-to-image |
| `api/qwen_2512_t2i_refine_api.json` | text, image | LoRA, refine params, seed, size | image | guided refine path |
| `api/qwen_edit_api.json` | image | edit prompt, LoRA, scaling, seed | image | edit workflow |
| `api/wan2_2_flf2v_api.json` | start image, end image, text | motion/length params | video | first/last-frame API path |

## Image Workflows

| Workflow | Required Inputs | Optional Inputs | Outputs | Notes |
|---|---|---|---|---|
| `qwen_image/image_qwen_Image_2512.json` | text | seed, size, sampling params | image | baseline still image |
| `qwen_image/02_qwen_Image_edit_subgraphed.json` | image | edit prompt | image | image edit |
| `qwen_image/qwen_multi_angle.json` | image, text/edit context | camera controls | image | multi-angle generation |
| `qwen_image/Qwen 2511 multi angle (Single Sampler)+ZImageTurbo.json` | image, text | camera controls | image | multi-angle variant |
| `qwen_image/ipadapter_controlnet_qwen.json` | image, text | controlnet/preprocessor settings | image | structure-guided image generation |
| `qwen_image/gsl_starter_1_1.json` | text | app wrapper params | image | still-image preset |

## Video Workflows

| Workflow | Required Inputs | Optional Inputs | Outputs | Notes |
|---|---|---|---|---|
| `qwen_image/video_ltx2_3_flf2v.json` | start image, end image, text | audio latent path, length, size | video | LTX first/last-frame |
| `qwen_image/video_ltx2_3_ia2v.json` | image | audio, prompt, motion params | video | image-assisted LTX video |
| `qwen_image/video_ltx2_canny_to_video.json` | image or video frames | canny preprocess params | video | control/preprocess video |
| `qwen_image/video_ltx2_depth_to_video.json` | image or video frames | depth preprocess params | video | depth-conditioned video |
| `qwen_image/video_wan2_2_14B_t2v.json` | text | LoRA, seed, length | video | Wan text-to-video |
| `qwen_image/video_wan2_2_14B_i2v.json` | image | prompt/generation params at wrapper level | video | Wan image-to-video |
| `qwen_image/video_wan2_2_14B_flf2v.json` | start image, end image, text | LoRA, timing | video | Wan first/last-frame |
| `qwen_image/video_wan2_2_14B_fun_inpaint.json` | image | prompt, inpaint/video params | video | Wan inpaint video |
| `qwen_image/wan2.1_fun_control.json` | image, video, text | control inputs such as canny | video | mixed control workflow |
| `qwen_image/LTX_2_FirstLastFrame 20260112.json` | start image, end image, text | upscale/guide params | video | older LTX variant |
| `qwen_image/ltx/1. LTX 2.3 All-In-One-1 260606-1.json` | image, video, audio | multiple advanced extras | video | broad all-in-one path |

## VFX and Specialized Workflows

| Workflow | Required Inputs | Optional Inputs | Outputs | Notes |
|---|---|---|---|---|
| `qwen_image/260330_MICKMUMPITZ_AI-VFX_PREPROCESS_1-0.json` | video | masks, depth/canny, tracking | processed images, masks, video | VFX preprocessing path |
| `qwen_image/260330_MICKMUMPITZ_AI-VFX_1-0_SMPL.json` | video, image, masks | model/mask/composite settings | video | VFX composition path |
| `qwen_image/Qwen Image Edit - Pose Studio + Camera Control 20260212.json` | image, text | pose studio and camera controls | image | pose-guided edit |
| `qwen_image/Qwen Image Edit - Pose Studio With DWPOse + Camera Control 20260212.json` | image, text | pose, DWPose, camera controls | image | richer pose-guided edit |
| `ricky/Ideogram_4_Workflow11.json` | text, image | style/model options | image | specialized image workflow |
| `ricky/anima.json` | manual inspection needed | unknown | likely image or video | advanced variant, do not expose by default |

## Audio and TTS Workflows

| Workflow | Required Inputs | Optional Inputs | Outputs | Notes |
|---|---|---|---|---|
| `qwen_image/TTS_audio_multichar_timed_wf.json` | dialogue text / role text | engine, voice bank, timing | audio | multi-character dialogue |
| `qwen_image/audio_SRT_timing.json` | text or audio context | SRT and ASR options | timing/subtitle artifacts | timing support workflow |
| `qwen_image/audio_ace_step_1_t2a_instrumentals.json` | text | music/audio params | audio | instrumental generation |
| `qwen_image/audio_ace_step_1_t2a_song.json` | text | song/audio params | audio | song generation |
| `qwen_image/audio_emotion.json` | audio, text | emotion and TTS engine options | audio, metadata | emotion-conditioned audio |
| `qwen_image/hunyuan_foley.json` | video | audio generation settings | audio, preview outputs | foley from video |
| `qwen_image/Benji modified - Multi-character dialogue ver 20260125.json` | dialogue or role prompts | role bank / clone prompt data | audio | Qwen3 TTS dialogue path |

## Ricky Variants

The `ricky/` directory contains personalized or alternate preset versions of several main workflows.

Treat them as:

- alternate presets
- tuned branches
- project-specific experiments

Do not expose them to beginners by default.

## UI Consequences

The media composer must support workflow-aware forms:

- text-only
- text + one image
- text + multiple images
- start + end image
- video input
- audio input
- advanced VFX controls

Every exposed workflow should declare:

- required inputs
- optional inputs
- output type
- recommended use case
