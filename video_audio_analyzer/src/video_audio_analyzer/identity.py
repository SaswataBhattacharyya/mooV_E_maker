"""Evidence-only speaker/visible-person association utilities."""
from __future__ import annotations

from typing import Any


def associate_speakers(diarization: list[dict[str, Any]], tracks: list[dict[str, Any]],
                       active_speaker_scores: list[dict[str, Any]], threshold: float = 0.6) -> list[dict[str, Any]]:
    """Join on temporal overlap and explicit ASD scores; visibility alone is insufficient."""
    output: list[dict[str, Any]] = []
    for utterance in diarization:
        start, end = float(utterance["start_time_sec"]), float(utterance["end_time_sec"])
        candidates: list[dict[str, Any]] = []
        for track in tracks:
            overlap = max(0.0, min(end, float(track.get("end_time_sec", 0))) - max(start, float(track.get("start_time_sec", 0))))
            if overlap <= 0:
                continue
            scores = [float(row.get("score", 0)) for row in active_speaker_scores
                      if row.get("track_id") == track.get("track_id")
                      and float(row.get("timestamp_sec", -1)) >= start and float(row.get("timestamp_sec", -1)) <= end]
            candidates.append({"track_id": track.get("track_id"), "overlap_sec": overlap,
                               "active_speaker_score": max(scores) if scores else None,
                               "face_evidence": track.get("face_evidence"), "body_reid_evidence": track.get("body_reid_evidence")})
        candidates.sort(key=lambda row: (row["active_speaker_score"] or -1, row["overlap_sec"]), reverse=True)
        winner = candidates[0] if candidates and (candidates[0]["active_speaker_score"] or 0.0) >= threshold else None
        output.append({"speaker_id": utterance.get("speaker_id"), "start_time_sec": start, "end_time_sec": end,
                       "candidate_tracks": candidates, "candidate_track_id": winner["track_id"] if winner else None,
                       "association_state": "candidate_needs_director_confirmation" if winner else "anonymous_unassociated",
                       "identity_merge_allowed": False,
                       "reason": "requires Codex director review of multimodal evidence" if winner else "no explicit active-speaker evidence"})
    return output
