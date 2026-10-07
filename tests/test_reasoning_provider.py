from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from story_builder.services import reasoning_provider as reasoning


def test_provider_setting_defaults_to_codex_and_is_allowlisted(tmp_path, monkeypatch):
    monkeypatch.setattr(reasoning, "SETTINGS_PATH", tmp_path / "reasoning.json")
    monkeypatch.delenv("STORY_BUILDER_REASONING_PROVIDER", raising=False)

    assert reasoning.get_settings()["provider"] == "codex"
    assert reasoning.set_provider("codex")["provider"] == "codex"
    assert reasoning.get_settings()["provider"] == "codex"
    with pytest.raises(ValueError, match="Unsupported reasoning provider"):
        reasoning.set_provider("hermes")
    with pytest.raises(ValueError, match="Unsupported reasoning provider"):
        reasoning.set_provider("shell")


def test_codex_adapter_uses_read_only_ephemeral_jsonl_and_parses_final_message(tmp_path, monkeypatch):
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok":true}'}}
    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        def communicate(**call_kwargs):
            captured["input"] = call_kwargs.get("input")
            return json.dumps(event) + "\n", ""
        return SimpleNamespace(pid=123, returncode=0,
            communicate=communicate)

    monkeypatch.setattr(reasoning.shutil, "which", lambda command: "/usr/bin/codex" if command == "codex" else None)
    monkeypatch.setattr(reasoning.subprocess, "Popen", fake_popen)
    assert reasoning.generate_json(provider="codex", prompt="private test prompt") == {"ok": True}
    command = captured["command"]
    assert "--sandbox" in command and command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command and "--ignore-user-config" in command and "--json" in command
    assert command[-1] == "-"
    assert captured["input"] == "private test prompt"
    assert captured["kwargs"]["stdin"] == subprocess.PIPE
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["cwd"] != str(reasoning.PROJECT_ROOT)


def test_codex_malformed_output_is_rejected(monkeypatch):
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": "not json"}}
    monkeypatch.setattr(reasoning.shutil, "which", lambda command: "/usr/bin/codex" if command == "codex" else None)
    monkeypatch.setattr(reasoning.subprocess, "Popen", lambda command, **kwargs: SimpleNamespace(
        pid=123, returncode=0, communicate=lambda **_kwargs: (json.dumps(event), "")))
    with pytest.raises(reasoning.ReasoningProviderError, match="valid JSON"):
        reasoning.generate_json(provider="codex", prompt="test")


def test_cpu_only_flag_reaches_selected_ollama_provider(monkeypatch):
    captured = {}

    def fake_generate_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(reasoning.ollama_client, "generate_json", fake_generate_json)
    assert reasoning.generate_json(provider="ollama", prompt="review", cpu_only=True,
        gpu_admission_timeout_seconds=37) == {"ok": True}
    assert captured["cpu_only"] is True
    assert captured["gpu_admission_timeout_seconds"] == 37


def test_provider_smoke_test_is_cpu_only_and_admission_bounded(monkeypatch):
    captured = {}

    def fake_generate_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "task": "director_provider_smoke_test"}

    monkeypatch.setattr(reasoning, "generate_json", fake_generate_json)
    result = reasoning.test_provider("codex")

    assert result["ok"] is True
    assert captured["provider"] == "codex"
    assert captured["cpu_only"] is True
    assert captured["gpu_admission_timeout_seconds"] == 120


def test_linux_provider_cli_exits_when_owning_worker_is_force_killed(tmp_path):
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux PR_SET_PDEATHSIG is the target host lifecycle guarantee")
    marker = tmp_path / "provider.pid"
    provider_script = tmp_path / "fake_provider.py"
    provider_script.write_text(
        "import os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "while True: time.sleep(0.1)\n",
        encoding="utf-8",
    )
    worker_script = (
        "import sys\n"
        "from story_builder.services.reasoning_provider import _run_json_command\n"
        "_run_json_command([sys.executable, sys.argv[1], sys.argv[2]], 'test', timeout_seconds=60)\n"
    )
    environment = dict(os.environ)
    pythonpath = str(reasoning.PROJECT_ROOT.parent)
    environment["PYTHONPATH"] = pythonpath + os.pathsep + environment.get("PYTHONPATH", "")
    worker = subprocess.Popen([sys.executable, "-c", worker_script,
        str(provider_script), str(marker)], cwd=tmp_path, env=environment)
    provider_pid = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.05)
        assert marker.exists(), "guarded provider did not start"
        provider_pid = int(marker.read_text(encoding="utf-8"))
        os.kill(worker.pid, signal.SIGKILL)
        worker.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            proc_stat = Path(f"/proc/{provider_pid}/stat")
            if not proc_stat.exists() or proc_stat.read_text().split(") ", 1)[1].startswith("Z "):
                break
            time.sleep(0.05)
        proc_stat = Path(f"/proc/{provider_pid}/stat")
        assert not proc_stat.exists() or proc_stat.read_text().split(") ", 1)[1].startswith("Z "), \
            "provider CLI survived SIGKILL of its worker process"
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)
        if provider_pid:
            proc_stat = Path(f"/proc/{provider_pid}/stat")
            if proc_stat.exists() and not proc_stat.read_text().split(") ", 1)[1].startswith("Z "):
                os.kill(provider_pid, signal.SIGKILL)


def test_provider_timeout_terminates_its_owned_process_group(monkeypatch):
    calls = []

    class TimeoutProcess:
        pid = 456
        returncode = -signal.SIGTERM

        def communicate(self, **kwargs):
            calls.append(("communicate", kwargs))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired("provider", kwargs["timeout"])
            return "", ""

    monkeypatch.setattr(reasoning.subprocess, "Popen", lambda *_args, **_kwargs: TimeoutProcess())
    def terminate_group(pid, sig):
        calls.append(("killpg", (pid, sig)))
    monkeypatch.setattr(reasoning.os, "killpg", terminate_group)

    with pytest.raises(reasoning.ReasoningProviderError, match="timed out after 1 seconds"):
        reasoning._run_json_command(["provider"], "bounded", timeout_seconds=1)
    assert calls == [
        ("communicate", {"input": "bounded", "timeout": 1}),
        ("killpg", (456, signal.SIGTERM)),
        ("communicate", {"timeout": 5}),
    ]
