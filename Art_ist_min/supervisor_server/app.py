"""Separate supervisor wrapper UI on port 3009 for OpenClaw-style diagnostics."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api_server.services.native_openclaw_client import gateway_summary as native_openclaw_gateway_summary
from api_server.services.openclaw_supervisor import (
    SupervisorError,
    generate_supervisor_text,
)
from api_server.services.openclaw_projects import ProjectStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = PROJECT_ROOT / "assets" / "projects"
PROJECT_STORE = ProjectStore(PROJECTS_DIR)
OPENCLAW_DOCS = [
    PROJECT_ROOT / "openclaw" / "DUTY.md",
    PROJECT_ROOT / "openclaw" / "KNOWLEDGE.md",
    PROJECT_ROOT / "openclaw" / "PIPELINE.md",
    PROJECT_ROOT / "openclaw" / "SOUL.md",
    PROJECT_ROOT / "openclaw" / "STYLE.md",
    PROJECT_ROOT / "openclaw" / "RUNTIME.md",
]
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

app = FastAPI(title="OpenClaw Supervisor Wrapper")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SupervisorChatRequest(BaseModel):
    project_id: str | None = None
    message: str


class SupervisorOperatorRequest(BaseModel):
    project_id: str
    message: str


def _service_reachable(url: str) -> bool:
    try:
        with urlopen(url, timeout=3):
            return True
    except URLError:
        return False


def _read_docs() -> str:
    blocks = []
    for path in OPENCLAW_DOCS:
        if path.exists():
            blocks.append(f"# {path.name}\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(blocks)


def _project_context(project_id: str | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    try:
        return PROJECT_STORE.read_project(project_id)
    except FileNotFoundError:
        return None


def _resolve_active_project() -> dict[str, Any] | None:
    projects = PROJECT_STORE.list_projects()
    if not projects:
        return None

    def project_rank(project: dict[str, Any]) -> tuple[int, str]:
        runtime = project.get("runtime", {})
        supervisor = runtime.get("supervisor", {})
        active = bool(runtime.get("automation_active"))
        waiting = bool(supervisor.get("waiting_for_user"))
        state = str(runtime.get("state", ""))
        priority = 0
        if active:
            priority = 4
        elif waiting:
            priority = 3
        elif state in {"RUNNING", "FAILED", "PAUSED"}:
            priority = 2
        elif project.get("status") in {"automating", "failed", "paused"}:
            priority = 1
        return (priority, str(project.get("updated_at", "")))

    projects.sort(key=project_rank, reverse=True)
    top = projects[0]
    if project_rank(top)[0] == 0:
        return None
    return top


def _artifact_summary(project: dict[str, Any] | None) -> dict[str, Any]:
    if not project:
        return {}
    summary: dict[str, Any] = {}
    for name, artifact in project.get("artifacts", {}).items():
        content = artifact.get("content")
        if isinstance(content, dict):
            summary[name] = {
                "status": artifact.get("status"),
                "keys": list(content.keys())[:12],
            }
        else:
            summary[name] = {"status": artifact.get("status"), "keys": []}
    return summary


def _supervisor_summary(project: dict[str, Any] | None) -> dict[str, Any]:
    if not project:
        return {}
    supervisor = project.get("runtime", {}).get("supervisor", {})
    return {
        "mode": supervisor.get("mode"),
        "waiting_for_user": supervisor.get("waiting_for_user"),
        "current_review": supervisor.get("current_review"),
        "last_decision": supervisor.get("last_decision"),
        "last_rationale": supervisor.get("last_rationale"),
        "actionable_diagnosis": supervisor.get("actionable_diagnosis"),
        "stage_retry_counts": supervisor.get("stage_retry_counts", {}),
        "image_retry_counts": supervisor.get("image_retry_counts", {}),
        "events": supervisor.get("events", [])[-60:],
    }


def _build_supervisor_prompt(message: str, project: dict[str, Any] | None) -> str:
    docs = _read_docs()
    context = {
        "project": {
            "id": project.get("id") if project else None,
            "title": project.get("title") if project else None,
            "status": project.get("status") if project else None,
            "current_stage": project.get("current_stage") if project else None,
            "runtime": project.get("runtime") if project else None,
            "context_layers": project.get("context_layers") if project else None,
        }
        if project
        else None,
        "artifacts": _artifact_summary(project),
        "recent_logs": (project.get("logs", [])[-12:] if project else []),
        "dependencies": {
            "ollama": _service_reachable(f"{OLLAMA_HOST}/api/tags"),
            "comfyui": _service_reachable("http://127.0.0.1:3008/system_stats"),
            "website_backend": _service_reachable("http://127.0.0.1:3010/api/health"),
        },
        "supervisor": _supervisor_summary(project),
    }
    return f"""
You are the OpenClaw supervisor for this repo.
Use the repo instructions below to supervise the project.
Be concise, practical, and diagnostic.
Do not claim to have changed anything unless the app explicitly supports that action.
Prefer: issue identification, likely cause, smallest safe next step.

Repo supervision instructions:
{docs}

Current project context:
{json.dumps(context, indent=2, ensure_ascii=True)}

User message:
{message}
""".strip()


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ui_port": int(os.environ.get("OPENCLAW_UI_PORT", "3009")),
        "ollama": _service_reachable(f"{OLLAMA_HOST}/api/tags"),
        "website_backend": _service_reachable("http://127.0.0.1:3010/api/health"),
        "comfyui": _service_reachable("http://127.0.0.1:3008/system_stats"),
    }


@app.get("/api/supervisor/status")
async def supervisor_status(project_id: str | None = None) -> dict[str, Any]:
    project = _project_context(project_id) if project_id else _resolve_active_project()
    return {
        "resolved_project_id": project.get("id") if project else None,
        "project": {
            "id": project.get("id") if project else None,
            "title": project.get("title") if project else None,
            "status": project.get("status") if project else None,
            "current_stage": project.get("current_stage") if project else None,
            "runtime": project.get("runtime") if project else None,
        }
        if project
        else None,
        "dependencies": {
            "ollama": _service_reachable(f"{OLLAMA_HOST}/api/tags"),
            "comfyui": _service_reachable("http://127.0.0.1:3008/system_stats"),
            "website_backend": _service_reachable("http://127.0.0.1:3010/api/health"),
        },
        "supervisor": _supervisor_summary(project),
        "logs": project.get("logs", [])[-40:] if project else [],
        "artifacts": _artifact_summary(project),
        "openclaw_gateway": native_openclaw_gateway_summary(),
        "models": {
            "reasoning": os.environ.get("OLLAMA_REASONING_MODEL", "gemma4:latest"),
            "coder": os.environ.get("OLLAMA_CODER_MODEL", "qwen2.5-coder:14b"),
            "vision": os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
        },
        "support_repos": {
            "graphify": (PROJECT_ROOT / "openclaw" / "support" / "graphify").exists(),
            "ruflo": (PROJECT_ROOT / "openclaw" / "support" / "ruflo").exists(),
        },
    }


@app.post("/api/supervisor/chat")
async def supervisor_chat(payload: SupervisorChatRequest) -> dict[str, Any]:
    project = _project_context(payload.project_id)
    prompt = _build_supervisor_prompt(payload.message, project)
    try:
        reply = generate_supervisor_text(prompt=prompt, project=project, temperature=0.2)
    except SupervisorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"reply": reply}


@app.post("/api/supervisor/operator-note")
async def supervisor_operator_note(payload: SupervisorOperatorRequest) -> dict[str, Any]:
    if not payload.project_id.strip():
        raise HTTPException(status_code=400, detail="Project ID is required")
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    try:
        PROJECT_STORE.add_supervisor_event(
            payload.project_id.strip(),
            kind="operator_note",
            level="info",
            message=payload.message.strip(),
            details={"source": "operator"},
        )
        PROJECT_STORE.add_log(payload.project_id.strip(), "info", f"Operator note: {payload.message.strip()}")
        return {"status": "ok"}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/", response_class=HTMLResponse)
async def index(project_id: str | None = None) -> str:
    safe_project_id = html.escape(project_id or "")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpenClaw Supervisor Wrapper</title>
  <style>
    body {{ background:#0b0d12; color:#e6e7eb; font-family:system-ui,sans-serif; margin:0; }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
    .grid {{ display:grid; grid-template-columns:1.25fr .75fr; gap:20px; }}
    .card {{ background:#141821; border:1px solid #2a3040; border-radius:18px; padding:18px; }}
    .muted {{ color:#8f9ab0; }}
    .pill {{ display:inline-block; padding:6px 10px; border-radius:999px; background:#202636; margin-right:8px; }}
    textarea, input {{ width:100%; background:#0f1320; color:#e6e7eb; border:1px solid #32394c; border-radius:12px; padding:12px; }}
    button {{ background:#1e66ff; color:white; border:none; border-radius:12px; padding:10px 14px; cursor:pointer; }}
    .log {{ border:1px solid #272d3d; border-radius:12px; padding:10px; margin-top:10px; }}
    .chat {{ min-height:320px; white-space:pre-wrap; }}
    .feed {{ min-height:320px; max-height:540px; overflow:auto; }}
    .row {{ display:flex; gap:12px; align-items:center; }}
    .split {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="row" style="justify-content:space-between;">
      <div>
        <div class="muted">OpenClaw Supervisor Wrapper</div>
        <h1 style="margin:6px 0 0;">Diagnostics and Commentary</h1>
      </div>
      <a id="mainWebsiteLink" href="/" style="color:#9ec1ff;">Main Website</a>
    </div>
    <div class="grid" style="margin-top:20px;">
      <div class="card">
        <h2 style="margin-top:0;">Ripa Feed</h2>
        <div class="muted">Live supervision feed, operator notes, and direct questions for Ripa.</div>
        <div style="margin-top:12px;">
          <label class="muted">Project ID</label>
          <input id="projectId" value="{safe_project_id}" />
        </div>
        <div class="split" style="margin-top:16px;">
          <div>
            <h3 style="margin:0 0 8px;">Live Feed</h3>
            <div id="feed" class="card feed">Waiting for project status...</div>
          </div>
          <div>
            <h3 style="margin:0 0 8px;">Ask Ripa</h3>
            <label class="muted">Message</label>
            <textarea id="message" rows="5" placeholder="Why is story generation stuck? What should I do next?"></textarea>
            <div style="margin-top:12px;" class="row">
              <button id="sendBtn">Ask Ripa</button>
              <button id="logBtn" style="background:#2f3a52;">Log Operator Note</button>
            </div>
            <div id="chat" class="card chat" style="margin-top:16px;">Ripa ready.</div>
          </div>
        </div>
      </div>
      <div class="card">
        <h2 style="margin-top:0;">Live Supervision</h2>
        <div id="statusBlock" class="muted">Loading...</div>
        <div id="logs"></div>
      </div>
    </div>
  </div>
  <script>
    async function refreshStatus() {{
      const projectId = document.getElementById('projectId').value.trim();
      const res = await fetch('/api/supervisor/status' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
      const data = await res.json();
      const project = data.project || {{}};
      const supervisor = data.supervisor || {{}};
      const gateway = data.openclaw_gateway || {{}};
      const diagnosis = supervisor.actionable_diagnosis;
      if (!document.getElementById('projectId').value.trim() && data.resolved_project_id) {{
        document.getElementById('projectId').value = data.resolved_project_id;
      }}
      const dependencySummary = !data.dependencies.ollama
        ? 'Ollama is offline on 127.0.0.1:11434 inside the VM.'
        : !data.dependencies.website_backend
          ? 'The website backend is offline on 127.0.0.1:3010 inside the VM.'
          : !data.dependencies.comfyui
            ? 'ComfyUI is offline on 127.0.0.1:3008 inside the VM.'
            : 'Wrapper and dependencies are reachable inside the VM.';
      document.getElementById('statusBlock').innerHTML = `
        <div class="pill">Ollama: ${{data.dependencies.ollama ? 'Online' : 'Offline'}}</div>
        <div class="pill">ComfyUI: ${{data.dependencies.comfyui ? 'Online' : 'Offline'}}</div>
        <div class="pill">Website: ${{data.dependencies.website_backend ? 'Online' : 'Offline'}}</div>
        <div class="pill">Ripa: ${{supervisor.mode || 'idle'}}</div>
        <p><strong>Diagnosis:</strong> ${{dependencySummary}}</p>
        <p><strong>Project:</strong> ${{project.title || 'None'}}<br/>
        <strong>OpenClaw Gateway:</strong> ${{gateway.url || 'Unavailable'}}<br/>
        <strong>Stage:</strong> ${{project.current_stage || 'N/A'}}<br/>
        <strong>Runtime:</strong> ${{project.runtime ? project.runtime.state : 'IDLE'}}<br/>
        <strong>Task:</strong> ${{project.runtime ? project.runtime.current_task : 'No active task'}}<br/>
        <strong>Review:</strong> ${{supervisor.current_review || 'N/A'}}<br/>
        <strong>Waiting For You:</strong> ${{supervisor.waiting_for_user ? 'Yes' : 'No'}}</p>
        ${{diagnosis ? `<div class="log"><strong>Actionable Diagnosis</strong><br/>Layer: ${{diagnosis.layer}}<br/>Stage: ${{diagnosis.stage}}<br/>Reason: ${{diagnosis.reason}}<br/>Next: ${{diagnosis.next_action}}</div>` : ''}}
      `;
      const logs = (data.logs || []).slice().reverse().map(log => `<div class="log"><strong>${{log.level}}</strong><br/>${{log.message}}</div>`).join('');
      document.getElementById('logs').innerHTML = logs || '<div class="muted">No logs yet.</div>';
      const feed = (supervisor.events || []).slice().reverse().map(event => `
        <div class="log">
          <strong>${{event.kind}}</strong> <span class="muted">${{event.level}}</span><br/>
          ${{event.message}}<br/>
          <span class="muted">${{new Date(event.timestamp).toLocaleTimeString()}}</span>
        </div>
      `).join('');
      document.getElementById('feed').innerHTML = feed || (data.resolved_project_id
        ? '<div class="muted">No supervisor events yet for the active project.</div>'
        : '<div class="muted">No active project detected yet.</div>');
    }}

    (function configureCrossHostLinks() {{
      const websiteUrl = new URL(window.location.href);
      websiteUrl.port = '3010';
      websiteUrl.pathname = '/';
      websiteUrl.search = '';
      websiteUrl.hash = '';
      document.getElementById('mainWebsiteLink').href = websiteUrl.toString();
    }})();

    document.getElementById('sendBtn').addEventListener('click', async () => {{
      const projectId = document.getElementById('projectId').value.trim();
      const message = document.getElementById('message').value.trim();
      if (!message) return;
      document.getElementById('chat').textContent = 'Supervisor is thinking...';
      const res = await fetch('/api/supervisor/chat', {{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{ project_id: projectId || null, message }})
      }});
      const data = await res.json();
      document.getElementById('chat').textContent = data.reply || data.detail || 'No response.';
    }});

    document.getElementById('logBtn').addEventListener('click', async () => {{
      const projectId = document.getElementById('projectId').value.trim();
      const message = document.getElementById('message').value.trim();
      if (!projectId || !message) {{
        document.getElementById('chat').textContent = 'Project ID and message are required to log an operator note.';
        return;
      }}
      const res = await fetch('/api/supervisor/operator-note', {{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{ project_id: projectId, message }})
      }});
      const data = await res.json();
      document.getElementById('chat').textContent = data.detail || 'Operator note logged.';
      document.getElementById('message').value = '';
      refreshStatus();
    }});

    refreshStatus();
    setInterval(refreshStatus, 2500);
  </script>
</body>
</html>"""
