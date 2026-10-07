#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$ROOT_DIR/config/openclaw_supervisor.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config: $CONFIG_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

VENV_PYTHON="$ROOT_DIR/venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Virtualenv Python not found: $VENV_PYTHON" >&2
  echo "Run ./bootstrap_vm.sh first." >&2
  exit 1
fi

export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-${OLLAMA_REASONING_MODEL_DEFAULT}}"
export OLLAMA_CODER_MODEL="${OLLAMA_CODER_MODEL:-${OLLAMA_CODER_MODEL_DEFAULT}}"
export OLLAMA_VISION_MODEL="${OLLAMA_VISION_MODEL:-${OLLAMA_VISION_MODEL_DEFAULT}}"
export OPENCLAW_UI_HOST
export OPENCLAW_UI_PORT

ensure_openclaw_chat_completions_endpoint() {
  local config_path="${OPENCLAW_CONFIG_PATH:-$HOME/.openclaw/openclaw.json}"
  if [[ ! -f "$config_path" ]]; then
    echo "[WARN] OpenClaw config not found at $config_path. The 3009 wrapper can still start, but native OpenClaw supervision will fail until you run 'openclaw configure' or 'openclaw onboard'."
    return 0
  fi

  if ! CONFIG_PATH="$config_path" python3 - <<'PY'
import json
import os
import pathlib
import sys

path = pathlib.Path(os.environ["CONFIG_PATH"])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[WARN] Could not parse OpenClaw config at {path}: {exc}", file=sys.stderr)
    sys.exit(1)

gateway = data.setdefault("gateway", {})
http = gateway.setdefault("http", {})
endpoints = http.setdefault("endpoints", {})
chat = endpoints.setdefault("chatCompletions", {})
already_enabled = chat.get("enabled") is True
chat["enabled"] = True

if not already_enabled:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[INFO] Enabled gateway.http.endpoints.chatCompletions.enabled in {path}")
    print("[INFO] Restart the OpenClaw gateway if it is already running so the new setting takes effect.")
else:
    print(f"[INFO] OpenClaw chatCompletions endpoint already enabled in {path}")
PY
  then
    echo "[WARN] Could not auto-enable the OpenClaw chatCompletions endpoint."
  fi
}

ensure_openclaw_chat_completions_endpoint

echo "[START] OpenClaw supervisor wrapper on ${OPENCLAW_UI_HOST}:${OPENCLAW_UI_PORT}"
exec "$VENV_PYTHON" -m uvicorn supervisor_server.app:app --host "$OPENCLAW_UI_HOST" --port "$OPENCLAW_UI_PORT"
