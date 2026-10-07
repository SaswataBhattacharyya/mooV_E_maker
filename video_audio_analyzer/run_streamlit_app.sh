#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export VIDEO_SUMMARIZER_YOLO_MODEL="${VIDEO_SUMMARIZER_YOLO_MODEL:-$ROOT_DIR/models/yolov8m.pt}"
export VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR="${VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR:-$ROOT_DIR/models/florence-2-large}"
export VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS="${VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS:-0}"

STREAMLIT_HOST="${STREAMLIT_HOST:-0.0.0.0}"
DEFAULT_STREAMLIT_PORT="${STREAMLIT_PORT:-3020}"
STREAMLIT_PORT="$DEFAULT_STREAMLIT_PORT"

if [[ -t 0 && -z "${STREAMLIT_PORT_PRESET:-}" ]]; then
  read -r -p "Enter Streamlit port [${DEFAULT_STREAMLIT_PORT}]: " USER_PORT
  if [[ -n "${USER_PORT}" ]]; then
    STREAMLIT_PORT="$USER_PORT"
  fi
fi

PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "[INFO] Starting Streamlit on ${STREAMLIT_HOST}:${STREAMLIT_PORT}"
echo "[INFO] Local URL: http://localhost:${STREAMLIT_PORT}"
if [[ -n "${PRIMARY_IP}" ]]; then
  echo "[INFO] VM URL: http://${PRIMARY_IP}:${STREAMLIT_PORT}"
fi

exec python -m streamlit run "$ROOT_DIR/src/video_scene_summarizer/streamlit_app.py" \
  --server.address "$STREAMLIT_HOST" \
  --server.port "$STREAMLIT_PORT"
