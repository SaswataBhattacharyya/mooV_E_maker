"""Provider-neutral JSON reasoning for Story Builder.

This adapter deliberately exposes model reasoning only. Media executors,
ComfyUI jobs, storage writes, and application authorization stay in their
existing services. Codex runs with no project working directory and no
write-enabled agent sandbox.
"""

from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import ollama_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PROJECT_ROOT / "storage" / "reasoning_provider.json"
SUPPORTED_PROVIDERS = {"ollama", "codex"}
DEFAULT_CODEX_MODEL = os.environ.get("CODEX_REASONING_MODEL", "gpt-6-luna")
_SETTINGS_LOCK = threading.RLock()
_ACTIVE_PROVIDER: ContextVar[str | None] = ContextVar("story_reasoning_provider", default=None)


class ReasoningProviderError(RuntimeError):
    """Raised when the selected reasoning provider cannot return valid JSON."""


def _default_settings() -> dict[str, Any]:
    configured = os.environ.get("STORY_BUILDER_REASONING_PROVIDER", "codex").lower()
    return {"provider": configured if configured in SUPPORTED_PROVIDERS else "codex"}


def get_settings() -> dict[str, Any]:
    """Read the persisted provider selection, defaulting eligible reasoning to Codex."""
    with _SETTINGS_LOCK:
        settings = _default_settings()
        try:
            stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            provider = str(stored.get("provider", "")).lower()
            if provider in SUPPORTED_PROVIDERS:
                settings["provider"] = provider
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            pass
        return settings


def set_provider(provider: str) -> dict[str, Any]:
    """Persist an allow-listed provider name; credentials never enter this file."""
    selected = str(provider).lower()
    if selected not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported reasoning provider: {provider}")
    with _SETTINGS_LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SETTINGS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps({"provider": selected}, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
    return get_settings()


@contextmanager
def use_provider(provider: str | None) -> Iterator[None]:
    """Pin a provider for one background run so UI changes do not affect it."""
    if provider is None:
        yield
        return
    selected = str(provider).lower()
    if selected not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported reasoning provider: {provider}")
    token: Token[str | None] = _ACTIVE_PROVIDER.set(selected)
    try:
        yield
    finally:
        _ACTIVE_PROVIDER.reset(token)


def activate_provider(provider: str | None) -> Token[str | None] | None:
    """Set a provider in the current worker context and return its reset token."""
    if provider is None:
        return None
    selected = str(provider).lower()
    if selected not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported reasoning provider: {provider}")
    return _ACTIVE_PROVIDER.set(selected)


def reset_provider(token: Token[str | None] | None) -> None:
    if token is not None:
        _ACTIVE_PROVIDER.reset(token)


def _selected_provider(provider: str | None) -> str:
    selected = provider or _ACTIVE_PROVIDER.get() or get_settings()["provider"]
    selected = str(selected).lower()
    if selected not in SUPPORTED_PROVIDERS:
        raise ReasoningProviderError(f"Unsupported reasoning provider: {selected}")
    return selected


def provider_catalog() -> dict[str, Any]:
    """Return safe UI metadata; this does not call a paid model or reveal secrets."""
    return {
        "provider": get_settings()["provider"],
        "providers": [
            {
                "id": "ollama",
                "label": "Ollama (current)",
                "model": ollama_client.DEFAULT_OLLAMA_MODEL,
                "available": bool(shutil.which("ollama")),
                "compatibility": True,
            },
            {
                "id": "codex",
                "label": "Codex",
                "model": DEFAULT_CODEX_MODEL,
                "available": bool(shutil.which("codex")),
                "compatibility": False,
            },
        ],
    }


def _run_json_command(command: list[str], prompt: str, *, timeout_seconds: int = 300) -> str:
    try:
        with tempfile.TemporaryDirectory(prefix="story-builder-reasoning-") as isolated_cwd:
            guarded_command = command
            if sys.platform.startswith("linux"):
                guard = Path(__file__).with_name("provider_exec_guard.py")
                guarded_command = [sys.executable, str(guard), str(os.getpid()), *command]
            process = subprocess.Popen(
                guarded_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=isolated_cwd,
                start_new_session=(os.name == "posix"),
            )
            try:
                stdout, stderr = process.communicate(input=prompt, timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (AttributeError, ProcessLookupError):
                    process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (AttributeError, ProcessLookupError):
                        process.kill()
                    stdout, stderr = process.communicate()
                raise ReasoningProviderError(
                    f"{command[0]} timed out after {timeout_seconds} seconds"
                ) from exc
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise ReasoningProviderError(f"Reasoning command is not installed: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReasoningProviderError(f"{command[0]} timed out after {timeout_seconds} seconds") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "provider command failed").strip()
        raise ReasoningProviderError(f"{command[0]} failed: {detail[-1800:]}")
    return result.stdout.strip()


def _parse_dict(text: str, provider: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ReasoningProviderError(f"{provider} did not return a valid JSON object")


def _codex_json(prompt: str) -> dict[str, Any]:
    if not shutil.which("codex"):
        raise ReasoningProviderError("Codex CLI is not installed or not on PATH")
    command = [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral",
        "--sandbox", "read-only", "--ignore-user-config", "--model",
        DEFAULT_CODEX_MODEL, "--json", "-",
    ]
    output = _run_json_command(command, prompt)
    messages: list[str] = []
    failures: list[str] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
        elif event.get("type") in {"turn.failed", "error"}:
            failures.append(str(event.get("error") or event.get("message") or event))
    if not messages:
        if failures:
            raise ReasoningProviderError("Codex failed: " + "; ".join(failures)[-1800:])
        raise ReasoningProviderError("Codex completed without a final assistant message")
    return _parse_dict(messages[-1], "Codex")


def generate_json(
    *,
    prompt: str,
    temperature: float = 0.4,
    provider: str | None = None,
    cpu_only: bool = False,
    gpu_admission_timeout_seconds: int = 24 * 3600,
) -> dict[str, Any]:
    """Generate structured reasoning with the selected, explicit backend."""
    selected = _selected_provider(provider)
    if selected == "ollama":
        try:
            return ollama_client.generate_json(prompt=prompt, temperature=temperature, cpu_only=cpu_only,
                gpu_admission_timeout_seconds=gpu_admission_timeout_seconds)
        except ollama_client.OllamaError as exc:
            raise ReasoningProviderError(str(exc)) from exc
    if selected == "codex":
        return _codex_json(prompt)
    raise ReasoningProviderError(f"Unsupported reasoning provider: {selected}")


def test_provider(provider: str) -> dict[str, Any]:
    """Run a tiny no-side-effect structured-output smoke test."""
    selected = _selected_provider(provider)
    started = datetime.now(timezone.utc)
    result = generate_json(
        provider=selected,
        temperature=0,
        cpu_only=True,
        gpu_admission_timeout_seconds=120,
        prompt=(
            'This is a provider connectivity test, not a real project. '
            'Return only this JSON object: {"ok":true,"task":"director_provider_smoke_test"}'
        ),
    )
    if result.get("ok") is not True or result.get("task") != "director_provider_smoke_test":
        raise ReasoningProviderError(f"{selected} returned an unexpected smoke-test payload")
    return {
        "provider": selected,
        "model": next((item["model"] for item in provider_catalog()["providers"] if item["id"] == selected), None),
        "ok": True,
        "result": result,
        "elapsed_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
    }


def model_for(provider: str) -> str | None:
    selected = _selected_provider(provider)
    return next((item["model"] for item in provider_catalog()["providers"] if item["id"] == selected), None)
