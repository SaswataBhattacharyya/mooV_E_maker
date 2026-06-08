#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV_FILE="$ROOT_DIR/config/movie_builder.local.env"

echo "[SETUP] mooV-E Studio Setup Script"
echo "================================="

# ── Privilege handling ────────────────────────────────────────────
configure_privilege_mode() {
    if [ "$EUID" -eq 0 ]; then
        APT_CMD="apt-get"
        echo "[INFO] Running as root, using apt-get directly."
    elif command -v sudo &>/dev/null; then
        APT_CMD="sudo apt-get"
        echo "[INFO] Using sudo for apt-get."
    else
        echo "[ERROR] No root access and no sudo available. Aborting."
        exit 1
    fi
}

# ── Apt packages ───────────────────────────────────────────────────
apt_install_basics() {
    echo "[SETUP] Installing system packages..."
    $APT_CMD update -y >/dev/null 2>&1
    $APT_CMD install -y ca-certificates curl git gnupg lsof nano pciutils psmisc wget build-essential python3 python3-pip python3-venv ffmpeg >/dev/null 2>&1
    echo "[INFO] System packages installed."
}

# ── GPU detection (optional) ───────────────────────────────────────
detect_gpu_optional() {
    if command -v nvidia-smi &>/dev/null; then
        local gpu_name driver_ver cuda_ver
        gpu_name=$(nvidia-smi --query-gpu=gpu_name --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
        driver_ver=$(nvidia-smi --query-gpm=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
        cuda_ver=$(nvidia-smi --query-gpm=cuda_driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "Unknown")
        echo "[INFO] GPU detected: $gpu_name, Driver: $driver_ver, CUDA: $cuda_ver"
    elif lspci 2>/dev/null | grep -qi nvidia; then
        echo "[WARN] NVIDIA hardware detected but nvidia-smi unavailable. Continuing without GPU acceleration."
    else
        echo "[INFO] No NVIDIA GPU detected. Running in CPU mode (Ollama will auto-detect)."
    fi
}

# ── Ollama install/start/readiness ──────────────────────────────────
install_ollama() {
    if command -v ollama &>/dev/null; then
        echo "[INFO] Ollama already installed: $(ollama --version 2>/dev/null || echo 'unknown')"
    else
        echo "[SETUP] Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        echo "[INFO] Ollama installed."
    fi

    ensure_ollama_running
}

ensure_ollama_running() {
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[INFO] Ollama is already running."
        return
    fi

    # Check for existing processes
    local pids
    pids=$(pgrep -f 'ollama|llama-server' || true)
    if [ -n "$pids" ]; then
        echo "[WARN] Existing Ollama process(s) found but API not reachable. Restarting..."
        kill $(pgrep -f 'ollama|llama-server' 2>/dev/null || true) >/dev/null 2>&1 || true
        sleep 2
    fi

    echo "[SETUP] Starting Ollama..."
    nohup ollama serve >/tmp/movie_builder_ollama.log 2>&1 &

    local waited=0
    while [ $waited -lt 45 ]; do
        if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            echo "[INFO] Ollama is ready."
            return
        fi
        sleep 2
        waited=$((waited + 2))
    done

    # If still not running, check the log briefly and try once more
    if [ -f /tmp/movie_builder_ollama.log ]; then
        echo "[WARN] Ollama may have started. Checking log for errors..."
        head -5 /tmp/movie_builder_ollama.log || true
    fi

    # Final attempt: restart in foreground briefly
    kill $(pgrep -f 'ollama' 2>/dev/null || true) >/dev/null 2>&1 || true
    sleep 1
    nohup ollama serve >/tmp/movie_builder_ollama.log 2>&1 &

    waited=0
    while [ $waited -lt 15 ]; do
        if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
            echo "[INFO] Ollama is ready."
            return
        fi
        sleep 2
        waited=$((waited + 2))
    done

    echo "[ERROR] Ollama did not become ready on http://127.0.0.1:11434"
    echo "[ERROR] Check /tmp/movie_builder_ollama.log and try again."
}

# ── Interactive model selection ────────────────────────────────────
interactive_model_selection() {
    # Story model
    if [ -n "${OLLAMA_STORY_MODEL:-}" ]; then
        STORY_MODEL="$OLLAMA_STORY_MODEL"
        echo "[INFO] OLLAMA_STORY_MODEL already set: $STORY_MODEL"
    elif [ -t 0 ]; then
        echo ""
        echo "Choose story/reasoning model:"
        echo "  1) qwen3.6:27b"
        echo "  2) qwen3.6:35b (default)"
        echo "  3) qwen3:32b"
        echo "  4) llama3.1:8b"
        echo "  5) custom model name"
        read -r "story_opt" <<< "2"
        
        case "$story_opt" in
            1) STORY_MODEL="qwen3.6:27b" ;;
            2) STORY_MODEL="qwen3.6:35b" ;;
            3) STORY_MODEL="qwen3:32b" ;;
            4) STORY_MODEL="llama3.1:8b" ;;
            5) read -rp "Enter Ollama story model name: " STORY_MODEL ;;
            *) STORY_MODEL="qwen3.6:35b" ;;
        esac
        
        [ -z "$STORY_MODEL" ] && STORY_MODEL="qwen3.6:35b"
    else
        STORY_MODEL="qwen3.6:35b"
        echo "[INFO] Non-interactive mode, using default story model: $STORY_MODEL"
    fi

    # Coder model
    if [ -n "${OLLAMA_CODER_MODEL:-}" ]; then
        CODER_MODEL="$OLLAMA_CODER_MODEL"
        echo "[INFO] OLLAMA_CODER_MODEL already set: $CODER_MODEL"
    elif [ -t 0 ]; then
        echo ""
        echo "Choose coder model:"
        echo "  1) qwen3-coder:30b (default)"
        echo "  2) qwen2.5-coder:14b"
        echo "  3) skip coder model"
        echo "  4) custom model name"
        read -r "coder_opt" <<< "1"
        
        case "$coder_opt" in
            1) CODER_MODEL="qwen3-coder:30b" ;;
            2) CODER_MODEL="qwen2.5-coder:14b" ;;
            3) CODER_MODEL="" ;;
            4) read -rp "Enter Ollama coder model name: " CODER_MODEL ;;
            *) CODER_MODEL="qwen3-coder:30b" ;;
        esac
        
    else
        CODER_MODEL="qwen3-coder:30b"
        echo "[INFO] Non-interactive mode, using default coder model: $CODER_MODEL"
    fi

    # Pull models if missing
    echo ""
    for model in "$STORY_MODEL" "$CODER_MODEL"; do
        if [ -z "$model" ]; then continue; fi
        
        local found=false
        while IFS= read -r line; do
            if echo "$line" | grep -q "$model"; then
                found=true
                break
            fi
        done < <(ollama list 2>/dev/null || true)

        if [ "$found" = false ]; then
            echo "[SETUP] Pulling $model..."
            if [[ "$model" == hf.co/* ]] || [[ "$model" == huggingface.co/* ]]; then
                OLLAMA_NOHISTORY=1 ollama run "$model" "" >/dev/null 2>&1 &
            else
                ollama pull "$model" >/dev/null 2>&1 &
            fi
        else
            echo "[INFO] Model $model already present. Skipping."
        fi
    done

    # Wait for pulls to complete if running in background
    if [ -n "${STORY_MODEL:-}" ]; then sleep 3; fi
}

# ── Port-in-use handling ───────────────────────────────────────────
port_in_use() {
    local port=$1
    lsof -ti :"$port" >/dev/null 2>&1 || fuser "$port/tcp" >/dev/null 2>&1
}

kill_port() {
    local port=$1
    if command -v lsof &>/dev/null; then
        kill $(lsof -ti :$port) >/dev/null 2>&1 || true
    elif command -v fuser &>/dev/null; then
        fuser -k "$port/tcp" >/dev/null 2>&1 || true
    fi
}

choose_streamlit_port() {
    if [ -n "${MOVIE_BUILDER_PORT:-}" ]; then
        PORT="$MOVIE_BUILDER_PORT"
    elif [ -t 0 ]; then
        read -rp "Enter Streamlit port [8501]: " PORT
    else
        PORT="8501"
    fi

    PORT="${PORT:-8501}"

    # Validate port range
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
        echo "[ERROR] Invalid port $PORT. Must be 1024-65535."
        exit 1
    fi

    if port_in_use "$PORT"; then
        echo "[WARN] Port $PORT is already in use."
        if [ -t 0 ]; then
            read -rp "  1) Kill existing process and continue"
            kill_port "$PORT"
            sleep 1
        fi
    fi

    echo "$PORT"
}

# ── Write env config ───────────────────────────────────────────────
write_env_config() {
    mkdir -p "$ROOT_DIR/config"
    
    cat > "$LOCAL_ENV_FILE" <<EOF
OLLAMA_HOST="http://127.0.0.1:11434"
OLLAMA_STORY_MODEL="$STORY_MODEL"
OLLAMA_CODER_MODEL="$CODER_MODEL"
MOVIE_BUILDER_HOST="0.0.0.0"
MOVIE_BUILDER_PORT="$PORT"
EOF

    echo "[INFO] Config written to $LOCAL_ENV_FILE"
}

# ── Python environment ────────────────────────────────────────────
setup_python_env() {
    # Ensure requirements.txt exists
    if [ ! -f "$ROOT_DIR/requirements.txt" ]; then
        cat > "$ROOT_DIR/requirements.txt" <<EOF
streamlit
ollama
pydantic
jsonschema
python-dotenv
EOF
        echo "[INFO] Created requirements.txt with defaults."
    fi

    # Python env mode
    if [ -t 0 ]; then
        read -rp "Choose Python environment mode: 1) venv (recommended), 2) conda [1]: " py_mode <<< "1"
    else
        py_mode="1"
    fi

    PY_MODE="${py_mode:-1}"

    if [ "$PY_MODE" = "1" ]; then
        # venv mode
        if [ ! -x "$ROOT_DIR/venv/bin/python" ]; then
            echo "[SETUP] Creating Python virtual environment..."
            python3 -m venv "$ROOT_DIR/venv" >/dev/null 2>&1
        fi
        
        echo "[SETUP] Installing Python requirements..."
        "$ROOT_DIR/venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
        "$ROOT_DIR/venv/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt" >/dev/null 2>&1
        echo "[INFO] venv ready."

        # Store env mode for run script
        echo "venv" > "$ROOT_DIR/.movie_builder_env_mode"

    elif [ "$PY_MODE" = "2" ]; then
        if command -v conda &>/dev/null; then
            conda create -y -n movie_builder python=3.11 >/dev/null 2>&1 || true
            echo "[SETUP] Installing Python requirements in conda..."
            conda run -n movie_builder python -m pip install --upgrade pip >/dev/null 2>&1
            conda run -n movie_builder python -m pip install -r "$ROOT_DIR/requirements.txt" >/dev/null 2>&1
            echo "conda" > "$ROOT_DIR/.movie_builder_env_mode"
        else
            if [ -t 0 ]; then
                read -rp "Conda not installed. Fall back to venv? [Y/n]: " y <<< "y"
            fi
            [ "${y:-n}" != "n" ] && PY_MODE="1"
        fi
    else
        py_mode="1"
        PY_MODE=1
        if [ ! -x "$ROOT_DIR/venv/bin/python" ]; then
            python3 -m venv "$ROOT_DIR/venv" >/dev/null 2>&1
        fi
        "$ROOT_DIR/venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
        "$ROOT_DIR/venv/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt" >/dev/null 2>&1
        echo "venv" > "$ROOT_DIR/.movie_builder_env_mode"
    fi
}

# ── Create run_movie_builder.sh ────────────────────────────────────
create_run_script() {
    cat > "$ROOT_DIR/run_movie_builder.sh" <<'RUNEOF'
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
RUNEOF
    chmod +x "$ROOT_DIR/run_movie_builder.sh"
}

# ── Main Setup Flow ───────────────────────────────────────────────
main() {
    configure_privilege_mode
    apt_install_basics
    detect_gpu_optional
    install_ollama
    interactive_model_selection
    ensure_project_dirs_setup
    setup_python_env
    
    PORT=$(choose_streamlit_port)
    write_env_config
    create_run_script

    echo ""
    echo "[READY] Setup complete! Movie Builder is ready on port $PORT"
    echo "[INFO] Next time, just run: bash $ROOT_DIR/run_movie_builder.sh"
    echo ""
}

ensure_project_dirs_setup() {
    mkdir -p "$ROOT_DIR/project_state"/{intake,story,characters,world,structure,units/{movie,comic,book,anime},review,exports,project_state/exports}
}

main "$@"
