#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[INFO] Setting up optional image generation and comparison path."

if [[ -x "$ROOT_DIR/scripts/setup_qwen_image_backend.sh" ]]; then
  "$ROOT_DIR/scripts/setup_qwen_image_backend.sh"
else
  echo "[WARN] Missing backend helper: $ROOT_DIR/scripts/setup_qwen_image_backend.sh" >&2
fi

echo "[INFO] Optional image generation setup finished."
