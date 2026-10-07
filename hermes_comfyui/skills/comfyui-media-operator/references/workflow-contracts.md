# Workflow Contracts

All paths must be absolute and exist before execution.

| Workflow ID | Inputs | Output |
|---|---|---|
| `z-image-turbo` | prompt; optional width, height, seed, count | image |
| `qwen-image-2512` | prompt; optional negative prompt, width, height, seed, count | image |
| `qwen-image-edit-2511` | prompt; 1-3 input images | image |
| `qwen-image-refine-2512` | prompt; 1-2 input images | image |
| `minimax-h3-t2v` | prompt; optional width, height, duration, seed | video with audio |
| `minimax-h3-i2v` | prompt; first image and optional last image; optional duration | video with audio |
| `minimax-h3-r2v` | prompt; 1-3 reference images; optional duration | video with audio |

Request example:

```json
{
  "workflow": "qwen-image-2512",
  "prompt": "A precise model-specific prompt",
  "negative_prompt": "",
  "input_images": [],
  "input_videos": [],
  "input_audio": [],
  "width": 1280,
  "height": 720,
  "seed": 123456,
  "count": 1
}
```

MiniMax duration defaults to the workflow value. When supplied, the runner converts seconds to H3's valid 17-frame block grid at 24 fps.

Standalone video and audio references are deliberately rejected in version 1. Reference-to-video currently accepts images only.
