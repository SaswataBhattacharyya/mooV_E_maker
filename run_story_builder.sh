#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$ROOT_DIR")"
BACKEND_PORT="${STORY_BUILDER_BACKEND_PORT:-3010}"
FRONTEND_PORT="${STORY_BUILDER_FRONTEND_PORT:-8080}"
OLLAMA_BASE_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL%/}"
COMFYUI_BASE_URL="${COMFYUI_URL:-http://127.0.0.1:3008}"
COMFYUI_BASE_URL="${COMFYUI_BASE_URL%/}"
OLLAMA_BIND="${STORY_BUILDER_OLLAMA_BIND:-127.0.0.1:11434}"
SERVICE_WAIT_SECONDS="${STORY_BUILDER_SERVICE_WAIT_SECONDS:-90}"
COMFYUI_START_SCRIPT="${STORY_BUILDER_COMFYUI_START_SCRIPT:-/home/riki/web_dev/setup_comfy_and-stuff/opencode/hermes_agent/start_comfyui_local.sh}"
LOG_DIR="$ROOT_DIR/logs"
OLLAMA_LOG="$LOG_DIR/ollama.log"
LAUNCH_LOCK="$LOG_DIR/story-builder-launcher.lock"

http_ok() {
  local url="$1"
  curl --connect-timeout 2 --max-time 5 -fsS "$url" >/dev/null 2>&1
}

ensure_ollama() {
  local health_url="${OLLAMA_BASE_URL}/api/tags"
  local attempt

  if http_ok "$health_url"; then
    echo "[READY] Ollama already reachable at $OLLAMA_BASE_URL; leaving it running."
    return
  fi

  case "$OLLAMA_BASE_URL" in
    http://127.0.0.1|http://127.0.0.1:*|http://localhost|http://localhost:*|http://\[::1\]|http://\[::1\]:*) ;;
    *)
      echo "[ERROR] Ollama is unreachable at $OLLAMA_BASE_URL; refusing to start a local service for a non-loopback endpoint." >&2
      return 1
      ;;
  esac

  command -v ollama >/dev/null || { echo "[ERROR] Ollama is offline and the ollama command is not on PATH." >&2; return 1; }
  command -v curl >/dev/null || { echo "[ERROR] curl is required to health-check Ollama." >&2; return 1; }
  mkdir -p "$LOG_DIR"
  echo "[START] Ollama is offline; starting 'ollama serve' (log: $OLLAMA_LOG)."
  # Keep the local model service independent of the Story Builder terminal.
  # A later launcher invocation will health-check it and will not start a duplicate.
  nohup env OLLAMA_HOST="$OLLAMA_BIND" ollama serve >>"$OLLAMA_LOG" 2>&1 </dev/null &
  local ollama_pid=$!
  disown "$ollama_pid" 2>/dev/null || true

  for ((attempt = 1; attempt <= SERVICE_WAIT_SECONDS; attempt++)); do
    if http_ok "$health_url"; then
      echo "[READY] Ollama is reachable at $OLLAMA_BASE_URL."
      return
    fi
    sleep 1
  done

  kill "$ollama_pid" 2>/dev/null || true
  echo "[ERROR] Ollama did not become reachable at $health_url after ${SERVICE_WAIT_SECONDS}s. Recent log:" >&2
  tail -n 30 "$OLLAMA_LOG" >&2 || true
  return 1
}

warn_if_ollama_model_missing() {
  local expected_model="${OLLAMA_REASONING_MODEL:-${OPENCLAW_LLM_MODEL:-qwen3.6:35b}}"
  case "$OLLAMA_BASE_URL" in
    http://127.0.0.1|http://127.0.0.1:*|http://localhost|http://localhost:*|http://\[::1\]|http://\[::1\]:*) ;;
    *) return ;;
  esac
  if command -v ollama >/dev/null 2>&1 && ! OLLAMA_HOST="$OLLAMA_BIND" ollama list 2>/dev/null | awk 'NR > 1 { print $1 }' | grep -Fxq "$expected_model"; then
    echo "[WARN] Ollama is reachable, but '$expected_model' is not listed locally. Ollama-backed planning will fail until that model is available (for example: ollama pull $expected_model)." >&2
  fi
}

ensure_comfyui() {
  local health_url="${COMFYUI_BASE_URL}/system_stats"
  if http_ok "$health_url"; then
    echo "[READY] ComfyUI already reachable at $COMFYUI_BASE_URL; leaving it running."
    return
  fi
  [[ -f "$COMFYUI_START_SCRIPT" ]] || { echo "[ERROR] ComfyUI is offline and its start script was not found: $COMFYUI_START_SCRIPT" >&2; return 1; }
  command -v bash >/dev/null || { echo "[ERROR] bash is required to start ComfyUI." >&2; return 1; }
  echo "[START] ComfyUI is offline; invoking $COMFYUI_START_SCRIPT."
  bash "$COMFYUI_START_SCRIPT"
  http_ok "$health_url" || { echo "[ERROR] ComfyUI start script returned, but $health_url is still unreachable." >&2; return 1; }
  echo "[READY] ComfyUI is reachable at $COMFYUI_BASE_URL."
}

cleanup() {
  trap - EXIT INT TERM
  stop_service_group() {
    local pid="${1:-}"
    [[ -n "$pid" ]] || return 0
    # Isolated groups prevent npm/node grandchildren from outliving the launcher.
    kill -TERM -- "-$pid" 2>/dev/null || true
    for _ in {1..50}; do
      kill -0 -- "-$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL -- "-$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  }
  stop_service_group "${BACKEND_PID:-}"
  stop_service_group "${FRONTEND_PID:-}"
}
trap cleanup EXIT INT TERM

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required to check Ollama and ComfyUI" >&2; exit 1; }
command -v flock >/dev/null || { echo "flock is required to prevent duplicate Story Builder launches." >&2; exit 1; }
command -v setsid >/dev/null || { echo "setsid is required to isolate and clean up Story Builder service process groups." >&2; exit 1; }

mkdir -p "$LOG_DIR"
exec 9>"$LAUNCH_LOCK"
if ! flock -n 9; then
  echo "[ERROR] Story Builder is already starting or running from this checkout; refusing to launch duplicate backend/frontend processes." >&2
  exit 1
fi

if ! python3 -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "[ERROR] The selected python3 cannot import FastAPI and Uvicorn. Activate the Story Builder environment and retry." >&2
  exit 1
fi

check_port_free() {
  local port="$1"
  local label="$2"
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "[ERROR] Invalid ${label} port: '$port' (expected 1–65535)." >&2
    return 1
  fi
  if ! python3 -c 'import socket,sys; s=socket.socket(); s.bind(("0.0.0.0", int(sys.argv[1]))); s.close()' "$port" >/dev/null 2>&1; then
    echo "[ERROR] ${label} port ${port} is already in use. Inspect it with: ss -ltnp '( sport = :${port} )'" >&2
    return 1
  fi
}

check_port_free "$BACKEND_PORT" "backend"
check_port_free "$FRONTEND_PORT" "frontend"

echo "Checking required local services before starting Story Builder..."
ensure_ollama
warn_if_ollama_model_missing
ensure_comfyui

echo "Starting Story Builder backend on port ${BACKEND_PORT}..."
setsid bash -c '
  exec 9>&-
  cd "$1"
  exec python3 -m uvicorn story_builder.api.main:app --host 0.0.0.0 --port "$2"
' _ "$PARENT_DIR" "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Starting Story Builder frontend on port ${FRONTEND_PORT}..."
setsid bash -c '
  exec 9>&-
  cd "$1"
  export VITE_BACKEND_TARGET="http://127.0.0.1:$2"
  exec npm run dev -- --host 0.0.0.0 --port "$3" --strictPort
' _ "$ROOT_DIR/frontend/app" "$BACKEND_PORT" "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo "Story Builder is starting. Frontend: http://127.0.0.1:${FRONTEND_PORT} · Backend API: http://127.0.0.1:${BACKEND_PORT}"
echo "Press Ctrl+C once to stop both services."
wait -n "$BACKEND_PID" "$FRONTEND_PID"
exit $?
