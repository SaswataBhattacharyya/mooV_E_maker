#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export IMAGE_ANALYZER_YOLO_MODEL="${IMAGE_ANALYZER_YOLO_MODEL:-$ROOT_DIR/models/yolov8n.pt}"
export IMAGE_ANALYZER_FLORENCE_MODEL_DIR="${IMAGE_ANALYZER_FLORENCE_MODEL_DIR:-$ROOT_DIR/models/florence-2-large}"
export IMAGE_ANALYZER_ALLOW_MODEL_DOWNLOADS="${IMAGE_ANALYZER_ALLOW_MODEL_DOWNLOADS:-0}"

exec python -m image_analyzer.main "$@"
