# PROMPT_02_SETUP_SCRIPT.md

## Goal

Create a one-step setup and run script for the Streamlit + Ollama `movie_builder` project.

The script should be:

```text
setup_and_run.sh
```

It should perform setup and launch the Streamlit app in one command:

```bash
bash setup_and_run.sh
```

Also create a smaller runtime script:

```text
run_movie_builder.sh
```

## Important reference policy

If reference scripts are provided, use them only for patterns.

Allowed to reuse/adapt:

- sudo/root handling
- apt install pattern
- Ollama install/start/readiness checks
- model selection menus
- missing-model pulling
- env-file writing/loading
- port check and process killing

Do not copy:

- Hermes setup
- Hermes memory sync
- ComfyUI install
- ComfyUI model downloads
- custom-node install
- Node/React frontend setup
- website server
- agent console
- mandatory NVIDIA GPU failure logic

This project must not fail just because no NVIDIA GPU is present.

## Required files to create

```text
setup_and_run.sh
run_movie_builder.sh
requirements.txt
config/movie_builder.local.env
```

`setup_and_run.sh` should create `run_movie_builder.sh` if missing.

Make both scripts executable.

## Script standards

Use:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

Use clear log prefixes:

```text
[INFO]
[SETUP]
[WARN]
[ERROR]
[READY]
```

## Project root detection

Use:

```bash
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV_FILE="$ROOT_DIR/config/movie_builder.local.env"
```

## Privilege handling

Implement:

```bash
configure_privilege_mode()
apt_get()
as_root()
```

Behavior:

- If `EUID == 0`, use `apt-get` directly.
- Else if `sudo` exists, use `sudo apt-get`.
- Else print a clear error and exit.

## Apt packages

Install only packages needed by this project:

```text
ca-certificates
curl
git
gnupg
lsof
nano
pciutils
psmisc
wget
build-essential
python3
python3-pip
python3-venv
ffmpeg
```

Do not install Node.js.

Do not install ComfyUI dependencies.

Do not install CUDA or NVIDIA drivers.

Do not install Tesseract.

## GPU handling

Implement optional GPU detection:

```bash
detect_gpu_optional()
```

Behavior:

- If `nvidia-smi` exists:
  - print GPU name
  - print NVIDIA driver version
  - print CUDA version reported by nvidia-smi
  - continue
- Else if `lspci` shows NVIDIA:
  - print warning: NVIDIA hardware detected but `nvidia-smi` is unavailable
  - continue
- Else:
  - print: no NVIDIA GPU detected; continuing in CPU mode
  - continue

Do not exit because of missing GPU.

Do not install GPU drivers.

Do not install PyTorch GPU wheels.

Ollama should manage GPU usage automatically if the host has a working driver.

## Ollama install

Implement:

```bash
have_cmd()
install_ollama()
ensure_ollama_running()
pull_model_if_missing()
```

`install_ollama()`:

- If `ollama` exists, print `[INFO] Ollama already installed.`
- Otherwise run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

`ensure_ollama_running()`:

- Check:

```text
http://127.0.0.1:11434/api/tags
```

- If reachable, continue.
- If an `ollama` process exists but API is not reachable, restart:
  - kill `llama-server`
  - kill `ollama serve`
  - wait 2 seconds
- Start:

```bash
nohup ollama serve >/tmp/movie_builder_ollama.log 2>&1 &
```

- Wait up to 45 seconds.
- If still not reachable, print:

```text
[ERROR] Ollama did not become ready on http://127.0.0.1:11434.
[ERROR] Inspect /tmp/movie_builder_ollama.log and rerun setup_and_run.sh.
```

## Interactive model selection

The app needs two model roles:

1. story/reasoning model
2. optional coder model

Environment override behavior:

- If `OLLAMA_STORY_MODEL` is already set, do not prompt for story model.
- If `OLLAMA_CODER_MODEL` is already set, do not prompt for coder model.
- If shell is non-interactive, use defaults.

Defaults:

```bash
OLLAMA_STORY_MODEL_DEFAULT="qwen3.6:35b"
OLLAMA_CODER_MODEL_DEFAULT="qwen3-coder:30b"
```

### Story model menu

Prompt:

```text
Choose story/reasoning model:
1) qwen3.6:27b
2) qwen3.6:35b
3) qwen3:32b
4) llama3.1:8b
5) custom model name
Enter 1, 2, 3, 4, or 5 [2]:
```

Default: option 2.

If custom, ask:

```text
Enter Ollama story model name:
```

### Coder model menu

Prompt:

```text
Choose coder model:
1) qwen3-coder:30b
2) qwen2.5-coder:14b
3) skip coder model
4) custom model name
Enter 1, 2, 3, or 4 [1]:
```

Default: option 1.

If skip, set coder model to empty string.

If custom, ask:

```text
Enter Ollama coder model name:
```

## Pull selected models

For each non-empty selected model:

- Check `ollama list`.
- If already present, skip.
- If missing and model starts with `hf.co/` or `huggingface.co/`, run:

```bash
OLLAMA_NOHISTORY=1 ollama run "$model" ""
```

- Otherwise run:

```bash
ollama pull "$model"
```

## Python environment mode

Ask:

```text
Choose Python environment mode:
1) venv, recommended
2) conda, if already installed
Enter 1 or 2 [1]:
```

Default: venv.

If non-interactive, use venv.

### venv mode

- Create venv at:

```text
venv/
```

Only create if `venv/bin/python` does not exist.

Run:

```bash
"$ROOT_DIR/venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/venv/bin/python" -m pip install -r "$ROOT_DIR/requirements.txt"
```

### conda mode

- If `conda` exists:
  - create env if missing:

```bash
conda create -y -n movie_builder python=3.11
```

  - install requirements:

```bash
conda run -n movie_builder python -m pip install --upgrade pip
conda run -n movie_builder python -m pip install -r "$ROOT_DIR/requirements.txt"
```

- If `conda` is missing:
  - ask:

```text
Conda is not installed. Continue with venv instead? [Y/n]
```

  - if yes/default, use venv.
  - if no, exit.

Do not auto-install Anaconda or Miniconda unless a future `INSTALL_CONDA=1` flag is explicitly added.

## requirements.txt

If `requirements.txt` is missing, create it with:

```text
streamlit
ollama
pydantic
jsonschema
python-dotenv
```

If it exists, do not overwrite it.

Always run pip install from it because dependencies may have changed.

## Streamlit port prompt

Ask:

```text
Enter Streamlit port [8501]:
```

Default: 8501.

Validate:

- numeric
- between 1024 and 65535

If non-interactive, use:

- `MOVIE_BUILDER_PORT` if set
- otherwise 8501

## Port-in-use behavior

Implement:

```bash
port_in_use()
kill_port()
choose_streamlit_port()
```

If selected port is in use, show:

```text
Port <port> is already in use.
1) Kill existing process and continue
2) Choose another port
3) Exit
```

If kill:

- use `lsof -ti :$PORT` if available
- send SIGTERM
- wait 1 second
- if process still alive, send SIGKILL

If lsof is unavailable, use `fuser` if available.

## Write local env config

Create folder:

```bash
mkdir -p "$ROOT_DIR/config"
```

Write:

```bash
OLLAMA_HOST="http://127.0.0.1:11434"
OLLAMA_STORY_MODEL="<selected_story_model>"
OLLAMA_CODER_MODEL="<selected_coder_model_or_empty>"
MOVIE_BUILDER_HOST="0.0.0.0"
MOVIE_BUILDER_PORT="<selected_port>"
MOVIE_BUILDER_ENV_MODE="<venv_or_conda>"
```

Do not silently overwrite unrelated config files.

It is okay to overwrite `config/movie_builder.local.env` because it is this project's generated local override.

## Start Streamlit

Load env file:

```bash
set -a
source "$LOCAL_ENV_FILE"
set +a
```

Print access URLs:

```text
Local:
http://127.0.0.1:<port>

Network:
http://<primary_vm_ip>:<port>
```

Get primary VM IP:

```bash
hostname -I 2>/dev/null | awk '{print $1}'
```

Then launch.

### venv launch

```bash
"$ROOT_DIR/venv/bin/python" -m streamlit run "$ROOT_DIR/app.py" \
  --server.address "$MOVIE_BUILDER_HOST" \
  --server.port "$MOVIE_BUILDER_PORT"
```

### conda launch

```bash
conda run -n movie_builder python -m streamlit run "$ROOT_DIR/app.py" \
  --server.address "$MOVIE_BUILDER_HOST" \
  --server.port "$MOVIE_BUILDER_PORT"
```

## `run_movie_builder.sh`

Create a runtime-only script.

It should:

1. detect root
2. load `config/movie_builder.local.env` if present
3. set defaults if missing
4. start Ollama if needed
5. prompt for port only if `MOVIE_BUILDER_PORT` is missing
6. check/handle port-in-use
7. use existing venv if `venv/bin/python` exists
8. otherwise use conda env if `MOVIE_BUILDER_ENV_MODE=conda`
9. otherwise fall back to `python3` with warning
10. run Streamlit

It should not install apt packages or pull models unless needed.

## Idempotency

The scripts must be safe to rerun:

- Do not recreate venv if it exists.
- Do not reinstall Ollama if installed.
- Do not repull models already present.
- Do not overwrite `requirements.txt` if it exists.
- Do update `config/movie_builder.local.env` when user selects a different port/model.
- Do run pip install each time to catch changed requirements.

## Final setup flow

The full setup should follow:

```text
configure privileges
↓
install apt basics
↓
optional GPU check
↓
install/start Ollama
↓
choose models
↓
pull missing models
↓
ensure requirements.txt
↓
choose venv/conda
↓
install Python requirements
↓
choose Streamlit port
↓
handle port conflict
↓
write config/movie_builder.local.env
↓
create run_movie_builder.sh
↓
launch Streamlit
```

## Final output before launch

Print:

```text
[READY] Movie Builder is starting on port <port>
```

Then run Streamlit.
