#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APT_PREFIX=()
ANALYSIS_MODEL="${VIDEO_SUMMARIZER_ANALYSIS_MODEL:-qwen3.6:35b}"

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

choose_apt_mode() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    APT_PREFIX=()
    return 0
  fi

  local mode="${SETUP_ENVIRONMENT:-}"
  if [[ -z "$mode" && -t 0 ]]; then
    read -r -p "Install mode for apt packages? [local/vm] (default: local): " mode
  fi
  mode="${mode:-local}"

  case "$mode" in
    vm|VM)
      APT_PREFIX=()
      ;;
    local|LOCAL|Local)
      if have_cmd sudo; then
        APT_PREFIX=(sudo)
      else
        echo "sudo is required for local installs but was not found." >&2
        exit 1
      fi
      ;;
    *)
      echo "Unknown install mode: $mode. Use 'vm' or 'local'." >&2
      exit 1
      ;;
  esac
}

ensure_linux_deps() {
  local packages=(curl ffmpeg python3-venv python3-pip pciutils lshw tesseract-ocr)
  local missing=()
  local pkg

  for pkg in "${packages[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi

  if ! have_cmd apt-get; then
    echo "Missing required system packages: ${missing[*]}" >&2
    exit 1
  fi

  choose_apt_mode
  echo "Installing missing system packages with apt: ${missing[*]}"
  "${APT_PREFIX[@]}" apt-get update
  DEBIAN_FRONTEND=noninteractive "${APT_PREFIX[@]}" apt-get install -y "${missing[@]}"
}

install_ollama_if_missing() {
  if have_cmd ollama; then
    return 0
  fi
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
}

ensure_ollama_running() {
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    return 0
  fi
  if ! pgrep -x ollama >/dev/null 2>&1; then
    echo "Starting Ollama service..."
    nohup ollama serve >/tmp/ollama.log 2>&1 &
  fi
  sleep 3
}

pull_model_if_missing() {
  local model="$1"
  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    echo "Model already present: $model"
    return 0
  fi
  echo "Pulling model: $model"
  ollama pull "$model"
}

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
fi

ensure_linux_deps
install_ollama_if_missing
ensure_ollama_running
pull_model_if_missing "$ANALYSIS_MODEL"

export PYTHONPATH="$ROOT_DIR/src:${PYTHONPATH:-}"
export VIDEO_SUMMARIZER_ANALYSIS_MODEL="$ANALYSIS_MODEL"
export VIDEO_SUMMARIZER_YOLO_MODEL="${VIDEO_SUMMARIZER_YOLO_MODEL:-$ROOT_DIR/models/yolov8m.pt}"
export VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR="${VIDEO_SUMMARIZER_FLORENCE_MODEL_DIR:-$ROOT_DIR/models/florence-2-large}"
export VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS="${VIDEO_SUMMARIZER_ALLOW_MODEL_DOWNLOADS:-0}"

python -m video_scene_summarizer.main
