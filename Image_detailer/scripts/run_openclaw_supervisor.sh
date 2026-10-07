#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/configs/openclaw_supervisor.env"
LOCAL_OVERRIDE_FILE="$ROOT_DIR/configs/openclaw_supervisor.local.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config: $CONFIG_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"
if [[ -f "$LOCAL_OVERRIDE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$LOCAL_OVERRIDE_FILE"
fi

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export OLLAMA_HOST
export OLLAMA_SYNTHESIS_MODEL="${OLLAMA_SYNTHESIS_MODEL:-$OLLAMA_SYNTHESIS_MODEL_DEFAULT}"
export OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-$OLLAMA_REASONING_MODEL_DEFAULT}"
export OLLAMA_CODER_MODEL="${OLLAMA_CODER_MODEL:-$OLLAMA_CODER_MODEL_DEFAULT}"

exec python -m uvicorn image_analyzer.supervisor_app:app --host "$OPENCLAW_UI_HOST" --port "$OPENCLAW_UI_PORT"
