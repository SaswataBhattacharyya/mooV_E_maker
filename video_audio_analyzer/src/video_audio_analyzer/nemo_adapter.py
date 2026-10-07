"""Local NeMo clustering diarization adapter with offline-only checkpoints."""
from __future__ import annotations

import json
import os
import requests
from pathlib import Path
from typing import Any


class NeMoUnavailable(RuntimeError):
    pass


def diarize(audio_path: Path, output_dir: Path) -> dict[str, Any]:
    remote = os.environ.get("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL")
    if remote:
        try:
            with audio_path.open("rb") as handle:
                response = requests.post(remote.rstrip("/") + "/api/diarize", files={"audio": (audio_path.name, handle, "audio/wav")}, timeout=3600)
            response.raise_for_status()
            result = response.json()
            rttm_text = result.pop("rttm_text", None)
            if result.get("status") == "completed" and rttm_text:
                rttm_path = output_dir / "pred_rttms" / f"{audio_path.stem}.rttm"
                rttm_path.parent.mkdir(parents=True, exist_ok=True)
                rttm_path.write_text(rttm_text, encoding="utf-8")
                result["rttm_path"] = str(rttm_path)
            return result
        except Exception as exc:
            return {"backend": "nemo-clustering", "model": "NVIDIA-NeMo/Speech", "status": "error", "segments": [], "reason": f"isolated audio worker request failed: {exc}"}
    vad = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_VAD_MODEL", ""))
    speaker = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_SPEAKER_MODEL", ""))
    base = {"backend": "nemo-clustering", "model": "NVIDIA-NeMo/Speech", "status": "unavailable",
            "speaker_model": "TitaNet", "vad_model": "MarbleNet", "segments": [], "offline_only": True}
    if not vad.is_file() or not speaker.is_file():
        base["reason"] = "local MarbleNet VAD and TitaNet .nemo checkpoints are required; downloads are never started by a job"
        return base
    try:
        import nemo.collections.asr.models as asr_models
        from omegaconf import OmegaConf
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "nemo_input.jsonl"
        manifest_path.write_text(json.dumps({"audio_filepath": str(audio_path), "offset": 0.0,
                                             "duration": None, "label": "infer", "text": "", "num": 0}) + "\n", encoding="utf-8")
        # Explicit model paths prevent NeMo from silently downloading a model.
        config = OmegaConf.create({
            "name": "ClusteringDiarizer", "verbose": False, "num_workers": 0, "sample_rate": 16000,
            "batch_size": 1, "device": os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_DEVICE", "cuda"),
            "diarizer": {"manifest_filepath": str(manifest_path), "out_dir": str(output_dir),
                "oracle_vad": False, "collar": 0.25, "ignore_overlap": True,
                "vad": {"model_path": str(vad), "external_vad_manifest": None,
                    "parameters": {"window_length_in_sec": 0.63, "shift_length_in_sec": 0.01,
                                   "smoothing": False, "overlap": 0.875, "onset": 0.5,
                                   "offset": 0.3, "pad_onset": 0.2, "pad_offset": 0.2,
                                   "min_duration_on": 0.1, "min_duration_off": 0.1,
                                   "filter_speech_first": True}},
                "speaker_embeddings": {"model_path": str(speaker), "parameters": {"window_length_in_sec": [1.5, 1.25, 1.0, 0.75, 0.5],
                    "shift_length_in_sec": [0.75, 0.625, 0.5, 0.375, 0.25], "multiscale_weights": [1, 1, 1, 1, 1],
                    "save_embeddings": False}},
                "clustering": {"parameters": {"oracle_num_speakers": False, "max_num_speakers": int(os.environ.get("VIDEO_AUDIO_ANALYZER_NEMO_MAX_SPEAKERS", "20")),
                    "enhanced_count_thres": 80, "max_rp_threshold": 0.25, "sparse_search_volume": 30,
                    "maj_vote_spk_count": False, "cuda": True}},
                "asr": {"parameters": {"asr_based_vad": False, "asr_based_vad_threshold": 1.0}},
            },
        })
        diarizer = asr_models.ClusteringDiarizer(cfg=config)
        diarizer.diarize()
        predictions = sorted(output_dir.rglob("pred_rttms/*.rttm")) + sorted(output_dir.rglob("*.rttm"))
        rttm = next((path for path in predictions if path.is_file()), None)
        if not rttm:
            raise RuntimeError("NeMo ran but did not produce an RTTM diarization output")
        segments: list[dict[str, Any]] = []
        for line in rttm.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 8 or parts[0] != "SPEAKER":
                continue
            start, duration = float(parts[3]), float(parts[4])
            segments.append({"start_time_sec": round(start, 3), "end_time_sec": round(start + duration, 3),
                             "speaker_id": parts[7], "confidence": None, "source": "nemo_rttm"})
        base.update({"status": "completed", "segments": segments, "rttm_path": str(rttm), "speaker_count": len({s["speaker_id"] for s in segments})})
    except Exception as exc:
        base.update({"status": "error", "reason": f"NeMo clustering diarization failed: {exc}"})
    return base
