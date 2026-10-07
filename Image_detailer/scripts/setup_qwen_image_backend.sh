#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${IMAGE_ANALYZER_QWEN_IMAGE_SETUP_COMMAND:-}" ]]; then
  echo "[INFO] Running configured Qwen-image backend setup command."
  bash -lc "$IMAGE_ANALYZER_QWEN_IMAGE_SETUP_COMMAND"
  exit 0
fi

cat <<EOF
[WARN] Qwen-image generation backend is not installed automatically by default.

Prompt creation works without this setup. Actual image generation and similarity
comparison require a local backend command. Configure one of these before using
the optional image generation mode:

1. Backend install/setup command for bootstrap:
   export IMAGE_ANALYZER_QWEN_IMAGE_SETUP_COMMAND='...your install command...'

2. Runtime generation command used by the repo wrapper:
   export IMAGE_ANALYZER_QWEN_IMAGE_RUNNER='...your qwen-image generation command...'

Run the optional setup entrypoint:
  $ROOT_DIR/scripts/setup_image_gen.sh

This repo's stable generator entrypoint is:
  $ROOT_DIR/scripts/run_qwen_image_generation.sh

The default config already points the closed-loop pipeline to that wrapper.
EOF
