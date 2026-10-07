from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "run_story_builder.sh"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        return int(sock.getsockname()[1])


def _stubbed_environment(tmp_path: Path, *, backend_port: int, frontend_port: int) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "launches.log"
    curl_log = tmp_path / "curl.log"
    (bin_dir / "curl").write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> \"$LAUNCH_TEST_CURL_LOG\"\nexit 0\n"
    )
    python_stub = f"""#!/usr/bin/env bash
if [[ "$1" == "-c" ]]; then
  if [[ "${{LAUNCH_TEST_MISSING_MODULES:-0}}" == "1" && "$2" == *"import fastapi, uvicorn"* ]]; then
    exit 1
  fi
  exec {sys.executable!r} "$@"
fi
if [[ "$1" == "-m" && "$2" == "uvicorn" ]]; then
  printf 'backend %s\\n' "${{*: -1}}" >> "$LAUNCH_TEST_LOG"
  exec sleep 60
fi
exec {sys.executable!r} "$@"
"""
    (bin_dir / "python3").write_text(python_stub)
    (bin_dir / "npm").write_text(
        "#!/usr/bin/env bash\nprintf 'frontend %s\\n' \"$*\" >> \"$LAUNCH_TEST_LOG\"\nexec sleep 60\n"
    )
    for stub in (bin_dir / "curl", bin_dir / "python3", bin_dir / "npm"):
        stub.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "LAUNCH_TEST_LOG": str(log),
        "LAUNCH_TEST_CURL_LOG": str(curl_log),
        "STORY_BUILDER_BACKEND_PORT": str(backend_port),
        "STORY_BUILDER_FRONTEND_PORT": str(frontend_port),
        "STORY_BUILDER_SERVICE_WAIT_SECONDS": "1",
    })
    return env, log, curl_log


def _wait_for_lines(path: Path, count: int, timeout: float = 5.0) -> list[str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lines = path.read_text().splitlines() if path.exists() else []
        if len(lines) >= count:
            return lines
        time.sleep(0.02)
    raise AssertionError(f"Expected {count} launch records in {path}; got {path.read_text() if path.exists() else ''}")


def test_launcher_prevents_duplicate_start_and_requests_strict_frontend_port(tmp_path: Path) -> None:
    backend_port, frontend_port = _free_port(), _free_port()
    while frontend_port == backend_port:
        frontend_port = _free_port()
    env, log, _ = _stubbed_environment(tmp_path, backend_port=backend_port, frontend_port=frontend_port)
    first = subprocess.Popen(["bash", str(LAUNCHER)], cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        records = _wait_for_lines(log, 2)
        assert f"backend {backend_port}" in records
        assert any(f"--port {frontend_port} --strictPort" in record for record in records)

        second = subprocess.run(["bash", str(LAUNCHER)], cwd=REPO_ROOT, env=env,
            capture_output=True, text=True, timeout=5)
        assert second.returncode != 0
        assert "already starting or running" in second.stderr
        assert len(log.read_text().splitlines()) == 2
    finally:
        first.terminate()
        try:
            first.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            first.kill()
            first.communicate(timeout=5)


def test_launcher_fails_before_ai_services_when_python_or_port_preflight_fails(tmp_path: Path) -> None:
    backend_port, frontend_port = _free_port(), _free_port()
    env, _, curl_log = _stubbed_environment(tmp_path, backend_port=backend_port, frontend_port=frontend_port)
    missing = subprocess.run(["bash", str(LAUNCHER)], cwd=REPO_ROOT,
        env={**env, "LAUNCH_TEST_MISSING_MODULES": "1"}, capture_output=True, text=True, timeout=5)
    assert missing.returncode != 0
    assert "cannot import FastAPI and Uvicorn" in missing.stderr
    assert not curl_log.exists()

    with socket.socket() as occupied:
        occupied.bind(("0.0.0.0", backend_port))
        occupied.listen()
        port_failure = subprocess.run(["bash", str(LAUNCHER)], cwd=REPO_ROOT, env=env,
            capture_output=True, text=True, timeout=5)
    assert port_failure.returncode != 0
    assert f"backend port {backend_port} is already in use" in port_failure.stderr
    assert "ss -ltnp" in port_failure.stderr
    assert not curl_log.exists()


def test_backend_exit_cleans_frontend_process_group_grandchild(tmp_path: Path) -> None:
    backend_port, frontend_port = _free_port(), _free_port()
    env, _, _ = _stubbed_environment(tmp_path, backend_port=backend_port, frontend_port=frontend_port)
    bin_dir = Path(env["PATH"].split(":", 1)[0])
    python_stub = (bin_dir / "python3").read_text()
    python_stub = python_stub.replace(
        "  exec sleep 60\nfi\nexec ",
        "  sleep 0.2\n  exit 23\nfi\nexec ",
        1,
    )
    (bin_dir / "python3").write_text(python_stub)
    npm_stub = (bin_dir / "npm").read_text().replace(
        "exec sleep 60",
        "sleep 60 &\nchild=$!\nprintf '%s\\n' \"$child\" > \"$LAUNCH_TEST_FRONTEND_CHILD_PID\"\nwait \"$child\"",
        1,
    )
    (bin_dir / "npm").write_text(npm_stub)
    child_pid_file = tmp_path / "frontend-child.pid"
    env["LAUNCH_TEST_FRONTEND_CHILD_PID"] = str(child_pid_file)
    launcher = subprocess.Popen(
        ["bash", str(LAUNCHER)], cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        output, _ = launcher.communicate(timeout=8)
        assert launcher.returncode == 23, output
        assert child_pid_file.exists(), output
        child_pid = int(child_pid_file.read_text().strip())
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            stat_file = Path(f"/proc/{child_pid}/stat")
            if not stat_file.exists() or stat_file.read_text().split()[2] == "Z":
                break
            time.sleep(0.02)
        else:
            raise AssertionError(f"frontend grandchild {child_pid} survived launcher cleanup")
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.communicate(timeout=5)
