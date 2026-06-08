#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV_FILE="$ROOT_DIR/config/movie_builder.local.env"

# Load env config if present
if [ -f "$LOCAL_ENV_FILE" ]; then
    set -a
    source "$LOCAL_ENV_FILE"
    set +a
    echo "[INFO] Loaded config from $LOCAL_ENV_FILE"
else
    OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
    MOVIE_BUILDER_HOST="${MOVIE_BUILDER_HOST:-0.0.0.0}"
    MOVIE_BUILDER_PORT="${MOVIE_BUILDER_PORT:-8501}"
fi

# Determine Python interpreter
VENV_PY="$ROOT_DIR/venv/bin/python"
if [ -x "$VENV_PY" ]; then
    PYTHON="$VENV_PY"
elif command -v conda &>/dev/null; then
    PYTHON="conda run -n movie_builder python"
else
    echo "[WARN] No venv or conda found. Using system python3."
    PYTHON="python3"
fi

# Ensure Ollama is running
if ! curl -sf "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "[INFO] Starting Ollama..."
    nohup ollama serve >/tmp/movie_builder_ollama.log 2>&1 &
    sleep 5
fi

# Get access URLs
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo "[READY] Movie Builder is starting on port ${MOVIE_BUILDER_PORT}"
echo ""
echo "Local:      http://127.0.0.1:${MOVIE_BUILDER_PORT}"
echo "Network:    http://${LOCAL_IP}:${MOVIE_BUILDER_PORT}"
echo ""

# Start Streamlit
$PYTHON -m streamlit run "$ROOT_DIR/app.py" \
    --server.address "$MOVIE_BUILDER_HOST" \
    --server.port "$MOVIE_BUILDER_PORT"
