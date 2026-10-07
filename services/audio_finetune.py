"""Project-scoped F5-TTS dataset validation and preparation.

This module deliberately stops before training. It prepares the artifact layout
expected by the installed F5-TTS code without mutating that custom node or its
base checkpoints.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import soundfile as sf
from datasets.arrow_writer import ArrowWriter


SUPPORTED_MODELS = {
    "F5TTS_v1_Base": "model_1250000.safetensors",
    "F5TTS_Base": "model_1200000.pt",
    "E2TTS_Base": "model_1200000.pt",
}
DATASET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aac"}


class F5DatasetError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _suite_root() -> Path:
    configured = os.environ.get("TTS_AUDIO_SUITE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    comfy_root = Path(os.environ.get("COMFYUI_ROOT", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI"))
    return comfy_root.expanduser().resolve() / "custom_nodes" / "TTS-Audio-Suite"


def _models_root() -> Path:
    comfy_root = Path(os.environ.get("COMFYUI_ROOT", "/home/riki/web_dev/setup_comfy_and-stuff/ComfyUI"))
    return comfy_root.expanduser().resolve() / "models" / "TTS" / "F5-TTS"


def _checkpoint(model: str) -> Path:
    if model not in SUPPORTED_MODELS:
        raise F5DatasetError(f"Unsupported local F5 fine-tuning base model: {model}")
    return _models_root() / model / SUPPORTED_MODELS[model]


def preflight() -> dict[str, Any]:
    suite = _suite_root()
    prepare_script = suite / "engines" / "f5_tts" / "train" / "datasets" / "prepare_csv_wavs.py"
    finetune_cli = suite / "engines" / "f5_tts" / "train" / "finetune_cli.py"
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("architecture", True, os.uname().machine)
    add("ffprobe", shutil.which("ffprobe") is not None, shutil.which("ffprobe") or "not found")
    add("suite_source", suite.is_dir(), str(suite))
    add("prepare_source", prepare_script.is_file(), str(prepare_script))
    add("finetune_source", finetune_cli.is_file(), str(finetune_cli))
    for module in ("torch", "torchaudio", "datasets", "soundfile", "accelerate"):
        add(f"python:{module}", importlib.util.find_spec(module) is not None, sys.executable)
    try:
        import torch

        add("cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "not available")
    except Exception as exc:  # pragma: no cover - environment dependent
        add("cuda", False, str(exc))
    for model in SUPPORTED_MODELS:
        checkpoint = _checkpoint(model)
        add(f"checkpoint:{model}", checkpoint.is_file(), str(checkpoint))

    prepare_import_ok = False
    prepare_detail = "source not found"
    if prepare_script.is_file():
        source = prepare_script.read_text(encoding="utf-8", errors="replace")
        prepare_import_ok = "from ...model.utils import" in source
        prepare_detail = "module import is valid" if prepare_import_ok else "installed script uses broken '..model' relative import; Story Builder compatibility preparer will be used"
    add("suite_prepare_import", prepare_import_ok, prepare_detail)
    cached_ok = False
    cached_detail = "cached_path is not importable"
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from cached_path import cached_path"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        cached_ok = result.returncode == 0
        cached_detail = "importable" if cached_ok else (result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "import failed")
    except Exception as exc:  # pragma: no cover - environment dependent
        cached_detail = str(exc)
    add("training_cli_cached_path", cached_ok, cached_detail)
    return {
        "architecture": os.uname().machine,
        "supported_models": list(SUPPORTED_MODELS),
        "checks": checks,
        "preparation_ready": all(item["ok"] for item in checks if item["name"] in {"ffprobe", "suite_source", "python:datasets", "python:soundfile"})
        and any(_checkpoint(model).is_file() for model in SUPPORTED_MODELS),
        "training_ready": all(item["ok"] for item in checks),
        "training_enabled": False,
    }


def read_metadata(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise F5DatasetError("metadata.csv must be UTF-8") from exc
    rows = list(csv.reader(text.splitlines(), delimiter="|"))
    if not rows or [value.strip().lower() for value in rows[0][:2]] != ["audio_file", "text"]:
        raise F5DatasetError("metadata.csv must start with the header audio_file|text")
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    for line_number, row in enumerate(rows[1:], 2):
        if len(row) < 2:
            raise F5DatasetError(f"metadata.csv line {line_number} must contain audio_file|text")
        filename = Path(row[0].strip()).name
        transcript = row[1].strip()
        if not filename or not transcript:
            raise F5DatasetError(f"metadata.csv line {line_number} has an empty filename or transcript")
        if filename in seen:
            raise F5DatasetError(f"metadata.csv contains duplicate audio file: {filename}")
        if Path(filename).suffix.lower() not in AUDIO_SUFFIXES:
            raise F5DatasetError(f"Unsupported training audio type: {filename}")
        seen.add(filename)
        parsed.append({"filename": filename, "text": transcript})
    if not parsed:
        raise F5DatasetError("metadata.csv must contain at least one training sample")
    return parsed


def validate_audio(path: Path) -> dict[str, Any]:
    try:
        info = sf.info(path)
        if info.frames <= 0 or info.samplerate <= 0:
            raise F5DatasetError(f"Audio is empty: {path.name}")
        peak = 0.0
        with sf.SoundFile(path) as handle:
            while True:
                block = handle.read(65536, dtype="float32", always_2d=True)
                if not len(block):
                    break
                block_peak = float(abs(block).max())
                peak = max(peak, block_peak)
        if peak < 1e-5:
            raise F5DatasetError(f"Audio appears silent: {path.name}")
        return {
            "filename": path.name,
            "duration": round(info.frames / info.samplerate, 4),
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "peak": round(peak, 6),
        }
    except F5DatasetError:
        raise
    except Exception as exc:
        raise F5DatasetError(f"Could not read audio {path.name}: {exc}") from exc


def stage_dataset(*, project_dir: Path, dataset_name: str, model: str, metadata: bytes, uploads: list[tuple[str, bytes]]) -> dict[str, Any]:
    clean_name = dataset_name.strip()
    if not DATASET_NAME_RE.fullmatch(clean_name):
        raise F5DatasetError("Dataset name must be 1-80 letters, numbers, dot, underscore, or hyphen")
    _checkpoint(model)
    entries = read_metadata(metadata)
    upload_map: dict[str, bytes] = {}
    for filename, content in uploads:
        safe_name = Path(filename).name
        if safe_name in upload_map:
            raise F5DatasetError(f"Duplicate uploaded filename: {safe_name}")
        upload_map[safe_name] = content
    expected = {entry["filename"] for entry in entries}
    missing = sorted(expected - set(upload_map))
    extras = sorted(set(upload_map) - expected)
    if missing:
        raise F5DatasetError(f"Missing uploaded audio listed by metadata.csv: {', '.join(missing)}")
    if extras:
        raise F5DatasetError(f"Uploaded audio is not listed by metadata.csv: {', '.join(extras)}")

    root = project_dir / "audio" / "finetune" / clean_name
    if root.exists():
        raise FileExistsError(f"An F5 dataset named '{clean_name}' already exists in this project")
    input_dir = root / "input"
    wavs_dir = input_dir / "wavs"
    wavs_dir.mkdir(parents=True, exist_ok=False)
    try:
        samples: list[dict[str, Any]] = []
        for entry in entries:
            target = wavs_dir / entry["filename"]
            target.write_bytes(upload_map[entry["filename"]])
            samples.append({**entry, **validate_audio(target)})
        with (input_dir / "metadata.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="|", lineterminator="\n")
            writer.writerow(["audio_file", "text"])
            for entry in entries:
                writer.writerow([f"wavs/{entry['filename']}", entry["text"]])
        manifest = {
            "version": 1,
            "dataset_name": clean_name,
            "base_model": model,
            "created_at": utc_now(),
            "status": "validated",
            "sample_count": len(samples),
            "total_duration": round(sum(item["duration"] for item in samples), 4),
            "sample_rates": sorted({item["sample_rate"] for item in samples}),
            "samples": samples,
            "input_dir": str(input_dir),
            "prepared_dir": str(root / "prepared"),
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _convert_texts(texts: list[str]) -> list[str]:
    utils_path = _suite_root() / "engines" / "f5_tts" / "model" / "utils.py"
    spec = importlib.util.spec_from_file_location("story_builder_f5_utils", utils_path)
    if spec is None or spec.loader is None:
        raise F5DatasetError(f"Could not load F5 text utilities from {utils_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.convert_char_to_pinyin(texts, polyphone=True))


def prepare_dataset(*, project_dir: Path, job: dict[str, Any], update: Callable[[dict[str, Any]], None]) -> None:
    root = project_dir / "audio" / "finetune" / job["dataset_name"]
    manifest_path = root / "manifest.json"
    try:
        update({"status": "running", "started_at": utc_now()})
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        texts = [sample["text"] for sample in manifest["samples"]]
        converted = _convert_texts(texts)
        prepared = root / "prepared"
        prepared.mkdir(parents=True, exist_ok=False)
        raw_path = prepared / "raw.arrow"
        durations: list[float] = []
        with ArrowWriter(path=str(raw_path)) as writer:
            for sample, text in zip(manifest["samples"], converted):
                duration = float(sample["duration"])
                durations.append(duration)
                writer.write({"audio_path": str(root / "input" / "wavs" / sample["filename"]), "text": text, "duration": duration})
            writer.finalize()
        (prepared / "duration.json").write_text(json.dumps({"duration": durations}) + "\n", encoding="utf-8")
        vocab_source = _models_root() / job["base_model"] / "vocab.txt"
        if not vocab_source.is_file():
            vocab_source = _suite_root() / "engines" / "f5_tts" / "data" / "Emilia_ZH_EN_pinyin" / "vocab.txt"
        if not vocab_source.is_file():
            raise F5DatasetError("No compatible F5 vocabulary file is installed")
        shutil.copy2(vocab_source, prepared / "vocab.txt")
        checkpoint = _checkpoint(job["base_model"])
        command = [
            sys.executable, "-m", "engines.f5_tts.train.finetune_cli",
            "--exp_name", job["base_model"], "--dataset_name", job["dataset_name"],
            "--finetune", "--pretrain", str(checkpoint), "--logger", "tensorboard",
        ]
        update({
            "status": "completed", "completed_at": utc_now(),
            "artifacts": {"raw_arrow": str(raw_path), "duration_json": str(prepared / "duration.json"), "vocab": str(prepared / "vocab.txt")},
            "command_preview": command,
            "command_blockers": [
                "Training is intentionally disabled until the dataset and exact command are approved.",
                "The prepared dataset must be staged where the installed F5 loader resolves dataset_name.",
                "The current host cached_path import must be repaired before training.",
            ],
        })
    except Exception as exc:
        update({"status": "failed", "completed_at": utc_now(), "error": str(exc)})


def new_prepare_job(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": f"f5prep-{uuid.uuid4().hex[:12]}", "kind": "f5_prepare", "status": "queued",
        "created_at": utc_now(), "dataset_name": manifest["dataset_name"], "base_model": manifest["base_model"],
        "validation": {key: manifest[key] for key in ("sample_count", "total_duration", "sample_rates", "samples")},
        "artifacts": {}, "command_preview": None, "command_blockers": [], "error": None,
    }
