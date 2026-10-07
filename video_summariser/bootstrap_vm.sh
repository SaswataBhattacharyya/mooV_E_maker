#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    python3-pip \
    python3-venv \
    tesseract-ocr
}

ensure_venv() {
  if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$ROOT_DIR/.venv"
  fi
  "$ROOT_DIR/.venv/bin/pip" install --upgrade pip
  "$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt"
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
    nohup ollama serve >/tmp/ollama-video-summarizer.log 2>&1 &
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
    OLLAMA_NOHISTORY=1 ollama run "$model" ""
    return
  fi
  ollama pull "$model"
}

main() {
  local analysis_model="${VIDEO_SUMMARIZER_ANALYSIS_MODEL:-qwen3.6:35b}"

  configure_privilege_mode
  ensure_base_packages
  ensure_venv
  install_ollama_if_missing
  ensure_ollama_running
  pull_model_if_missing "$analysis_model"
  mkdir -p "$ROOT_DIR/data/cache" "$ROOT_DIR/data/transcripts" "$ROOT_DIR/logs" "$ROOT_DIR/outputs" "$ROOT_DIR/out_videos" "$ROOT_DIR/artifacts"
  touch "$ROOT_DIR/data/url_list.txt" "$ROOT_DIR/data/down_url_list.txt"
  chmod +x "$ROOT_DIR"/*.sh
  log "[INFO] Combined flow entrypoint: ./run_video_scene_summarizer.sh"
  log "[INFO] Analysis entrypoint: ./run_video_analysis.sh"
  log "[INFO] Streamlit UI entrypoint: ./run_streamlit_app.sh"
  log "[INFO] Ollama analysis model: $analysis_model"
  log "[INFO] Bootstrap complete."
}

main "$@"
