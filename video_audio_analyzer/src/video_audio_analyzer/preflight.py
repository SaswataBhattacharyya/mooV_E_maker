from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
import os


REGISTRY: list[dict[str, str]] = [
    {"component": "FFmpeg", "purpose": "media decoding/audio extraction", "repository": "FFmpeg/FFmpeg", "model": "system"},
    {"component": "PE-AV", "purpose": "primary multimodal retrieval", "repository": "facebookresearch/perception_models", "model": "facebook/pe-av-base"},
    {"component": "CLAP", "purpose": "audio-text fallback/reranker", "repository": "LAION-AI/CLAP", "model": "repository-documented checkpoint"},
    {"component": "HTS-AT", "purpose": "sound-event detection", "repository": "RetroCirce/HTS-Audio-Transformer", "model": "repository-documented checkpoint"},
    {"component": "PANNs", "purpose": "sound-event fallback", "repository": "qiuqiangkong/panns_inference", "model": "repository-documented checkpoint"},
    {"component": "WhisperX", "purpose": "ASR/alignment", "repository": "m-bain/whisperX", "model": "Systran/faster-whisper-large-v3"},
    {"component": "NeMo", "purpose": "default speaker diarization", "repository": "NVIDIA-NeMo/Speech", "model": "local clustering diarizer"},
    {"component": "ECAPA", "purpose": "persistent speaker identity", "repository": "speechbrain/speechbrain", "model": "speechbrain/spkrec-ecapa-voxceleb"},
    {"component": "Demucs", "purpose": "source separation", "repository": "adefossez/demucs", "model": "AUTO/htdemucs"},
    {"component": "SAM Audio", "purpose": "lazy arbitrary sound isolation", "repository": "facebookresearch/sam-audio", "model": "facebook/sam-audio-large-tv"},
    {"component": "Essentia/librosa", "purpose": "measurable music/audio features", "repository": "MTG/essentia; librosa/librosa", "model": "package"},
    {"component": "InsightFace", "purpose": "face identity", "repository": "deepinsight/insightface", "model": "license-preflight-required"},
    {"component": "ByteTrack", "purpose": "geometry tracking", "repository": "FoundationVision/ByteTrack", "model": "selected release"},
    {"component": "BoxMOT", "purpose": "appearance ReID", "repository": "mikel-brostrom/boxmot", "model": "BoT-SORT/StrongSORT backend"},
    {"component": "MMPose", "purpose": "pose evidence", "repository": "open-mmlab/mmpose", "model": "selected compatible model"},
    {"component": "TalkNet", "purpose": "active speaker", "repository": "TaoRuijie/TalkNet-ASD", "model": "TalkSet pretrained checkpoint"},
]


def _module_status(name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(name)
    return {"module": name, "available": spec is not None}


def run_preflight(root: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    ollama = None
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            ollama = {"available": response.status == 200}
    except Exception as exc:
        ollama = {"available": False, "reason": str(exc)}

    modules = [_module_status(name) for name in ("cv2", "numpy", "yaml", "librosa", "soundfile", "torch", "transformers", "faster_whisper", "lancedb", "scenedetect")]
    asr_model = Path(__import__("os").environ.get("VIDEO_AUDIO_ANALYZER_ASR_MODEL", str(root / "models" / "faster-whisper-large-v3")))
    def model_record(component: str, model: str, env: str, module: str, default: str = "") -> dict[str, Any]:
        path = Path(os.environ.get(env, default)).expanduser() if (os.environ.get(env) or default) else None
        checkpoint_present = bool(path and path.exists() and (path.is_file() or any(path.iterdir())))
        return {"component": component, "model": model, "module_available": importlib.util.find_spec(module) is not None,
                "checkpoint_path": str(path) if path else None, "checkpoint_present": checkpoint_present,
                "authentication_configured": bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")) if component == "SAM Audio" else None,
                "download_on_preflight": False}
    peav_path = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", str(root / "models" / "pe-av-base")))
    talknet_health: dict[str, Any] = {"available": False, "reason": "isolated TalkNet worker URL is not configured"}
    talknet_url = os.environ.get("VIDEO_AUDIO_ANALYZER_TALKNET_URL", "http://127.0.0.1:8032")
    if talknet_url:
        try:
            import urllib.request
            with urllib.request.urlopen(talknet_url.rstrip("/") + "/health", timeout=3) as response:
                talknet_health = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            talknet_health = {"available": False, "reason": str(exc), "url": talknet_url}
    sam_health: dict[str, Any] = {"available": False, "reason": "isolated SAM Audio worker URL is not configured"}
    sam_url = os.environ.get("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL", "http://127.0.0.1:8033")
    if sam_url:
        try:
            import urllib.request
            with urllib.request.urlopen(sam_url.rstrip("/") + "/health", timeout=3) as response:
                sam_health = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            sam_health = {"available": False, "reason": str(exc), "url": sam_url}
    peav_worker_url = os.environ.get("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "http://127.0.0.1:8034")
    try:
        import urllib.request
        with urllib.request.urlopen(peav_worker_url.rstrip("/") + "/health", timeout=3) as response:
            peav_worker_health: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            peav_worker_health["available"] = bool(peav_worker_health.get("ok"))
    except Exception as exc:
        peav_worker_health = {"available": False, "reason": str(exc), "url": peav_worker_url}
    try:
        from transformers import PeAudioVideoModel, PeAudioVideoProcessor  # type: ignore[attr-defined]
        local_peav_module_available = PeAudioVideoModel is not None and PeAudioVideoProcessor is not None
    except Exception:
        local_peav_module_available = False
    audio_worker_url = os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL", "http://127.0.0.1:8031")
    try:
        import urllib.request
        with urllib.request.urlopen(audio_worker_url.rstrip("/") + "/health", timeout=3) as response:
            audio_worker_health: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            audio_worker_health["available"] = bool(audio_worker_health.get("ok"))
    except Exception as exc:
        audio_worker_health = {"available": False, "reason": str(exc), "url": audio_worker_url}
    report: dict[str, Any] = {
        "analyzer_version": "0.1.0",
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "ffmpeg": {"available": bool(ffmpeg), "path": ffmpeg},
        "ffprobe": {"available": bool(ffprobe), "path": ffprobe},
        "ollama": ollama,
        "asr": {"backend": "faster-whisper", "model": "Systran/faster-whisper-large-v3", "checkpoint_path": str(asr_model), "checkpoint_present": asr_model.exists(), "download_on_preflight": False},
        "modules": modules,
        "registry": REGISTRY,
        "components": {
            "HTS-AT": model_record("HTS-AT", "HTSAT_AudioSet_Saved_1.ckpt", "VIDEO_AUDIO_ANALYZER_HTSAT_CHECKPOINT", "torch", str(root / "models" / "HTSAT_AudioSet_Saved_1.ckpt")),
            "PANNs": model_record("PANNs", "Cnn14_DecisionLevelMax_mAP=0.385", "VIDEO_AUDIO_ANALYZER_PANNS_CHECKPOINT", "panns_inference", str(root / "models" / "panns" / "Cnn14_DecisionLevelMax_mAP=0.385.pth")),
            "NeMo": {**model_record("NeMo", "NVIDIA-NeMo/Speech clustering", "VIDEO_AUDIO_ANALYZER_NEMO_SPEAKER_MODEL", "nemo", ""),
                     "vad_checkpoint": os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_VAD_MODEL"),
                     "vad_checkpoint_present": bool(os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_VAD_MODEL") and Path(os.environ["VIDEO_AUDIO_ANALYZER_NEMO_VAD_MODEL"]).is_file())},
            "ECAPA": model_record("ECAPA", "speechbrain/spkrec-ecapa-voxceleb", "VIDEO_AUDIO_ANALYZER_ECAPA_MODEL", "speechbrain", str(root / "models" / "spkrec-ecapa-voxceleb")),
            "CLAP": {**model_record("CLAP", "LAION-AI/CLAP", "VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", "laion_clap", ""),
                "worker_url": audio_worker_url, "worker": audio_worker_health},
            "PE-AV": {"component": "PE-AV", "model": "facebook/pe-av-base", "checkpoint_path": str(peav_path), "checkpoint_present": (peav_path / "config.json").is_file() and (peav_path / "model.safetensors").is_file(), "module_available": local_peav_module_available, "worker_url": peav_worker_url, "worker": peav_worker_health},
            "SAM Audio": {**model_record("SAM Audio", "facebook/sam-audio-large-tv", "VIDEO_AUDIO_ANALYZER_SAM_AUDIO_PATH", "sam_audio", str(root / "models" / "sam-audio-large-tv")),
                "worker": sam_health, "checkpoint_present": bool(sam_health.get("checkpoint_present")),
                "checkpoint_filename": "sam-audio-large-tv_checkpoint.pt",
                "auxiliary_models": {"t5": {"model": "google-t5/t5-base", "path": str(root / "models" / "sam-audio-t5-base"),
                    "checkpoint_present": (root / "models" / "sam-audio-t5-base" / "config.json").is_file() and
                        any((root / "models" / "sam-audio-t5-base" / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")) and
                        any((root / "models" / "sam-audio-t5-base" / name).is_file() for name in ("spiece.model", "tokenizer.json"))}},
                "license": "SAM License; model gated on Hugging Face; review official terms"},
            "active_speaker": {"component": "TalkNet", "repository": "TaoRuijie/TalkNet-ASD", "worker": talknet_health,
                "checkpoint_path": "/models/talknet/pretrain_TalkSet.model", "checkpoint_present": bool(talknet_health.get("checkpoint_present")),
                "face_checkpoint_path": "/models/talknet/sfd_face.pth", "face_checkpoint_present": bool(talknet_health.get("face_checkpoint_present")),
                "code_license": "MIT", "checkpoint_license": "not independently stated by checkpoint host; review before redistribution/commercial use",
                "dependency_isolation": "separate video-audio-analyzer-talknet image"},
            "face_identity": {"component": "InsightFace", "status": "license_review_required_before_model_selection", "checkpoint_present": False},
            "body_reid": {"component": "BoxMOT/BoT-SORT", "module_available": importlib.util.find_spec("boxmot") is not None, "checkpoint_path": os.environ.get("VIDEO_AUDIO_ANALYZER_REID_CHECKPOINT"), "checkpoint_present": bool(os.environ.get("VIDEO_AUDIO_ANALYZER_REID_CHECKPOINT") and Path(os.environ["VIDEO_AUDIO_ANALYZER_REID_CHECKPOINT"]).is_file())},
        },
        "voice_store": {"path": os.environ.get("VIDEO_AUDIO_ANALYZER_VOICE_STORE_PATH", str(root / "voice_store")), "project_first_then_global": True, "ann_backend": "LanceDB if installed; explicit JSONL centroid fallback otherwise", "raw_audio_cross_project_search": False},
        "director": {"provider": "Codex", "model": os.environ.get("VIDEO_AUDIO_ANALYZER_CODEX_MODEL", "gpt-6-luna"),
            "endpoint_configured": bool(os.environ.get("VIDEO_AUDIO_ANALYZER_DIRECTOR_URL")),
            "status": "ready" if os.environ.get("VIDEO_AUDIO_ANALYZER_DIRECTOR_URL") else "unavailable_no_server_side_codex_director_endpoint",
            "no_auto_merge_without_director": True},
        "gated_components": ["SAM Audio (model access approval/token)", "pyannote (optional)", "InsightFace checkpoint license review"],
        "docker_boundary": "isolated analyzer workers only; ComfyUI untouched",
    }
    # Website/worker runs keep generated state in the single shared repertoire.
    # Standalone development can still default to <root>/manifests, while the
    # integrated launcher passes VIDEO_AUDIO_ANALYZER_PREFLIGHT_PATH explicitly.
    report_path_value = os.environ.get("VIDEO_AUDIO_ANALYZER_PREFLIGHT_PATH", "").strip()
    report_path = Path(report_path_value).expanduser() if report_path_value else root / "manifests" / "preflight.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
