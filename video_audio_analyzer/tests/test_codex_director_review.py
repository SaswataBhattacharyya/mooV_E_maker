from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_audio_analyzer.codex_director_review import (
    DirectorReviewError,
    apply_director_overlay,
    review_manifest,
    review_payload,
    validate_decisions,
)


def sample_manifest() -> dict:
    return {
        "run_id": "run-one",
        "source": {"video_id": "video-one"},
        "statuses": {"director_confirmation": "pending_codex_director_integration"},
        "transcript": {"segments": [{"start_time_sec": 1.0, "end_time_sec": 2.0, "text": "Hello there."}]},
        "character_tracking": {"tracks": [{"track_id": "face-1", "start_time_sec": 0.0,
            "end_time_sec": 3.0, "identity_scope": "within_video_track_only"}]},
        "speaker_character_associations": [{"speaker_id": "speaker-1", "start_time_sec": 1.0,
            "end_time_sec": 2.0, "candidate_track_id": "face-1", "candidate_tracks": [
                {"track_id": "face-1", "overlap_sec": 1.0, "active_speaker_score": 0.95}],
            "identity_merge_allowed": False}],
        "voices": {"examples": [{"speaker_id": "speaker-1", "transcript": "Hello there.",
            "voice_identity": {"voice_identity_id": "voice-1", "character_id": "character-1",
                "display_name": "Character-ABCD"}, "voice_candidates": {"scope_used": "global", "candidates": []}}]},
        "provenance": {},
    }


def test_codex_review_persists_scoped_association_without_identity_merge(tmp_path: Path):
    manifest_path = tmp_path / "run" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(sample_manifest()), encoding="utf-8")

    def fake_codex(prompt: str) -> dict:
        assert "untrusted data" in prompt
        return {"speaker_track_decisions": [{"association_index": 0, "decision": "confirm_track",
            "track_id": "face-1", "confidence": 0.91, "evidence_codes": ["temporal_overlap", "active_speaker_score"]}],
            "voice_identity_decisions": []}

    review_root = tmp_path / "reviews"
    result = review_manifest(manifest_path, tmp_path / "voice-store", review_root=review_root, reviewer=fake_codex)
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated = apply_director_overlay(original, review_root)
    assert result["status"] == "completed"
    assert updated["speaker_character_associations"][0]["association_state"] == "codex_confirmed_within_video_track"
    assert updated["speaker_character_associations"][0]["character_id"] == "character-1"
    assert updated["speaker_character_associations"][0]["identity_merge_allowed"] is False
    assert updated["character_tracking"]["tracks"][0]["display_name"] == "Character-ABCD"
    audit = (review_root / "run-one.jsonl").read_text(encoding="utf-8")
    assert '"provider": "codex"' in audit


def test_codex_cannot_confirm_voice_match_using_similarity_only():
    manifest = sample_manifest()
    manifest["voices"]["examples"][0]["voice_candidates"]["candidates"] = [{
        "voice_identity_id": "voice-prior", "similarity": 0.99,
        "embedding_model": "ecapa", "embedding_version": "v1",
    }]
    review = review_payload(manifest)
    candidate = review["voice_identity_reviews"][0]
    payload = {"speaker_track_decisions": [{"association_index": 0, "decision": "keep_anonymous",
        "track_id": None, "confidence": 0.8}], "voice_identity_decisions": [{
        "voice_identity_id": "voice-1", "candidate_voice_identity_id": "voice-prior",
        "decision": "confirm_match", "confidence": 0.99}]}
    assert not candidate["independent_identity_evidence_present"]
    with pytest.raises(DirectorReviewError, match="independent trusted identity evidence"):
        validate_decisions(payload, review)


def test_codex_cannot_substitute_an_unprovided_face_track():
    review = review_payload(sample_manifest())
    with pytest.raises(DirectorReviewError, match="not supplied as the candidate"):
        validate_decisions({"speaker_track_decisions": [{"association_index": 0, "decision": "confirm_track",
            "track_id": "invented-track", "confidence": 1.0}], "voice_identity_decisions": []}, review)


def test_weak_codex_face_link_remains_anonymous():
    review = review_payload(sample_manifest())
    decisions = validate_decisions({"speaker_track_decisions": [{"association_index": 0,
        "decision": "confirm_track", "track_id": "face-1", "confidence": 0.65,
        "evidence_codes": ["temporal_overlap"]}], "voice_identity_decisions": []}, review)
    assert decisions["speaker_track_decisions"][0]["decision"] == "keep_anonymous"
    assert decisions["speaker_track_decisions"][0]["track_id"] is None
    assert "below_auto_link_confidence_floor" in decisions["speaker_track_decisions"][0]["evidence_codes"]
