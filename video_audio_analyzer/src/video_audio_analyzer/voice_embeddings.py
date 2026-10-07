"""Project-local ECAPA identities and long, continuous voice reference clips.

Short ASR fragments are not saved as reusable voice examples. We merge adjacent
diarization intervals for the same speaker while retaining their natural gaps,
then only write clips whose continuous envelope is at least 30 seconds long.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


MIN_VOICE_REFERENCE_SECONDS = 30.0
MAX_PAUSE_TO_JOIN_SECONDS = 2.5


def speaker_passages(diarization_segments: list[dict[str, Any]], *, max_pause_sec: float = MAX_PAUSE_TO_JOIN_SECONDS) -> list[dict[str, Any]]:
    """Merge adjacent intervals only for the same diarized speaker."""
    grouped: dict[str, list[tuple[float, float]]] = {}
    for item in diarization_segments:
        speaker = str(item.get("speaker_id") or "").strip()
        if not speaker:
            continue
        try:
            start = max(0.0, float(item["start_time_sec"]))
            end = float(item["end_time_sec"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            grouped.setdefault(speaker, []).append((start, end))
    passages: list[dict[str, Any]] = []
    for speaker, intervals in grouped.items():
        intervals.sort()
        current_start, current_end = intervals[0]
        part = 1
        for start, end in intervals[1:]:
            if start - current_end <= max_pause_sec:
                current_end = max(current_end, end)
                continue
            if current_end - current_start >= MIN_VOICE_REFERENCE_SECONDS:
                passages.append({"speaker_id": speaker, "passage_index": part,
                                 "start_time_sec": current_start, "end_time_sec": current_end})
                part += 1
            current_start, current_end = start, end
        if current_end - current_start >= MIN_VOICE_REFERENCE_SECONDS:
            passages.append({"speaker_id": speaker, "passage_index": part,
                             "start_time_sec": current_start, "end_time_sec": current_end})
    return sorted(passages, key=lambda item: (item["start_time_sec"], item["speaker_id"]))


def transcript_for_passage(transcript_segments: list[dict[str, Any]], diarization_segments: list[dict[str, Any]],
                           *, speaker_id: str, start: float, end: float) -> list[dict[str, Any]]:
    """Keep timestamped transcript lines supported by the target speaker."""
    selected: list[dict[str, Any]] = []
    for item in transcript_segments:
        item_start = float(item.get("start_time_sec", 0) or 0)
        item_end = float(item.get("end_time_sec", 0) or 0)
        if min(end, item_end) <= max(start, item_start):
            continue
        labeled_speaker = str(item.get("speaker_id") or item.get("speaker") or "").strip()
        if labeled_speaker:
            if labeled_speaker == speaker_id:
                selected.append(item)
            continue
        # Whisper-style ASR may not label speakers. Attribute a line only when
        # one diarized speaker owns its greatest temporal overlap.
        overlaps: list[tuple[str, float]] = []
        for diarized_item in diarization_segments:
            other_start = float(diarized_item.get("start_time_sec", 0) or 0)
            other_end = float(diarized_item.get("end_time_sec", 0) or 0)
            amount = max(0.0, min(item_end, other_end) - max(item_start, other_start))
            if amount > 0:
                overlaps.append((str(diarized_item.get("speaker_id") or ""), amount))
        if overlaps and max(overlaps, key=lambda pair: pair[1])[0] == speaker_id:
            selected.append(item)
    return selected


def extract_voice_examples(audio_path: Path, transcript: dict[str, Any], output_dir: Path, *,
                           diarization: dict[str, Any] | None = None, store_root: Path | None = None,
                           project_id: str | None = None, video_id: str | None = None,
                           identity_scope: str = "project_only", save_audio_examples: bool = False) -> dict[str, Any]:
    model_dir = Path(os.environ.get("VIDEO_AUDIO_ANALYZER_ECAPA_MODEL", "/models/spkrec-ecapa-voxceleb"))
    result: dict[str, Any] = {"status": "unavailable", "backend": "speechbrain-ecapa", "model": "speechbrain/spkrec-ecapa-voxceleb", "examples": [], "identity_store": {"status": "not_run", "persisted_identities": 0, "director_candidates": 0}}
    if not model_dir.exists():
        result["reason"] = f"prepared ECAPA model not mounted: {model_dir}"
        return result
    try:
        import torchaudio
        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: []
        if not hasattr(torchaudio, "get_audio_backend"):
            torchaudio.get_audio_backend = lambda: None
        import huggingface_hub
        original_download = huggingface_hub.hf_hub_download
        def compatible_download(*args, **kwargs):
            kwargs.pop("use_auth_token", None)
            return original_download(*args, **kwargs)
        huggingface_hub.hf_hub_download = compatible_download
        from speechbrain.inference.speaker import EncoderClassifier
        import numpy as np
        import soundfile as sf
        import torch
        classifier = EncoderClassifier.from_hparams(source=str(model_dir), savedir="/tmp/video_audio_analyzer_ecapa_runtime")
        transcript_segments = transcript.get("segments", [])
        diarized = (diarization or {}).get("segments", [])
        if not transcript_segments:
            result["reason"] = "no timestamped transcript segments"
            return result
        output_dir.mkdir(parents=True, exist_ok=True)
        passages = speaker_passages(diarized)
        if not passages:
            result.update({"reason": "no continuous single-speaker passage reached the 30-second minimum",
                           "minimum_reference_seconds": MIN_VOICE_REFERENCE_SECONDS,
                           "eligible_passages": 0})
            return result
        examples: list[dict[str, Any]] = []
        persisted_identity_ids: set[str] = set()
        director_candidate_count = 0
        persisted_speakers: set[str] = set()
        voice_identity_by_speaker: dict[str, str] = {}
        for passage in passages:
            speaker_id = str(passage["speaker_id"])
            start, end = float(passage["start_time_sec"]), float(passage["end_time_sec"])
            audio, sample_rate = sf.read(str(audio_path), start=int(start * 16000), stop=max(int(start * 16000) + 1, int(end * 16000)), dtype="float32")
            if getattr(audio, "ndim", 1) > 1:
                audio = np.mean(audio, axis=1)
            if len(audio) < int(MIN_VOICE_REFERENCE_SECONDS * sample_rate):
                continue
            # Compute a stable centroid from bounded 10-second windows to avoid
            # feeding long movie passages to the encoder as one huge tensor.
            vectors: list[list[float]] = []
            chunk_samples = max(1, int(10 * sample_rate))
            for offset in range(0, len(audio), chunk_samples):
                chunk = np.asarray(audio[offset:offset + chunk_samples], dtype="float32")
                if len(chunk) < int(1.0 * sample_rate):
                    continue
                signal = torch.from_numpy(chunk).unsqueeze(0)
                vector = classifier.encode_batch(signal).squeeze().detach().cpu().tolist()
                vectors.append([float(value) for value in vector])
            if not vectors:
                continue
            centroid = np.mean(np.asarray(vectors, dtype="float32"), axis=0)
            norm = float(np.linalg.norm(centroid))
            if norm:
                centroid = centroid / norm
            embedding = centroid.tolist()
            passage_transcript = transcript_for_passage(transcript_segments, diarized,
                speaker_id=speaker_id, start=start, end=end)
            transcript_text = " ".join(str(item.get("text", "")).strip() for item in passage_transcript if item.get("text")).strip()
            filename_base = f"voice_{speaker_id}_{int(passage['passage_index']):03d}"
            path = output_dir / f"{filename_base}.json"
            record = {"voice_example_id": path.stem, "start_time_sec": start, "end_time_sec": end,
                "duration_sec": round(end - start, 3), "transcript": transcript_text,
                "transcript_segments": passage_transcript,
                "embedding_model": "speechbrain/spkrec-ecapa-voxceleb",
                "embedding_version": "speechbrain-1.0.3-ecapa-voxceleb-v1",
                "embedding": embedding, "speaker_id": speaker_id,
                "identity_scope": "project_only", "identity_status": "diarized_continuous_passage",
                "minimum_reference_seconds": MIN_VOICE_REFERENCE_SECONDS}
            if save_audio_examples:
                audio_path_out = output_dir / f"{filename_base}.wav"
                sf.write(str(audio_path_out), np.asarray(audio, dtype="float32"), int(sample_rate), subtype="PCM_16")
                record["audio_path"] = str(audio_path_out)
            if store_root:
                # The Voice Store is partitioned by this project. No other
                # project's candidates are queried or merged here.
                if speaker_id not in persisted_speakers:
                    from .voice_store import VoiceStore
                    store = VoiceStore(store_root)
                    voice_candidates = store.candidates(embedding, project_id or video_id or "unassigned",
                                                        top_k=8, scope="project_only")
                    candidates = [candidate for candidate in voice_candidates.get("candidates", [])
                        if not (candidate.get("source_video_id") == (video_id or "unknown")
                            and candidate.get("speaker_id") == speaker_id)]
                    voice_candidates["candidates"] = candidates
                    record["voice_candidates"] = voice_candidates
                    director_candidate_count += len(candidates)
                    record["voice_identity"] = store.add_identity(project_id=project_id or video_id or "unassigned",
                        video_id=video_id or "unknown", speaker_id=speaker_id, embedding=embedding,
                        start_time_sec=start, end_time_sec=end, evidence={"transcript": transcript_text,
                        "diarization_backend": (diarization or {}).get("backend"), "duration_sec": round(end - start, 3)})
                    record["identity_merge_state"] = "pending_director_review" if candidates else "project_local_identity"
                    voice_identity_by_speaker[speaker_id] = record["voice_identity"]["voice_identity_id"]
                    persisted_identity_ids.add(record["voice_identity"]["voice_identity_id"])
                elif speaker_id in voice_identity_by_speaker:
                    record["voice_identity_id"] = voice_identity_by_speaker[speaker_id]
            path.write_text(__import__("json").dumps(record, indent=2), encoding="utf-8")
            examples.append(record)
            persisted_speakers.add(speaker_id)
        identity_status = "completed" if persisted_identity_ids else "not_run_no_diarized_speakers"
        result.update({"status": "completed" if examples else "unavailable", "reason": None if examples else "no eligible voice passages",
            "minimum_reference_seconds": MIN_VOICE_REFERENCE_SECONDS,
            "eligible_passages": len(passages), "dimension": len(examples[0]["embedding"]) if examples else None, "examples": examples,
            "identity_store": {"status": identity_status, "backend": "LanceDB ANN" if os.environ.get("VIDEO_AUDIO_ANALYZER_VOICE_STORE_ENABLE_LANCEDB") == "1" else "JSONL identity-centroid fallback", "persisted_identities": len(persisted_identity_ids), "director_candidates": director_candidate_count}})
    except Exception as exc:
        result["reason"] = str(exc)
    return result
