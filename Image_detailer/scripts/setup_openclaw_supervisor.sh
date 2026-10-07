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

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_ollama_ready() {
  if ! have_cmd ollama; then
    echo "Ollama is not installed. Run ./scripts/bootstrap_vm.sh first." >&2
    exit 1
  fi
  if ! curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "Ollama is not reachable at ${OLLAMA_HOST}. Run ./scripts/bootstrap_vm.sh first." >&2
    exit 1
  fi
}

pull_model_if_missing() {
  local model="$1"
  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    return
  fi
  ollama pull "$model"
}

ensure_openclaw() {
  if have_cmd openclaw; then
    return
  fi
  curl -fsSL https://openclaw.ai/install.sh | bash
}

ensure_openclaw_config_hint() {
  if [[ -f "$OPENCLAW_CONFIG_PATH" ]]; then
    echo "[INFO] OpenClaw config found at $OPENCLAW_CONFIG_PATH"
    return
  fi
  echo "[WARN] OpenClaw config not found at $OPENCLAW_CONFIG_PATH"
  echo "[WARN] Run 'openclaw configure' or 'openclaw onboard' after install."
}

main() {
  ensure_ollama_ready
  pull_model_if_missing "$OLLAMA_SYNTHESIS_MODEL_DEFAULT"
  pull_model_if_missing "$OLLAMA_REASONING_MODEL_DEFAULT"
  pull_model_if_missing "$OLLAMA_CODER_MODEL_DEFAULT"
  ensure_openclaw
  ensure_openclaw_config_hint
  echo "[INFO] OpenClaw supervisor setup is ready."
}

main "$@"
