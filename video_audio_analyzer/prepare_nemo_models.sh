#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT_DIR/models/nemo"
docker run --rm --gpus all --network host \
  --entrypoint python3 \
  -e PYTHONPATH=/app/src:/opt/perception_models \
  -v "$ROOT_DIR/models:/models" \
  -v "$ROOT_DIR/scripts:/app/scripts:ro" \
  video-audio-analyzer-audio:dev \
  /app/scripts/prepare_nemo_models.py "$@"
