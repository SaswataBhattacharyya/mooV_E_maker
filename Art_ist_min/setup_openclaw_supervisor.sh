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

OLLAMA_REASONING_MODEL_DEFAULT="${OLLAMA_REASONING_MODEL_DEFAULT:-gemma4:latest}"
OLLAMA_CODER_MODEL_DEFAULT="${OLLAMA_CODER_MODEL_DEFAULT:-qwen2.5-coder:14b}"
OLLAMA_VISION_MODEL_DEFAULT="${OLLAMA_VISION_MODEL_DEFAULT:-qwen2.5vl:7b}"

SUPPORT_DIR="$ROOT_DIR/${OPENCLAW_SUPPORT_DIR}"
STATE_DIR="$ROOT_DIR/${OPENCLAW_STATE_DIR}"
mkdir -p "$SUPPORT_DIR" "$STATE_DIR"

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_openclaw_chat_completions_endpoint() {
  local config_path="${OPENCLAW_CONFIG_PATH:-$HOME/.openclaw/openclaw.json}"
  if [[ ! -f "$config_path" ]]; then
    echo "[WARN] OpenClaw config not found at $config_path yet."
    echo "[WARN] Run 'openclaw configure' or 'openclaw onboard' first, then rerun this setup or the wrapper script."
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
else:
    print(f"[INFO] OpenClaw chatCompletions endpoint already enabled in {path}")
PY
  then
    echo "[WARN] Could not auto-enable the OpenClaw chatCompletions endpoint."
  fi
}

ensure_ollama_ready() {
  if ! have_cmd ollama; then
    cat <<EOF >&2
Ollama is not installed.
Run ./bootstrap_vm.sh first so Ollama and its models are installed.
EOF
    exit 1
  fi

  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    return 0
  fi

  cat <<EOF >&2
Ollama is not reachable at http://127.0.0.1:11434
Run ./bootstrap_vm.sh first, or start Ollama manually before OpenClaw setup.
EOF
  exit 1
}

ensure_model_present() {
  local model="$1"
  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    echo "[INFO] Ollama model present: $model"
    return 0
  fi

  echo "[INFO] Pulling missing Ollama model for supervisor: $model"
  ollama pull "$model"
}

install_openclaw() {
  if have_cmd openclaw; then
    echo "[INFO] OpenClaw already installed."
    return 0
  fi

  echo "[SETUP] Installing OpenClaw..."
  curl -fsSL https://openclaw.ai/install.sh | bash
}

clone_best_effort() {
  local repo_url="$1"
  local target_dir="$2"

  if [[ -d "$target_dir/.git" ]]; then
    echo "[INFO] Support repo already present: $target_dir"
    return 0
  fi

  echo "[SETUP] Cloning optional support repo: $repo_url"
  if ! git clone "$repo_url" "$target_dir"; then
    echo "[WARN] Failed to clone optional repo: $repo_url"
  fi
}

print_next_steps() {
  cat <<EOF

OpenClaw supervisor setup is ready.

What this setup did:
  - verified Ollama is installed and reachable
  - ensured these Ollama models exist:
      reasoning: ${OLLAMA_REASONING_MODEL_DEFAULT}
      coder: ${OLLAMA_CODER_MODEL_DEFAULT}
      vision: ${OLLAMA_VISION_MODEL_DEFAULT}
  - installed OpenClaw if missing
  - cloned optional support repos (best effort):
      ${SUPPORT_DIR}/graphify
      ${SUPPORT_DIR}/ruflo

OpenClaw instruction files for this repo:
  ${ROOT_DIR}/openclaw/DUTY.md
  ${ROOT_DIR}/openclaw/KNOWLEDGE.md
  ${ROOT_DIR}/openclaw/PIPELINE.md
  ${ROOT_DIR}/openclaw/SOUL.md
  ${ROOT_DIR}/openclaw/STYLE.md
  ${ROOT_DIR}/openclaw/RUNTIME.md

If OpenClaw onboarding asks for models, choose:
  - Reasoning: ${OLLAMA_REASONING_MODEL_DEFAULT}
  - Coder: ${OLLAMA_CODER_MODEL_DEFAULT}
  - Vision: ${OLLAMA_VISION_MODEL_DEFAULT}

If you want to open this repo's optional supervisor wrapper in a browser, use:
  - Bind host on the VM: ${OPENCLAW_UI_HOST}
  - Browser port: ${OPENCLAW_UI_PORT}

Do not use ${OPENCLAW_UI_PORT} as an Ollama or OpenClaw internal gateway port.
That port belongs only to this repo's wrapper UI.

If a service on the same VM asks where Ollama is running, use:
  - Host: 127.0.0.1
  - Port: 11434

If OpenClaw is running in a different container from Ollama, do not use
127.0.0.1 unless both services share the same network namespace. Use the
other service/container hostname or bridge IP instead.

If OpenClaw does not expose a native web UI port during onboarding, this repo
provides a supervisor wrapper UI on that port via:
  ./run_openclaw_supervisor.sh

Normal daily use:
  1. ./bootstrap_vm.sh
  2. ./run_openclaw_supervisor.sh
  3. Open website: http://<vm-ip>:3010
  4. Open supervisor UI: http://<vm-ip>:${OPENCLAW_UI_PORT}

EOF
}

ensure_ollama_ready
ensure_model_present "$OLLAMA_REASONING_MODEL_DEFAULT"
ensure_model_present "$OLLAMA_CODER_MODEL_DEFAULT"
ensure_model_present "$OLLAMA_VISION_MODEL_DEFAULT"
install_openclaw
ensure_openclaw_chat_completions_endpoint
clone_best_effort "$GRAPHIFY_REPO_URL" "$SUPPORT_DIR/graphify"
clone_best_effort "$RUFLO_REPO_URL" "$SUPPORT_DIR/ruflo"
print_next_steps
