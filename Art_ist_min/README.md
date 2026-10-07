# Agentic Art Bare Minimum

Minimal local stack for an agent-assisted art generation workflow:

- `main.py` boots the Python environment, optional ComfyUI checkout, the FastAPI backend, and the Vite frontend build flow.
- `api_server/` serves the website API and static frontend assets.
- `ai-art-generator-hub/` contains the React UI for prompt entry, asset upload, and agent status monitoring.

## What works today

- Prompt and media upload UI
- Payload assembly and preview in the browser
- FastAPI endpoints for uploads, health, status, and placeholder agent state
- Local launcher for wiring the pieces together

## Current limitation

The backend is still in placeholder mode for generation jobs. The site accepts inputs and stores uploaded assets, but it does not yet submit real workflows to ComfyUI.

## Local run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cd ai-art-generator-hub && npm install
cd ..
python main.py
```

Important environment variables:

- `COMFYUI_PATH`
- `COMFYUI_PORT`
- `WEBSITE_PORT`
- `START_COMFYUI`
- `START_WEBSITE`
