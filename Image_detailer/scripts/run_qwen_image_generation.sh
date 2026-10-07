#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROMPT_FILE=""
NEGATIVE_PROMPT_FILE=""
OUTPUT_IMAGE=""
WIDTH=""
HEIGHT=""
STEPS=""
CFG=""
SAMPLER=""
SEED=""
MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt-file)
      PROMPT_FILE="$2"
      shift 2
      ;;
    --negative-prompt-file)
      NEGATIVE_PROMPT_FILE="$2"
      shift 2
      ;;
    --output-image)
      OUTPUT_IMAGE="$2"
      shift 2
      ;;
    --width)
      WIDTH="$2"
      shift 2
      ;;
    --height)
      HEIGHT="$2"
      shift 2
      ;;
    --steps)
      STEPS="$2"
      shift 2
      ;;
    --cfg)
      CFG="$2"
      shift 2
      ;;
    --sampler)
      SAMPLER="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PROMPT_FILE" || -z "$OUTPUT_IMAGE" ]]; then
  echo "[ERROR] --prompt-file and --output-image are required." >&2
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "[ERROR] Prompt file not found: $PROMPT_FILE" >&2
  exit 1
fi

if [[ -n "${IMAGE_ANALYZER_QWEN_IMAGE_RUNNER:-}" ]]; then
  export IMAGE_ANALYZER_QWEN_IMAGE_PROMPT_FILE="$PROMPT_FILE"
  export IMAGE_ANALYZER_QWEN_IMAGE_NEGATIVE_PROMPT_FILE="$NEGATIVE_PROMPT_FILE"
  export IMAGE_ANALYZER_QWEN_IMAGE_OUTPUT_IMAGE="$OUTPUT_IMAGE"
  export IMAGE_ANALYZER_QWEN_IMAGE_WIDTH="$WIDTH"
  export IMAGE_ANALYZER_QWEN_IMAGE_HEIGHT="$HEIGHT"
  export IMAGE_ANALYZER_QWEN_IMAGE_STEPS="$STEPS"
  export IMAGE_ANALYZER_QWEN_IMAGE_CFG="$CFG"
  export IMAGE_ANALYZER_QWEN_IMAGE_SAMPLER="$SAMPLER"
  export IMAGE_ANALYZER_QWEN_IMAGE_SEED="$SEED"
  export IMAGE_ANALYZER_QWEN_IMAGE_MODEL="$MODEL"
  exec bash -lc "$IMAGE_ANALYZER_QWEN_IMAGE_RUNNER"
fi

cat >&2 <<EOF
[ERROR] No Qwen-image backend runner is configured.

This repo now routes closed-loop image generation through:
  ./scripts/run_qwen_image_generation.sh

You must provide one of the following before generation can work:

1. Export IMAGE_ANALYZER_QWEN_IMAGE_RUNNER with a shell command that reads:
   \$IMAGE_ANALYZER_QWEN_IMAGE_PROMPT_FILE
   \$IMAGE_ANALYZER_QWEN_IMAGE_NEGATIVE_PROMPT_FILE
   \$IMAGE_ANALYZER_QWEN_IMAGE_OUTPUT_IMAGE
   \$IMAGE_ANALYZER_QWEN_IMAGE_WIDTH
   \$IMAGE_ANALYZER_QWEN_IMAGE_HEIGHT
   \$IMAGE_ANALYZER_QWEN_IMAGE_STEPS
   \$IMAGE_ANALYZER_QWEN_IMAGE_CFG
   \$IMAGE_ANALYZER_QWEN_IMAGE_SAMPLER
   \$IMAGE_ANALYZER_QWEN_IMAGE_SEED
   \$IMAGE_ANALYZER_QWEN_IMAGE_MODEL

2. Or replace this wrapper with a repo-local implementation that calls your
   preferred Qwen-image runtime directly.

The current request was:
  prompt file: $PROMPT_FILE
  negative prompt file: ${NEGATIVE_PROMPT_FILE:-<none>}
  output image: $OUTPUT_IMAGE
  width x height: ${WIDTH}x${HEIGHT}
  steps: $STEPS
  cfg: $CFG
  sampler: $SAMPLER
  seed: $SEED
  model: $MODEL
EOF

exit 1
