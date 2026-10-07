# image_analyzer

Local-first image recreation agent driven by a VLM interrogation loop.

## Core flow

There is one canonical prompt-generation flow for both single images and batches:

1. Read the reference image.
2. Run a broad VLM overview.
3. Build scene memory.
4. Detect the most important missing visual detail.
5. Ask the next focused VLM question.
6. Repeat until the image is reconstruction-ready.
7. Build the final recreation text, concise prompt, and constraints.
8. Optionally generate an image.
9. Optionally compute a code-based similarity percentage.
10. If optional generation is enabled and similarity is below `80%`, restart the full process.
11. Stop when prompt outputs are ready, or when optional generation reaches its stop condition.

Auxiliary modules like YOLO, Florence, OCR, and color extraction are supporting signals only. They do not control the flow.

## Models pulled by bootstrap

`./scripts/bootstrap_vm.sh` currently pulls these prompt-generation models:

- `qwen2.5vl:7b`
- `qwen2.5-coder:14b`

Repo defaults:

- image interrogation model: `qwen2.5vl:7b`
- structuring model: `qwen2.5-coder:14b`
- supervisor/default reasoning model: selected during bootstrap

Bootstrap reasoning-model choices:

- `1` = `gemma4:latest`
- `2` = `hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2:Q4_K_M`

Automation-safe override:

```bash
export IMAGE_ANALYZER_REASONING_MODEL='gemma4:latest'
```

## Quick start

```bash
chmod +x scripts/*.sh
./scripts/bootstrap_vm.sh
./scripts/run_streamlit_app.sh
```

Optional image generation setup:

```bash
./scripts/setup_image_gen.sh
```

CLI:

```bash
image-analyzer analyze-image /path/to/image.png
image-analyzer analyze-batch /path/to/folder
```

## Bootstrap behavior

`./scripts/bootstrap_vm.sh`:

- installs system packages
- creates `.venv`
- installs the repo in editable mode
- installs Ollama if missing
- starts Ollama if needed
- pulls the default Ollama models listed above
- prompts for the OpenClaw reasoning model unless overridden by env
- installs OpenClaw if missing

`./scripts/setup_image_gen.sh`:

- sets up the optional image generation and comparison backend path
- validates or reminds you to configure the generator runner

Optional image-generation mode is not enabled by default in config or UI.

Runtime guardrails:

- repo-side Ollama calls enforce one active model at a time
- provider keep-alive is shortened so heavy models do not linger on GPU unnecessarily
- if Ollama returns a model-load/resource-limit error, the repo unloads competing models and retries once

## Unified CLI

Single image:

```bash
image-analyzer analyze-image /path/to/image.png \
  --enable-generation \
  --target-score 0.80 \
  --max-full-restarts 3 \
  --max-question-rounds 6
```

Batch:

```bash
image-analyzer analyze-batch /path/to/folder
```

`analyze-detailed` still exists as a compatibility alias, but it uses the same engine and is no longer the primary documented path.

## Streamlit

The Streamlit app uses the same unified flow.

For each image it shows:

- reference image
- generated image if optional generation is enabled and succeeds
- similarity percentage if optional generation is enabled and succeeds
- final prompt
- scene memory
- question loop history
- structured JSON outputs
- runtime errors directly in the UI

## Run artifacts

Unified runs write timestamped folders under:

```text
artifacts/detailed_runs/<timestamp>_<project>_<image>/
```

Each run contains:

```text
input/
memory/
passes/
outputs/
generated/
comparisons/
reports/
logs/
```

Important files:

- `memory/final_scene_memory.json`
- `outputs/structured_scene_map.json`
- `outputs/detailed_recreation_text.txt`
- `outputs/concise_generation_prompt.txt`
- `outputs/critical_constraints.txt`
- `generated/generated_v1.png` when generation is enabled
- `comparisons/similarity_v1.json` when generation is enabled
- `reports/run_report.json`

## OpenClaw

OpenClaw is expected to supervise this repo using the instructions under `openclaw/`.

Its main job is:

- interrogate the image with the VLM
- decide what detail is still missing
- ask the next focused question
- stop only when the image is recreation-ready

It should not treat one caption as sufficient.
If optional generation is not enabled, prompt creation is still a successful run.

## Generator backend

Optional image generation is routed through:

```bash
./scripts/run_qwen_image_generation.sh
```

The wrapper expects a real backend command through:

- `IMAGE_ANALYZER_QWEN_IMAGE_RUNNER`

If that backend is missing, generation will fail clearly.
Prompt creation will still work without it.

## Entry points

- `./scripts/bootstrap_vm.sh`
- `./scripts/run_streamlit_app.sh`
- `./scripts/run_image_analyzer.sh analyze-image <image_path>`
- `image-analyzer analyze-image <image_path>`
- `image-analyzer analyze-batch <input_dir>`
- `./scripts/setup_openclaw_supervisor.sh`
- `./scripts/run_openclaw_supervisor.sh`
