#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$ROOT_DIR/venv/bin/python"
PYTHON_EXECUTABLE="${VENV_PYTHON}"
CONFIG_FILE="$ROOT_DIR/config/hermes_agent.env"
LOCAL_OVERRIDE_FILE="$ROOT_DIR/config/hermes_agent.local.env"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi
if [[ -f "$LOCAL_OVERRIDE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$LOCAL_OVERRIDE_FILE"
fi

if [[ ! -x "$PYTHON_EXECUTABLE" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_EXECUTABLE="$(command -v python3)"
  else
    echo "No usable Python executable found." >&2
    echo "Install python3 or rerun ./bootstrap_vm.sh." >&2
    exit 1
  fi
fi

export COMFYUI_HOST="${COMFYUI_HOST:-0.0.0.0}"
export COMFYUI_PORT="${COMFYUI_PORT:-3008}"
export AGENT_CONSOLE_HOST="${AGENT_CONSOLE_HOST:-0.0.0.0}"
export AGENT_CONSOLE_PORT="${AGENT_CONSOLE_PORT:-3009}"
export WEBSITE_HOST="${WEBSITE_HOST:-0.0.0.0}"
export WEBSITE_PORT="${WEBSITE_PORT:-3010}"
export START_COMFYUI="${START_COMFYUI:-true}"
export START_WEBSITE="${START_WEBSITE:-true}"
export START_AGENT_CONSOLE="${START_AGENT_CONSOLE:-true}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_CODER_MODEL="${OLLAMA_CODER_MODEL:-qwen3-coder:30b}"
export OLLAMA_VISION_MODEL="${OLLAMA_VISION_MODEL:-qwen3-vl:30b}"
export OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-qwen3.6:27b}"
export HERMES_AGENT_BASE_URL="${HERMES_AGENT_BASE_URL:-http://127.0.0.1:11434/v1}"
export HERMES_AGENT_MODEL="${HERMES_AGENT_MODEL:-$OLLAMA_REASONING_MODEL}"
export HERMES_AGENT_CODER_MODEL="${HERMES_AGENT_CODER_MODEL:-$OLLAMA_CODER_MODEL}"
export HERMES_AGENT_VISION_MODEL="${HERMES_AGENT_VISION_MODEL:-$OLLAMA_VISION_MODEL}"
export HERMES_AGENT_TIMEOUT_SECONDS="${HERMES_AGENT_TIMEOUT_SECONDS:-900}"
export OLLAMA_TIMEOUT_SECONDS="${OLLAMA_TIMEOUT_SECONDS:-900}"

if command -v hermes >/dev/null 2>&1; then
  hermes config set model.provider custom >/dev/null 2>&1 || true
  hermes config set model.default "$HERMES_AGENT_MODEL" >/dev/null 2>&1 || true
  hermes config set model.base_url "$HERMES_AGENT_BASE_URL" >/dev/null 2>&1 || true
  hermes config set model.api_key ollama >/dev/null 2>&1 || true
  hermes config set model.api_mode chat_completions >/dev/null 2>&1 || true
fi

pgrep -x ollama >/dev/null || nohup ollama serve >/tmp/ollama.log 2>&1 &

"$PYTHON_EXECUTABLE" "$ROOT_DIR/main.py"
