#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_OPENCLAW_ENV="$ROOT_DIR/configs/openclaw_supervisor.local.env"
export DEBIAN_FRONTEND=noninteractive
APT_PREFIX=()

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

log() {
  echo "$1"
}

configure_privilege_mode() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    APT_PREFIX=()
    return
  fi

  if have_cmd sudo; then
    APT_PREFIX=(sudo)
    return
  fi

  log "[ERROR] Root privileges or sudo are required for apt-based bootstrap."
  exit 1
}

apt_get() {
  "${APT_PREFIX[@]}" apt-get "$@"
}

ensure_base_packages() {
  apt_get update
  apt_get install -y \
    curl \
    ffmpeg \
    git \
    lshw \
    pciutils \
    poppler-utils \
    python3-pip \
    python3-venv \
    tesseract-ocr
}

validate_gpu() {
  if ! lspci | grep -qi nvidia; then
    log "[WARN] No NVIDIA GPU detected in lspci. The repo will still install, but GPU-first execution is unavailable."
    return
  fi

  if ! have_cmd nvidia-smi; then
    cat <<EOF
[ERROR] NVIDIA GPU detected but nvidia-smi is missing.
Install host NVIDIA drivers first, then rerun:
  Ubuntu example:
    sudo ubuntu-drivers autoinstall
    reboot
EOF
    exit 1
  fi

  log "[INFO] GPU visibility:"
  nvidia-smi
}

ensure_venv() {
  if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$ROOT_DIR/.venv"
  fi
  "$ROOT_DIR/.venv/bin/pip" install --upgrade pip
  "$ROOT_DIR/.venv/bin/pip" install -e "$ROOT_DIR"
}

install_ollama_if_missing() {
  if have_cmd ollama; then
    return
  fi
  curl -fsSL https://ollama.com/install.sh | sh
}

ensure_ollama_running() {
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    return
  fi

  if ! pgrep -x ollama >/dev/null 2>&1; then
    nohup ollama serve >/tmp/ollama-image-analyzer.log 2>&1 &
  fi

  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  log "[ERROR] Ollama did not become reachable on http://127.0.0.1:11434"
  exit 1
}

pull_model_if_missing() {
  local model="$1"
  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    return
  fi
  if [[ "$model" == hf.co/* || "$model" == huggingface.co/* ]]; then
    # Some Ollama builds/documented HF GGUF paths work more reliably via `run`
    # than `pull`, which can reject valid hf.co identifiers.
    OLLAMA_NOHISTORY=1 ollama run "$model" ""
    return
  fi
  ollama pull "$model"
}

install_openclaw_if_missing() {
  if have_cmd openclaw; then
    return
  fi
  curl -fsSL https://openclaw.ai/install.sh | bash
}

setup_qwen_image_backend() {
  if [[ -f "$ROOT_DIR/scripts/setup_qwen_image_backend.sh" ]]; then
    bash "$ROOT_DIR/scripts/setup_qwen_image_backend.sh"
  fi
}

setup_prompt_models() {
  if [[ -f "$ROOT_DIR/scripts/setup_prompt_models.sh" ]]; then
    bash "$ROOT_DIR/scripts/setup_prompt_models.sh"
  fi
}

choose_reasoning_model() {
  local explicit="${IMAGE_ANALYZER_REASONING_MODEL:-}"
  if [[ -n "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return
  fi

  if [[ ! -t 0 ]]; then
    printf '%s\n' "gemma4:latest"
    return
  fi

  echo "[INFO] Choose the OpenClaw reasoning model:" >&2
  echo "  1) gemma4:latest" >&2
  echo "  2) hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2:Q4_K_M" >&2
  read -r -p "Enter 1 or 2 [1]: " choice
  case "${choice:-1}" in
    2)
      printf '%s\n' "hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2:Q4_K_M"
      ;;
    *)
      printf '%s\n' "gemma4:latest"
      ;;
  esac
}

write_openclaw_local_override() {
  local reasoning_model="$1"
  cat >"$LOCAL_OPENCLAW_ENV" <<EOF
OLLAMA_REASONING_MODEL_DEFAULT="$reasoning_model"
EOF
}

main() {
  local reasoning_model

  configure_privilege_mode
  ensure_base_packages
  validate_gpu
  ensure_venv
  install_ollama_if_missing
  ensure_ollama_running
  pull_model_if_missing "qwen2.5vl:7b"
  pull_model_if_missing "qwen2.5-coder:14b"
  setup_prompt_models
  reasoning_model="$(choose_reasoning_model)"
  pull_model_if_missing "$reasoning_model"
  write_openclaw_local_override "$reasoning_model"
  install_openclaw_if_missing
  chmod +x "$ROOT_DIR"/scripts/*.sh
  log "[INFO] CLI entrypoint: ./scripts/run_image_analyzer.sh"
  log "[INFO] Unified image flow entrypoint: image-analyzer analyze-image <image_path>"
  log "[INFO] Unified batch flow entrypoint: image-analyzer analyze-batch <input_dir>"
  log "[INFO] Optional image generation setup: ./scripts/setup_image_gen.sh"
  log "[INFO] Streamlit UI entrypoint: ./scripts/run_streamlit_app.sh"
  log "[INFO] Bootstrap complete."
}

main "$@"
