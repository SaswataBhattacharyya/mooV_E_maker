#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${IMAGE_ANALYZER_MODEL_DIR:-$ROOT_DIR/models}"
YOLO_PATH="${IMAGE_ANALYZER_YOLO_MODEL:-$MODEL_DIR/yolov8n.pt}"
FLORENCE_DIR="${IMAGE_ANALYZER_FLORENCE_MODEL_DIR:-$MODEL_DIR/florence-2-large}"
YOLO_URL="${IMAGE_ANALYZER_YOLO_DOWNLOAD_URL:-https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.pt}"
export HF_HUB_DISABLE_TELEMETRY=1

log() {
  echo "$1"
}

ensure_venv() {
  if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.venv/bin/activate"
  fi
}

download_yolo() {
  mkdir -p "$(dirname "$YOLO_PATH")"
  if [[ -f "$YOLO_PATH" ]]; then
    log "[INFO] YOLO model already present at $YOLO_PATH"
    return
  fi

  log "[INFO] Downloading YOLO model to $YOLO_PATH"
  curl -L --fail "$YOLO_URL" -o "$YOLO_PATH"
}

download_florence() {
  mkdir -p "$FLORENCE_DIR"
  if [[ -f "$FLORENCE_DIR/config.json" ]]; then
    log "[INFO] Florence-2 already present at $FLORENCE_DIR"
    return
  fi

  log "[INFO] Downloading Florence-2 model to $FLORENCE_DIR"
  export IMAGE_ANALYZER_FLORENCE_TARGET="$FLORENCE_DIR"
  python - <<'PY'
import os
from pathlib import Path
from huggingface_hub import snapshot_download

target = Path(os.environ["IMAGE_ANALYZER_FLORENCE_TARGET"])
snapshot_download(
    repo_id="microsoft/Florence-2-large",
    local_dir=str(target),
    local_dir_use_symlinks=False,
)
PY
}

main() {
  ensure_venv
  mkdir -p "$MODEL_DIR"
  download_yolo
  download_florence
  log "[INFO] Prompt-support models are ready."
}

main "$@"
