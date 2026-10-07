"""Official HTS-AT AudioSet checkpoint adapter (lazy, local-only)."""
from __future__ import annotations

import csv
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


class HTSATUnavailable(RuntimeError):
    pass


def _as_probabilities(values: Any) -> Any:
    """Normalize HTS-AT outputs without double-sigmoiding probabilities."""
    import numpy as np
    values = np.asarray(values, dtype="float32")
    if values.size and (float(values.min()) < 0.0 or float(values.max()) > 1.0):
        # Stable sigmoid for checkpoints/branches that expose logits.
        values = 1.0 / (1.0 + np.exp(-np.clip(values, -80.0, 80.0)))
    return values


@lru_cache(maxsize=1)
def _load():
    checkpoint = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_HTSAT_CHECKPOINT", ""))
    if not checkpoint.is_file():
        raise HTSATUnavailable("official HTSAT_AudioSet_Saved_1.ckpt is not prepared")
    repo_override = os.environ.get("VIDEO_AUDIO_ANALYZER_HTSAT_REPO")
    candidates = [Path(repo_override).expanduser()] if repo_override else []
    analyzer_root = Path(__file__).resolve().parents[2]
    candidates.extend([
        analyzer_root / "vendor" / "HTS-Audio-Transformer",
        analyzer_root / "project" / "video_audio_analyzer" / "vendor" / "HTS-Audio-Transformer",
    ])
    repo = next((path for path in candidates if (path / "model" / "htsat.py").is_file()), None)
    if repo is None:
        raise HTSATUnavailable("official RetroCirce/HTS-Audio-Transformer source checkout was not found in mounted analyzer paths")
    sys.path.insert(0, str(repo))
    try:
        import torch
        # htsat.py imports two inference helpers from a large training-only
        # utilities module. Provide just those helpers, avoiding training deps.
        import types
        utility = types.ModuleType("utils")
        utility.do_mixup = lambda x, _mix: x
        def interpolate_time(x, ratio):
            # Match the official repository's [batch, time, classes] repeat
            # interpolation. Generic torch.nn.functional.interpolate treats
            # time as channels here and silently corrupts the SED class axis.
            batch, steps, classes = x.shape
            return x[:, :, None, :].repeat(1, 1, int(ratio), 1).reshape(batch, steps * int(ratio), classes)
        utility.interpolate = interpolate_time
        sys.modules["utils"] = utility
        import config
        from model.htsat import HTSAT_Swin_Transformer
        model = HTSAT_Swin_Transformer(spec_size=config.htsat_spec_size, patch_size=config.htsat_patch_size,
            in_chans=1, num_classes=config.classes_num, window_size=config.htsat_window_size, config=config,
            depths=config.htsat_depth, embed_dim=config.htsat_dim, patch_stride=config.htsat_stride,
            num_heads=config.htsat_num_head)
        raw = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
        state = raw.get("state_dict", raw)
        state = {key.removeprefix("sed_model."): value for key, value in state.items()}
        model.load_state_dict(state, strict=False)
        device = os.environ.get("VIDEO_AUDIO_ANALYZER_HTSAT_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        model.to(device).eval()
        labels = {}
        with (repo / "class_label_indice.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                labels[int(row["index"])] = row["display_name"]
        return torch, model, labels, device
    except Exception as exc:
        raise HTSATUnavailable(f"HTS-AT runtime/checkpoint load failed: {exc}") from exc


def detect(wav_path: str | Path, *, detect_speech: bool = True, detect_music: bool = True,
           detect_sfx: bool = True, threshold: float | None = None, window_sec: float = 10.0,
           stride_sec: float = 5.0, minimum_event_sec: float = 0.25) -> list[dict[str, Any]]:
    try:
        import librosa
        import numpy as np
        torch, model, labels, device = _load()
        threshold = float(threshold if threshold is not None else os.environ.get("VIDEO_AUDIO_ANALYZER_HTSAT_THRESHOLD", "0.35"))
        audio, sample_rate = librosa.load(str(wav_path), sr=32000, mono=True)
        duration = len(audio) / sample_rate
        rows: list[dict[str, Any]] = []
        start = 0.0
        while start < duration:
            end = min(duration, start + window_sec)
            crop = audio[int(start * sample_rate):int(end * sample_rate)]
            if crop.size == 0:
                break
            expected = int(window_sec * sample_rate)
            crop = np.pad(crop, (0, max(0, expected - len(crop))))[:expected].astype("float32")
            with torch.inference_mode():
                output = model(torch.from_numpy(crop).unsqueeze(0).to(device), None, True)
                # The official HTS-AT forward path returns sigmoid probabilities
                # in evaluation mode (and logits in one optional branch). A
                # second sigmoid compresses values into ~0.5 and creates
                # hundreds of false-positive AudioSet labels. Only transform
                # values that are clearly outside probability range.
                clip_scores = output["clipwise_output"][0].detach().float().cpu().numpy()
                clip_probabilities = _as_probabilities(clip_scores)
                frame_scores = output.get("framewise_output")
                if frame_scores is not None:
                    frame_scores = frame_scores[0].detach().float().cpu().numpy()
                    frame_probabilities = _as_probabilities(frame_scores)
                    # The canonical repository has emitted both [T,C] and
                    # [C,T] depending on the inference branch/config.
                    if frame_probabilities.ndim == 2 and frame_probabilities.shape[-1] != len(clip_probabilities) and frame_probabilities.shape[0] == len(clip_probabilities):
                        frame_probabilities = frame_probabilities.T
                    if frame_probabilities.ndim != 2 or frame_probabilities.shape[-1] != len(clip_probabilities):
                        frame_probabilities = None
                else:
                    frame_probabilities = None
            # The repository's framewise SED head is temporally localized; use
            # it instead of assigning every class to an entire 10-second clip.
            # The clipwise output remains a fallback for checkpoints without
            # framewise scores.
            frame_count = int(frame_probabilities.shape[0]) if frame_probabilities is not None else 0
            local_duration = min(window_sec, duration - start)
            for idx in range(len(clip_probabilities)):
                label = labels.get(int(idx), f"class_{idx}")
                folded = label.lower()
                is_speech = any(key in folded for key in ("speech", "speaking", "conversation", "narration", "shout"))
                is_music = "music" in folded or "musical instrument" in folded or "singing" in folded
                enabled = (detect_speech if is_speech else False) or (detect_music if is_music else False) or (detect_sfx if not is_speech and not is_music else False)
                if not enabled:
                    continue
                if frame_count:
                    active = frame_probabilities[:, idx] >= threshold
                    changes = np.diff(np.pad(active.astype("int8"), (1, 1)))
                    spans = zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1))
                    intervals = []
                    for left, right in spans:
                        event_start = start + local_duration * float(left) / frame_count
                        event_end = min(start + local_duration, start + local_duration * float(right) / frame_count)
                        if event_end - event_start >= minimum_event_sec:
                            confidence = float(frame_probabilities[left:right, idx].mean())
                            intervals.append((event_start, event_end, confidence))
                else:
                    score = float(clip_probabilities[idx])
                    intervals = [(start, start + local_duration, score)] if score >= threshold else []
                for event_start, event_end, score in intervals:
                    rows.append({"event_id": f"htsat_{len(rows)+1:05d}", "start_time_sec": round(event_start, 3),
                        "end_time_sec": round(event_end, 3), "label": label, "confidence": round(score, 6),
                        "event_type": "speech" if is_speech else "music" if is_music else "sfx_ambience",
                        "detector": "HTS-AT", "model": "HTSAT_AudioSet_Saved_1.ckpt", "temporal_resolution_sec": round(local_duration / max(1, frame_count), 3) if frame_count else local_duration})
            start += stride_sec
        # Coalesce overlapping sliding windows without hiding detector uncertainty.
        compact: list[dict[str, Any]] = []
        for event in sorted(rows, key=lambda row: (row["label"], row["start_time_sec"])):
            prev = compact[-1] if compact else None
            if prev and prev["label"] == event["label"] and event["start_time_sec"] <= prev["end_time_sec"]:
                prev["end_time_sec"] = max(prev["end_time_sec"], event["end_time_sec"])
                prev["confidence"] = max(prev["confidence"], event["confidence"])
            else:
                compact.append(dict(event))
        for index, event in enumerate(compact, 1): event["event_id"] = f"htsat_{index:05d}"
        return compact
    except HTSATUnavailable:
        raise
    except Exception as exc:
        raise HTSATUnavailable(f"HTS-AT event detection failed: {exc}") from exc
