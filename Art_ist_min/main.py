#!/usr/bin/env python3
"""Project launcher for ComfyUI and the website."""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
from urllib.error import URLError

from app_config import AppConfig, load_config
ROOT = Path(__file__).resolve().parent
COMFYUI_REPO = "https://github.com/comfyanonymous/ComfyUI.git"
LINKS_FILE = ROOT / "links.md"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_REASONING_MODEL = os.environ.get("OLLAMA_REASONING_MODEL", "gemma4:latest")
OLLAMA_CODER_MODEL = os.environ.get("OLLAMA_CODER_MODEL", "qwen2.5-coder:14b")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
OLLAMA_REQUIRED_MODELS = (
    OLLAMA_REASONING_MODEL,
    OLLAMA_CODER_MODEL,
    OLLAMA_VISION_MODEL,
)
APT_COMMAND_PACKAGES = {
    "curl": "curl",
    "fuser": "psmisc",
    "git": "git",
    "lsof": "lsof",
    "nano": "nano",
    "node": "nodejs",
    "npm": "npm",
    "wget": "wget",
}
APT_LIBRARY_PACKAGES = [
    "libgl1",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender1",
]
TTS_AUDIO_SUITE_DIRNAME = "TTS-Audio-Suite"
TTS_AUDIO_SUITE_APT_PACKAGES = [
    "libsamplerate0-dev",
    "portaudio19-dev",
    "libgl1",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender1",
]
MODEL_SECTION_DIRS = {
    "checkpoints": "checkpoints",
    "diffusion_models": "diffusion_models",
    "text_encoders": "text_encoders",
    "vae": "vae",
    "clip_vision": "clip_vision",
    "loras": "loras",
    "latent_upscale_models": "latent_upscale_models",
    "upscale_models": "upscale_models",
    "unet": "unet",
    "other_models": "other_models",
}


def log(message: str) -> None:
    print(message, flush=True)


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log(f"[RUN] {' '.join(shlex.quote(part) for part in cmd)}")
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True)


def _http_get_json(url: str) -> dict | list:
    with urlopen(url, timeout=10) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def _extend_pythonpath(*paths: Path) -> str:
    pythonpath_parts = [str(path) for path in paths]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        pythonpath_parts.append(existing)
    return os.pathsep.join(pythonpath_parts)


def ensure_command(command: str, install_hint: str) -> None:
    if shutil.which(command):
        return
    raise RuntimeError(f"Required command '{command}' was not found. {install_hint}")


def is_ollama_ready() -> bool:
    try:
        _http_get_json(f"{OLLAMA_HOST}/api/tags")
        return True
    except Exception:
        return False


def start_ollama_if_needed() -> subprocess.Popen[str] | None:
    ensure_command("ollama", "Install Ollama first or run ./bootstrap_vm.sh.")
    if is_ollama_ready():
        log(f"[INFO] Ollama is already reachable at {OLLAMA_HOST}")
        return None

    log("[START] Ollama: ollama serve")
    process = subprocess.Popen(
        ["ollama", "serve"],
        cwd=ROOT,
        env=os.environ.copy(),
    )

    deadline = time.time() + 45
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Ollama exited early with code {process.returncode}")
        if is_ollama_ready():
            log(f"[READY] Ollama is reachable at {OLLAMA_HOST}")
            return process
        time.sleep(1)

    process.terminate()
    raise RuntimeError(f"Ollama did not become ready at {OLLAMA_HOST} within 45 seconds")


def ensure_ollama_models() -> None:
    if not is_ollama_ready():
        raise RuntimeError(f"Ollama is not reachable at {OLLAMA_HOST}")

    try:
        data = _http_get_json(f"{OLLAMA_HOST}/api/tags")
    except URLError as exc:
        raise RuntimeError(f"Could not query Ollama models at {OLLAMA_HOST}") from exc

    models = {entry.get("name") for entry in data.get("models", []) if isinstance(entry, dict)}
    missing = [model for model in OLLAMA_REQUIRED_MODELS if model not in models]
    if not missing:
        log("[INFO] Required Ollama models are available")
        return

    for model in missing:
        log(f"[SETUP] Pulling missing Ollama model: {model}")
        run_command(["ollama", "pull", model], env=os.environ.copy())


def _get_node_major_version() -> int | None:
    if not shutil.which("node"):
        return None

    result = subprocess.run(["node", "--version"], capture_output=True, text=True, check=False)
    version_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0 or not version_text:
        return None

    normalized = version_text.lstrip("v")
    major_text = normalized.split(".", 1)[0]
    try:
        return int(major_text)
    except ValueError:
        return None


def ensure_apt_packages() -> None:
    if not shutil.which("apt-get"):
        return

    missing_packages = sorted(
        {
            package
            for command, package in APT_COMMAND_PACKAGES.items()
            if shutil.which(command) is None
        }
    )
    if not missing_packages:
        return

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise RuntimeError(
            "Missing required system packages: "
            f"{', '.join(missing_packages)}. Install them with apt or rerun as root."
        )

    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    log(f"[SETUP] Installing system packages via apt: {', '.join(missing_packages)}")
    run_command(["apt-get", "update"], env=env)
    run_command(["apt-get", "install", "-y", *missing_packages], env=env)


def ensure_apt_libraries(packages: list[str]) -> None:
    if not shutil.which("apt-get") or not packages:
        return

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise RuntimeError(
            "Missing required system libraries: "
            f"{', '.join(packages)}. Install them with apt or rerun as root."
        )

    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    log(f"[SETUP] Ensuring system libraries via apt: {', '.join(packages)}")
    run_command(["apt-get", "update"], env=env)
    run_command(["apt-get", "install", "-y", *packages], env=env)


def ensure_venv(config: AppConfig) -> Path:
    venv_python = config.venv_python
    if venv_python.exists():
        return venv_python

    log("[SETUP] Creating Python virtual environment")
    run_command([sys.executable, "-m", "venv", str(config.venv_dir)])
    return venv_python


def _comfyui_path_candidates(config: AppConfig) -> list[Path]:
    candidates = [
        config.comfyui_path,
        (config.project_root / "ComfyUI").resolve(),
        (config.project_root / "comfyui").resolve(),
    ]
    unique_candidates: list[Path] = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def find_comfyui_path(config: AppConfig) -> Path | None:
    for candidate in _comfyui_path_candidates(config):
        if (candidate / "main.py").exists():
            return candidate
    return None


def ensure_comfyui_checkout(config: AppConfig) -> Path:
    existing_checkout = find_comfyui_path(config)
    if existing_checkout is not None:
        return existing_checkout

    ensure_command("git", "Install git to clone ComfyUI.")
    target_dir = config.comfyui_path
    for candidate in _comfyui_path_candidates(config):
        if not candidate.exists():
            continue
        if not candidate.is_dir():
            raise RuntimeError(f"ComfyUI path exists but is not a directory: {candidate}")
        if any(candidate.iterdir()):
            raise RuntimeError(
                f"ComfyUI directory exists but is incomplete: {candidate}. "
                "Remove it or populate it with a valid ComfyUI checkout."
            )
        target_dir = candidate

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    log(f"[SETUP] Cloning ComfyUI from {COMFYUI_REPO} into {target_dir}")
    run_command(["git", "clone", COMFYUI_REPO, str(target_dir)])
    return target_dir


def install_python_dependencies(config: AppConfig) -> None:
    venv_python = ensure_venv(config)
    log("[SETUP] Installing Python runtime dependencies")
    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(venv_python), "-m", "pip", "install", "-r", str(config.requirements_file)])


def install_selected_torch_runtime(config: AppConfig) -> None:
    torch_index_url = os.environ.get("TORCH_INDEX_URL")
    torch_packages = os.environ.get("TORCH_PACKAGES", "torch torchvision torchaudio").split()
    if not torch_index_url or not torch_packages:
        return

    log(f"[SETUP] Installing PyTorch runtime from {torch_index_url}")
    run_command(
        [
            str(config.venv_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            *torch_packages,
            "--index-url",
            torch_index_url,
        ]
    )


def install_comfyui_requirements(config: AppConfig) -> None:
    if not config.start_comfyui:
        return

    install_selected_torch_runtime(config)
    requirements_file = ensure_comfyui_checkout(config) / "requirements.txt"
    if not requirements_file.exists():
        log(f"[WARN] Skipping ComfyUI requirements install because {requirements_file} does not exist")
        return

    log("[SETUP] Installing ComfyUI Python dependencies")
    run_command([str(config.venv_python), "-m", "pip", "install", "-r", str(requirements_file)])


def ensure_frontend_dependencies(config: AppConfig) -> bool:
    if not config.start_website:
        return False

    package_json = config.frontend_dir / "package.json"
    dist_dir = config.frontend_dir / "dist"
    if not package_json.exists():
        if dist_dir.exists():
            log(
                "[WARN] Frontend source checkout is missing package.json. "
                "Using existing frontend build from ai-art-generator-hub/dist."
            )
            return True
        log(
            "[WARN] Frontend source checkout is incomplete: "
            f"{package_json} does not exist. The website UI will be skipped."
        )
        return False

    if not shutil.which("npm"):
        if dist_dir.exists():
            log("[WARN] npm was not found. Using existing frontend build from ai-art-generator-hub/dist.")
            return True
        log("[WARN] npm was not found and no frontend build exists. The website UI will be skipped.")
        return False

    node_major = _get_node_major_version()
    if node_major is None:
        if dist_dir.exists():
            log("[WARN] Could not determine Node.js version. Using existing frontend build from ai-art-generator-hub/dist.")
            return True
        raise RuntimeError("Could not determine Node.js version. Install Node.js 18 or newer to build the frontend.")

    if node_major < 18:
        if dist_dir.exists():
            log(
                f"[WARN] Node.js {node_major} is too old for this frontend build. "
                "Using existing frontend build from ai-art-generator-hub/dist."
            )
            return True
        raise RuntimeError(
            f"Node.js {node_major} is too old for this frontend. "
            "Install Node.js 18 or newer (Node 20 LTS recommended), "
            "or run ./bootstrap_vm.sh on the target VM."
        )

    node_modules = config.frontend_dir / "node_modules"
    if node_modules.exists():
        log("[SETUP] Frontend dependencies already present, skipping npm install")
    else:
        log("[SETUP] Installing frontend dependencies")
        run_command(["npm", "install"], cwd=config.frontend_dir)

    log("[SETUP] Building frontend")
    run_command(["npm", "run", "build"], cwd=config.frontend_dir)
    return True


def kill_port(port: int) -> None:
    tools = (
        ["lsof", "-ti", f":{port}"],
        ["fuser", f"{port}/tcp"],
    )
    for tool in tools:
        if not shutil.which(tool[0]):
            continue
        result = subprocess.run(tool, capture_output=True, text=True, check=False)
        output = result.stdout if tool[0] == "lsof" else result.stderr
        pids = [token for token in output.split() if token.isdigit()]
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
                log(f"[INFO] Stopped process {pid} on port {port}")
            except ProcessLookupError:
                pass
        if pids:
            time.sleep(1)
        return


def start_process(
    name: str,
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    log(f"[START] {name}: {' '.join(shlex.quote(part) for part in cmd)}")
    process = subprocess.Popen(cmd, cwd=cwd, env=env)
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError(f"{name} exited early with code {process.returncode}")
    return process


def restart_process(
    process: subprocess.Popen[str] | None,
    name: str,
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return start_process(name, cmd, cwd=cwd, env=env)


def start_comfyui(config: AppConfig) -> subprocess.Popen[str] | None:
    if not config.start_comfyui:
        log("[SKIP] START_COMFYUI is false")
        return None

    comfyui_path = ensure_comfyui_checkout(config)
    comfyui_main = comfyui_path / "main.py"
    if not comfyui_main.exists():
        raise RuntimeError(f"ComfyUI entry point not found: {comfyui_main}")

    kill_port(config.comfyui_port)
    return start_process(
        "ComfyUI",
        [
            str(config.venv_python),
            str(comfyui_main),
            "--listen",
            config.comfyui_host,
            "--port",
            str(config.comfyui_port),
        ],
        cwd=comfyui_path,
        env=config.base_env,
    )


def _repo_dirname(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def _local_tts_audio_suite_path() -> Path:
    return ROOT / TTS_AUDIO_SUITE_DIRNAME


def _iter_active_links() -> Iterable[tuple[str | None, str]]:
    if not LINKS_FILE.exists():
        raise RuntimeError(f"Install manifest not found: {LINKS_FILE}")

    current_section: str | None = None
    for raw_line in LINKS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_section = line[3:].strip().lower()
            continue
        if line.startswith("#"):
            continue
        yield current_section, line


def get_active_model_downloads() -> list[tuple[str, str]]:
    downloads: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for section, line in _iter_active_links():
        if section not in MODEL_SECTION_DIRS:
            continue
        if not line.startswith("wget "):
            continue
        url = line[5:].strip()
        item = (section, url)
        if item in seen:
            continue
        seen.add(item)
        downloads.append(item)
    return downloads


def get_active_custom_node_repos() -> list[str]:
    repos: list[str] = []
    seen: set[str] = set()
    for _section, line in _iter_active_links():
        if not line.startswith("git clone "):
            continue
        repo = line[len("git clone ") :].strip()
        normalized = repo.removesuffix(".git")
        if normalized in seen:
            continue
        seen.add(normalized)
        repos.append(repo)
    return repos


def _download_filename(url: str) -> str:
    path = urlparse(url).path
    name = Path(unquote(path)).name
    if not name:
        raise RuntimeError(f"Could not determine filename from URL: {url}")
    return name


def install_model_downloads(config: AppConfig) -> None:
    comfyui_path = ensure_comfyui_checkout(config)
    models_root = comfyui_path / "models"
    downloads = get_active_model_downloads()
    if not downloads:
        log(f"[WARN] No active model downloads found in {LINKS_FILE}")
        return

    for section, url in downloads:
        target_dir = models_root / MODEL_SECTION_DIRS[section]
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / _download_filename(url)
        if target_file.exists():
            log(f"[SETUP] Model already present: {target_file.relative_to(comfyui_path)}")
            continue
        log(f"[SETUP] Downloading model into {target_dir.relative_to(comfyui_path)}: {target_file.name}")
        run_command(["wget", "-O", str(target_file), url])


def install_custom_nodes(config: AppConfig) -> None:
    ensure_command("git", "Install git to clone ComfyUI custom nodes.")
    custom_nodes_dir = ensure_comfyui_checkout(config) / "custom_nodes"
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)
    local_tts_audio_suite = _local_tts_audio_suite_path()

    for repo in get_active_custom_node_repos():
        target_dir = custom_nodes_dir / _repo_dirname(repo)
        if target_dir.name == TTS_AUDIO_SUITE_DIRNAME and local_tts_audio_suite.exists():
            log(
                "[SETUP] Skipping TTS-Audio-Suite git clone because a local modified "
                "checkout will be moved into ComfyUI/custom_nodes"
            )
            continue
        if target_dir.exists():
            log(f"[SETUP] Custom node already present: {target_dir.name}")
            continue
        log(f"[SETUP] Cloning custom node: {repo}")
        run_command(["git", "clone", repo], cwd=custom_nodes_dir)


def install_tts_audio_suite(config: AppConfig) -> None:
    comfyui_path = ensure_comfyui_checkout(config)
    custom_nodes_dir = comfyui_path / "custom_nodes"
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)

    source_dir = _local_tts_audio_suite_path()
    target_dir = custom_nodes_dir / TTS_AUDIO_SUITE_DIRNAME
    if not source_dir.exists():
        if target_dir.exists():
            log("[SETUP] TTS-Audio-Suite already present in ComfyUI/custom_nodes")
        else:
            log("[WARN] Local TTS-Audio-Suite checkout not found; skipping custom installer")
        return

    if target_dir.exists():
        log("[SETUP] TTS-Audio-Suite already present in ComfyUI/custom_nodes")
    else:
        log("[SETUP] Moving local TTS-Audio-Suite into ComfyUI/custom_nodes")
        shutil.move(str(source_dir), str(target_dir))

    ensure_apt_libraries(TTS_AUDIO_SUITE_APT_PACKAGES)
    install_script = target_dir / "install.py"
    if not install_script.exists():
        raise RuntimeError(f"TTS-Audio-Suite installer not found: {install_script}")

    log("[SETUP] Running TTS-Audio-Suite install.py")
    run_command([str(config.venv_python), str(install_script)], cwd=target_dir)

    step_audio_model_dir = comfyui_path / "models" / "TTS" / "step_audio_editx" / "Step-Audio-EditX"
    if step_audio_model_dir.exists():
        log("[SETUP] Step Audio EditX model already present")
        return

    step_audio_env = config.base_env.copy()
    step_audio_env["PYTHONPATH"] = _extend_pythonpath(comfyui_path, target_dir)

    log("[SETUP] Downloading Step Audio EditX model")
    run_command(
        [
            str(config.venv_python),
            "-m",
            "engines.step_audio_editx.step_audio_editx_downloader",
            "Step-Audio-EditX",
        ],
        cwd=target_dir,
        env=step_audio_env,
    )


def install_custom_node_requirements(config: AppConfig) -> None:
    custom_nodes_dir = ensure_comfyui_checkout(config) / "custom_nodes"
    for repo in get_active_custom_node_repos():
        node_dir = custom_nodes_dir / _repo_dirname(repo)
        requirements_file = node_dir / "requirements.txt"
        if not requirements_file.exists():
            continue
        log(f"[SETUP] Installing requirements for {node_dir.name}")
        run_command([str(config.venv_python), "-m", "pip", "install", "-r", str(requirements_file)])

    video_helper_suite_dir = custom_nodes_dir / "ComfyUI-VideoHelperSuite"
    if video_helper_suite_dir.exists():
        log("[SETUP] Installing ComfyUI-VideoHelperSuite extra packages")
        run_command(
            [
                str(config.venv_python),
                "-m",
                "pip",
                "install",
                "aiohttp",
                "tqdm",
                "rembg[cpu]",
                "rembg[gpu]",
                "accelerate",
                "gguf",
                "surrealist",
                "diffusers",
                "imageio-ffmpeg",
                "sageattention",
                "huggingface_hub",
            ]
        )
        run_command([str(config.venv_python), "-m", "pip", "uninstall", "-y", "onnxruntime", "onnxruntime-gpu"])
        onnxruntime_package = os.environ.get("ONNXRUNTIME_PACKAGE", "onnxruntime-gpu")
        onnxruntime_extra_index = os.environ.get(
            "ONNXRUNTIME_EXTRA_INDEX_URL",
            "https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/",
        )
        install_command = [
            str(config.venv_python),
            "-m",
            "pip",
            "install",
            onnxruntime_package,
        ]
        if onnxruntime_package == "onnxruntime-gpu" and onnxruntime_extra_index:
            install_command.extend(["--extra-index-url", onnxruntime_extra_index])
        log(f"[SETUP] Installing ONNX Runtime package: {onnxruntime_package}")
        run_command(install_command)


def ensure_opencv_runtime(config: AppConfig) -> None:
    ensure_apt_libraries(APT_LIBRARY_PACKAGES)

    log("[SETUP] Normalizing OpenCV runtime for headless ComfyUI")
    run_command(
        [
            str(config.venv_python),
            "-m",
            "pip",
            "uninstall",
            "-y",
            "opencv-python",
            "opencv-contrib-python",
            "opencv-python-headless",
        ],
        check=False,
    )
    run_command(
        [
            str(config.venv_python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "opencv-python-headless",
        ]
    )
    run_command([str(config.venv_python), "-c", "import cv2; print(cv2.__version__)"])


def start_website(config: AppConfig) -> subprocess.Popen[str]:
    kill_port(config.website_port)
    env = {
        **config.base_env,
        "WEBSITE_PORT": str(config.website_port),
        "PYTHONPATH": str(ROOT),
    }
    return start_process(
        "Website",
        [
            str(config.venv_python),
            "-m",
            "uvicorn",
            "api_server.main:app",
            "--host",
            config.website_host,
            "--port",
            str(config.website_port),
        ],
        cwd=ROOT,
        env=env,
    )


def terminate_processes(processes: Iterable[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    config = load_config(ROOT, prompt_for_ports=True)
    ensure_apt_packages()
    comfyui_path = find_comfyui_path(config) or config.comfyui_path

    log("Agentic Art Builder")
    log("===================")
    log(f"ComfyUI path: {comfyui_path}")
    log(f"Website: http://localhost:{config.website_port}")
    log(f"ComfyUI target: http://{config.comfyui_host}:{config.comfyui_port}")
    log(f"Ollama target: {OLLAMA_HOST}")

    install_python_dependencies(config)
    install_comfyui_requirements(config)
    frontend_ready = ensure_frontend_dependencies(config)

    processes: list[subprocess.Popen[str]] = []
    try:
        ollama_process = start_ollama_if_needed()
        if ollama_process is not None:
            processes.append(ollama_process)
        ensure_ollama_models()

        if config.start_comfyui:
            install_model_downloads(config)
            install_custom_nodes(config)
            install_tts_audio_suite(config)
            install_custom_node_requirements(config)
            ensure_opencv_runtime(config)
        comfyui_process = start_comfyui(config)
        if comfyui_process is not None:
            processes.append(comfyui_process)

        if config.start_website:
            if frontend_ready:
                processes.append(start_website(config))
            else:
                log("[SKIP] Website was not started because the frontend build is unavailable")
        else:
            log("[SKIP] START_WEBSITE is false")

        if not processes:
            log("[INFO] Nothing was started because both START_COMFYUI and START_WEBSITE are false")
            return

        log("[READY] Services are running.")
        log(f"[READY] Website UI: http://localhost:{config.website_port}")
        log(f"[READY] ComfyUI: http://{config.comfyui_host}:{config.comfyui_port}")
        log(f"[READY] Ollama API: {OLLAMA_HOST}")
        log("[READY] Press Ctrl+C to stop them.")
        while True:
            for process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    raise RuntimeError(f"Process {process.args[0]} exited with code {exit_code}")
            time.sleep(2)
    except KeyboardInterrupt:
        log("[INFO] Stopping services")
    finally:
        terminate_processes(processes)


if __name__ == "__main__":
    main()
