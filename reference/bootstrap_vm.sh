#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_HERMES_ENV="$ROOT_DIR/config/hermes_agent.local.env"
export DEBIAN_FRONTEND=noninteractive
APT_PREFIX=()
OLLAMA_REASONING_MODEL_EXPLICIT=0
OLLAMA_CODER_MODEL_EXPLICIT=0
OLLAMA_VISION_MODEL_EXPLICIT=0
[[ -n "${OLLAMA_REASONING_MODEL+x}" ]] && OLLAMA_REASONING_MODEL_EXPLICIT=1
[[ -n "${OLLAMA_CODER_MODEL+x}" ]] && OLLAMA_CODER_MODEL_EXPLICIT=1
[[ -n "${OLLAMA_VISION_MODEL+x}" ]] && OLLAMA_VISION_MODEL_EXPLICIT=1
OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-qwen3.6:27b}"
OLLAMA_CODER_MODEL="${OLLAMA_CODER_MODEL:-qwen3-coder:30b}"
OLLAMA_VISION_MODEL="${OLLAMA_VISION_MODEL:-qwen3-vl:30b}"

log() {
  echo "$1"
}

configure_privilege_mode() {
  if [[ "${EUID}" -eq 0 ]]; then
    log "[INFO] Running as root. Using apt-get directly."
    APT_PREFIX=()
    return
  fi

  if command -v sudo >/dev/null 2>&1; then
    log "[INFO] Running without root. Using sudo for apt-get commands."
    APT_PREFIX=(sudo)
    return
  fi

  if [[ -t 0 ]]; then
    log "[WARN] Script is not running as root and sudo is unavailable."
    read -r -p "Is this a VM/container where you can rerun this script as root? [Y/n] " reply
    reply="${reply:-Y}"
    if [[ "${reply}" =~ ^[Yy]$ ]]; then
      log "[ERROR] Rerun this script as root in the VM/container."
    else
      log "[ERROR] Local installation requires sudo, but sudo is not available."
    fi
  else
    log "[ERROR] Script needs root privileges or sudo for apt-get operations."
  fi
  exit 1
}

apt_get() {
  "${APT_PREFIX[@]}" apt-get "$@"
}

as_root() {
  if [[ "${#APT_PREFIX[@]}" -eq 0 ]]; then
    "$@"
  else
    "${APT_PREFIX[@]}" "$@"
  fi
}

ensure_repo_scripts_executable() {
  chmod +x \
    "$ROOT_DIR/bootstrap_vm.sh" \
    "$ROOT_DIR/setup_hermes_agent.sh" \
    "$ROOT_DIR/run_hermes_pipeline.sh"
}

ensure_base_packages() {
  apt_get update
  apt_get install -y \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    gnupg \
    libgl1 \
    libglib2.0-0 \
    lshw \
    libsm6 \
    libsamplerate0-dev \
    libxext6 \
    libxrender1 \
    lsof \
    nano \
    pciutils \
    portaudio19-dev \
    psmisc \
    python3-pip \
    python3-venv \
    tesseract-ocr \
    wget
}

ensure_node20() {
  apt_get remove -y nodejs npm libnode-dev nodejs-doc || true
  apt_get autoremove -y || true

  as_root mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | as_root gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    | as_root tee /etc/apt/sources.list.d/nodesource.list >/dev/null

  apt_get update
  apt_get -f install -y
  apt_get install -y nodejs

  node -v
  npm -v
}

detect_nvidia() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    return 0
  fi

  if lspci | grep -qi 'NVIDIA'; then
    log "[ERROR] NVIDIA GPU detected but nvidia-smi is unavailable. Install the NVIDIA driver and container runtime on the host, then retry."
    exit 1
  fi

  log "[ERROR] No NVIDIA GPU detected. This project currently expects an NVIDIA GPU-enabled environment."
  exit 1
}

select_torch_index() {
  local cuda_version="$1"
  python3 - "$cuda_version" <<'PY'
import sys

cuda_version = sys.argv[1].strip()
parts = cuda_version.split(".")
major = int(parts[0])
minor = int(parts[1]) if len(parts) > 1 else 0
code = major * 10 + minor
available = [
    (129, "https://download.pytorch.org/whl/cu129"),
    (128, "https://download.pytorch.org/whl/cu128"),
    (126, "https://download.pytorch.org/whl/cu126"),
    (124, "https://download.pytorch.org/whl/cu124"),
    (121, "https://download.pytorch.org/whl/cu121"),
    (118, "https://download.pytorch.org/whl/cu118"),
]
for supported_code, url in available:
    if code >= supported_code:
        print(url)
        break
else:
    sys.exit(1)
PY
}

configure_gpu_runtime() {
  local gpu_name
  local driver_version
  local cuda_version

  gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
  driver_version="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1)"
  cuda_version="$(nvidia-smi | sed -n 's/.*CUDA Version: \([0-9.]\+\).*/\1/p' | head -n 1)"

  if [[ -z "${gpu_name}" || -z "${driver_version}" || -z "${cuda_version}" ]]; then
    log "[ERROR] Could not determine GPU, driver, or CUDA version from nvidia-smi."
    exit 1
  fi

  log "[INFO] GPU: ${gpu_name}"
  log "[INFO] NVIDIA driver: ${driver_version}"
  log "[INFO] CUDA reported by nvidia-smi: ${cuda_version}"

  if command -v nvcc >/dev/null 2>&1; then
    log "[INFO] nvcc detected: $(nvcc --version | tail -n 1)"
  else
    log "[INFO] nvcc not detected. That is acceptable for pip wheels; the host driver is what matters here."
  fi

  TORCH_INDEX_URL="$(select_torch_index "${cuda_version}")" || {
    log "[ERROR] No supported official PyTorch wheel mapping was found for CUDA ${cuda_version}."
    exit 1
  }
  export TORCH_INDEX_URL
  export TORCH_PACKAGES="torch torchvision torchaudio"
  export ONNXRUNTIME_PACKAGE="onnxruntime-gpu"
  export ONNXRUNTIME_EXTRA_INDEX_URL="https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/"

  log "[INFO] Selected PyTorch wheel index: ${TORCH_INDEX_URL}"
}

configure_network_binding() {
  local primary_ip
  primary_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  export COMFYUI_HOST="0.0.0.0"
  export WEBSITE_HOST="0.0.0.0"

  log "[INFO] Binding ComfyUI to ${COMFYUI_HOST}:3008"
  log "[INFO] Binding website to ${WEBSITE_HOST}:3010"
  if [[ -n "${primary_ip}" ]]; then
    log "[INFO] Access ComfyUI at: http://${primary_ip}:3008"
    log "[INFO] Access website at: http://${primary_ip}:3010"
  else
    log "[INFO] Access ComfyUI at: http://<vm-ip>:3008"
    log "[INFO] Access website at: http://<vm-ip>:3010"
  fi
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_ollama() {
  if have_cmd ollama; then
    log "[INFO] Ollama already installed."
    return
  fi

  log "[SETUP] Installing Ollama"
  curl -fsSL https://ollama.com/install.sh | sh
}

ensure_ollama_running() {
  if curl --max-time 5 -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    log "[INFO] Ollama API is already reachable."
    return
  fi

  if pgrep -x ollama >/dev/null 2>&1; then
    log "[WARN] Ollama process exists but API is not reachable. Restarting Ollama."
    pkill -f "llama-server" >/dev/null 2>&1 || true
    pkill -f "ollama serve" >/dev/null 2>&1 || true
    sleep 2
  fi

  log "[SETUP] Starting Ollama service"
  (
    cd /tmp
    nohup ollama serve >/tmp/ollama.log 2>&1 &
  )

  local attempt
  for attempt in $(seq 1 45); do
    if curl --max-time 5 -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      log "[INFO] Ollama API is ready."
      return
    fi
    sleep 1
  done

  log "[ERROR] Ollama did not become ready on http://127.0.0.1:11434."
  log "[ERROR] Inspect /tmp/ollama.log and rerun bootstrap_vm.sh."
  exit 1
}

pull_model_if_missing() {
  local model="$1"
  if ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    log "[INFO] Ollama model already present: $model"
    return
  fi

  log "[SETUP] Pulling Ollama model: $model"
  if [[ "$model" == hf.co/* || "$model" == huggingface.co/* ]]; then
    OLLAMA_NOHISTORY=1 ollama run "$model" ""
    return
  fi
  ollama pull "$model"
}

choose_reasoning_model() {
  if [[ "$OLLAMA_REASONING_MODEL_EXPLICIT" == "1" ]]; then
    printf '%s\n' "$OLLAMA_REASONING_MODEL"
    return
  fi

  if [[ ! -t 0 ]]; then
    printf '%s\n' "$OLLAMA_REASONING_MODEL"
    return
  fi

  echo "[INFO] Choose the Hermes reasoning model:" >&2
  echo "  1) gemma4:latest" >&2
  echo "  2) hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2:Q4_K_M" >&2
  echo "  3) gemma4:31b" >&2
  echo "  4) qwen3.6:27b" >&2
  echo "  5) qwen3.6:35b" >&2
  read -r -p "Enter 1, 2, 3, 4, or 5 [4]: " choice
  case "${choice:-4}" in
    1)
      printf '%s\n' "gemma4:latest"
      ;;
    2)
      printf '%s\n' "hf.co/Jiunsong/supergemma4-26b-uncensored-gguf-v2:Q4_K_M"
      ;;
    3)
      printf '%s\n' "gemma4:31b"
      ;;
    4)
      printf '%s\n' "qwen3.6:27b"
      ;;
    5)
      printf '%s\n' "qwen3.6:35b"
      ;;
    *)
      printf '%s\n' "qwen3.6:27b"
      ;;
  esac
}

choose_coder_model() {
  if [[ "$OLLAMA_CODER_MODEL_EXPLICIT" == "1" ]]; then
    printf '%s\n' "$OLLAMA_CODER_MODEL"
    return
  fi

  if [[ ! -t 0 ]]; then
    printf '%s\n' "$OLLAMA_CODER_MODEL"
    return
  fi

  echo "[INFO] Choose the Hermes coding model:" >&2
  echo "  1) qwen2.5-coder:14b" >&2
  echo "  2) qwen3-coder:30b" >&2
  read -r -p "Enter 1 or 2 [2]: " choice
  case "${choice:-2}" in
    1)
      printf '%s\n' "qwen2.5-coder:14b"
      ;;
    *)
      printf '%s\n' "qwen3-coder:30b"
      ;;
  esac
}

choose_vision_model() {
  if [[ "$OLLAMA_VISION_MODEL_EXPLICIT" == "1" ]]; then
    printf '%s\n' "$OLLAMA_VISION_MODEL"
    return
  fi

  if [[ ! -t 0 ]]; then
    printf '%s\n' "$OLLAMA_VISION_MODEL"
    return
  fi

  echo "[INFO] Choose the Hermes vision-language model:" >&2
  echo "  1) qwen2.5vl:7b" >&2
  echo "  2) qwen3-vl:30b" >&2
  read -r -p "Enter 1 or 2 [2]: " choice
  case "${choice:-2}" in
    1)
      printf '%s\n' "qwen2.5vl:7b"
      ;;
    *)
      printf '%s\n' "qwen3-vl:30b"
      ;;
  esac
}

write_hermes_local_override() {
  local reasoning_model="$1"
  local coder_model="$2"
  local vision_model="$3"
  mkdir -p "$(dirname "$LOCAL_HERMES_ENV")"
  cat >"$LOCAL_HERMES_ENV" <<EOF
OLLAMA_REASONING_MODEL="$reasoning_model"
OLLAMA_CODER_MODEL="$coder_model"
OLLAMA_VISION_MODEL="$vision_model"
HERMES_AGENT_MODEL="$reasoning_model"
HERMES_AGENT_CODER_MODEL="$coder_model"
HERMES_AGENT_BASE_URL="http://127.0.0.1:11434/v1"
HERMES_AGENT_VISION_MODEL="$vision_model"
EOF
}

prepare_ollama_runtime() {
  local reasoning_model
  local coder_model
  local vision_model

  install_ollama
  ensure_ollama_running
  coder_model="$(choose_coder_model)"
  OLLAMA_CODER_MODEL="$coder_model"
  export OLLAMA_CODER_MODEL
  pull_model_if_missing "$OLLAMA_CODER_MODEL"
  vision_model="$(choose_vision_model)"
  OLLAMA_VISION_MODEL="$vision_model"
  export OLLAMA_VISION_MODEL
  pull_model_if_missing "$OLLAMA_VISION_MODEL"
  reasoning_model="$(choose_reasoning_model)"
  OLLAMA_REASONING_MODEL="$reasoning_model"
  export OLLAMA_REASONING_MODEL
  pull_model_if_missing "$OLLAMA_REASONING_MODEL"
  write_hermes_local_override "$OLLAMA_REASONING_MODEL" "$OLLAMA_CODER_MODEL" "$OLLAMA_VISION_MODEL"
}

main() {
  configure_privilege_mode
  ensure_repo_scripts_executable
  ensure_base_packages
  ensure_node20
  detect_nvidia
  configure_gpu_runtime
  configure_network_binding
  prepare_ollama_runtime
  "$ROOT_DIR/setup_hermes_agent.sh"

  export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
  export OLLAMA_REASONING_MODEL
  export OLLAMA_CODER_MODEL
  export OLLAMA_VISION_MODEL

  cd "${ROOT_DIR}"
  exec "$ROOT_DIR/run_hermes_pipeline.sh"
}

main "$@"
