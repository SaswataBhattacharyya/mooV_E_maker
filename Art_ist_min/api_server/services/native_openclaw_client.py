"""Native OpenClaw Gateway client for supervision requests."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_GATEWAY_PORT = os.environ.get("OPENCLAW_GATEWAY_PORT", "18789")
DEFAULT_GATEWAY_HOST = os.environ.get("OPENCLAW_GATEWAY_HOST", "127.0.0.1")
DEFAULT_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", f"http://{DEFAULT_GATEWAY_HOST}:{DEFAULT_GATEWAY_PORT}")
DEFAULT_CHAT_MODEL = os.environ.get("OPENCLAW_GATEWAY_MODEL", "openclaw/default")
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("OPENCLAW_GATEWAY_TIMEOUT_SECONDS", "300"))
LOCAL_PROVIDER_MARKERS = ("ollama", "local")
CLOUD_PROVIDER_MARKERS = ("openrouter", "openai", "anthropic", "google", "gemini", "xai", "groq", "deepseek")


class NativeOpenClawError(RuntimeError):
    """Raised when the native OpenClaw Gateway cannot satisfy a supervision request."""


def _load_openclaw_config() -> dict[str, Any]:
    config_path = Path(os.environ.get("OPENCLAW_CONFIG_PATH", Path.home() / ".openclaw" / "openclaw.json"))
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (PermissionError, json.JSONDecodeError):
        return {}


def load_openclaw_config() -> dict[str, Any]:
    """Expose the parsed OpenClaw config for runtime policy decisions."""

    return _load_openclaw_config()


def _gateway_url() -> str:
    config = _load_openclaw_config()
    gateway = config.get("gateway", {}) if isinstance(config, dict) else {}
    port = os.environ.get("OPENCLAW_GATEWAY_PORT") or gateway.get("port") or DEFAULT_GATEWAY_PORT
    bind = str(gateway.get("bind") or "loopback").strip().lower()
    host = os.environ.get("OPENCLAW_GATEWAY_HOST")
    if not host:
        host = "127.0.0.1" if bind == "loopback" else DEFAULT_GATEWAY_HOST
    return os.environ.get("OPENCLAW_GATEWAY_URL", f"http://{host}:{port}")


def _gateway_token() -> str:
    direct = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if direct:
        return direct
    config = _load_openclaw_config()
    gateway = config.get("gateway", {}) if isinstance(config, dict) else {}
    auth = gateway.get("auth", {}) if isinstance(gateway, dict) else {}
    token = auth.get("token")
    return str(token).strip() if token else ""


def _gateway_auth_mode() -> str:
    config = _load_openclaw_config()
    gateway = config.get("gateway", {}) if isinstance(config, dict) else {}
    auth = gateway.get("auth", {}) if isinstance(gateway, dict) else {}
    return str(auth.get("mode") or os.environ.get("OPENCLAW_GATEWAY_AUTH_MODE") or "token").strip().lower()


def gateway_summary() -> dict[str, Any]:
    return {
        "url": _gateway_url(),
        "auth_mode": _gateway_auth_mode(),
        "model": DEFAULT_CHAT_MODEL,
    }


def _flatten_config_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        flattened: list[str] = []
        for child in value.values():
            flattened.extend(_flatten_config_values(child))
        return flattened
    if isinstance(value, list):
        flattened = []
        for child in value:
            flattened.extend(_flatten_config_values(child))
        return flattened
    if isinstance(value, str):
        return [value.lower()]
    return []


def gateway_runtime_summary() -> dict[str, Any]:
    config = _load_openclaw_config()
    env_markers = [
        os.environ.get("OPENCLAW_PROVIDER", "").strip().lower(),
        os.environ.get("OPENCLAW_GATEWAY_PROVIDER", "").strip().lower(),
    ]
    config_values = _flatten_config_values(config)
    combined = [value for value in [*env_markers, *config_values] if value]

    provider_name = "unknown"
    provider_mode = "assumed_local"
    is_local = True

    for marker in combined:
        if any(token in marker for token in CLOUD_PROVIDER_MARKERS):
            provider_name = marker
            provider_mode = "cloud"
            is_local = False
            break
        if any(token in marker for token in LOCAL_PROVIDER_MARKERS):
            provider_name = marker
            provider_mode = "local"
            is_local = True
            break

    return {
        **gateway_summary(),
        "provider_name": provider_name,
        "provider_mode": provider_mode,
        "is_local": is_local,
        "config_present": bool(config),
    }


def _clean_json_text(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return text


def _extract_message_text(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content.strip()
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    auth_mode = _gateway_auth_mode()
    if auth_mode in {"token", "password"}:
        token = _gateway_token()
        if not token:
            raise NativeOpenClawError(
                "Native OpenClaw Gateway requires auth, but no gateway token/password is available. "
                "Set OPENCLAW_GATEWAY_TOKEN or make sure ~/.openclaw/openclaw.json contains gateway.auth.token."
            )
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{_gateway_url().rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = f"Native OpenClaw Gateway returned HTTP {exc.code}"
        if exc.code == 404:
            detail = (
                "Native OpenClaw Gateway does not expose /v1/chat/completions. "
                "Enable gateway.http.endpoints.chatCompletions.enabled in OpenClaw."
            )
        elif body:
            detail = f"{detail}: {body}"
        raise NativeOpenClawError(detail) from exc
    except urllib.error.URLError as exc:
        raise NativeOpenClawError(f"Could not reach native OpenClaw Gateway at {_gateway_url()}") from exc


def _encode_image_to_data_url(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".jpg":
        suffix = ".jpeg"
    mime = {
        ".png": "image/png",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode('ascii')}"


def generate_text(*, prompt: str, temperature: float = 0.2, user: str | None = None) -> str:
    payload: dict[str, Any] = {
        "model": DEFAULT_CHAT_MODEL,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if user:
        payload["user"] = user
    raw = _request_json(payload)
    try:
        return _extract_message_text(raw["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise NativeOpenClawError("Native OpenClaw Gateway returned an unexpected response shape") from exc


def generate_json(*, prompt: str, temperature: float = 0.2, user: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": DEFAULT_CHAT_MODEL,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    if user:
        payload["user"] = user
    raw = _request_json(payload)
    try:
        message = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise NativeOpenClawError("Native OpenClaw Gateway returned an unexpected response shape") from exc
    text = _clean_json_text(_extract_message_text(message))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeOpenClawError("Native OpenClaw Gateway did not return valid JSON") from exc


def generate_vision_json(
    *,
    prompt: str,
    image_paths: list[str],
    temperature: float = 0.2,
    user: str | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": _encode_image_to_data_url(path)}})
    payload: dict[str, Any] = {
        "model": DEFAULT_CHAT_MODEL,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    if user:
        payload["user"] = user
    raw = _request_json(payload)
    try:
        message = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise NativeOpenClawError("Native OpenClaw Gateway returned an unexpected response shape") from exc
    text = _clean_json_text(_extract_message_text(message))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise NativeOpenClawError("Native OpenClaw Gateway did not return valid JSON") from exc
