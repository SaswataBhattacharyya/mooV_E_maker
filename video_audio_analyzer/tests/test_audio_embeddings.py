from pathlib import Path

from video_audio_analyzer import peav_adapter, pipeline, retrieval


class _FakeAdapter:
    dimension = 2

    def embed(self, *, video=None, audio=None, text=None):
        if text:
            return {"text_audio_video_embeds": [[0.0, 1.0]]}
        return {"audio_embeds": [[1.0, 0.0]]}


def test_audio_events_get_independent_peav_vectors_and_relative_music_mood(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", "/prepared/checkpoint")
    monkeypatch.setattr(peav_adapter, "configured_adapter", lambda: _FakeAdapter())
    monkeypatch.setattr(pipeline, "_run", lambda _args: None)
    events = [{"event_id": "music_1", "start_time_sec": 0.0, "end_time_sec": 2.0,
        "label": "Music", "event_type": "music", "confidence": 0.8}]
    result = pipeline._run_peav_embeddings(Path("unused.mp4"), {"analysis_wav": "/tmp/source.wav"},
        [], events, tmp_path, create_av=False, create_audio=True)

    assert result["status"] == "completed"
    assert result["audio_events"] == 1
    assert events[0]["embeddings"]["audio"] == [1.0, 0.0]
    assert events[0]["semantic_mood"]["top_match"] == "joyful"
    assert events[0]["semantic_mood"]["scores_are_calibrated_probabilities"] is False
    row = next(item for item in retrieval._records({"source": {"video_id": "v1", "file_name": "clip.mp4"},
        "audio_events": events, "scenes": []}) if item["kind"] == "audio_event")
    assert row["pe_av_vector"] == [1.0, 0.0]
    assert row["embedding_modality"] == "audio"
    assert "estimated music mood: joyful" in row["text"]
