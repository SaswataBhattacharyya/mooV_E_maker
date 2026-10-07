from video_audio_analyzer.voice_embeddings import speaker_passages, transcript_for_passage


def test_voice_passages_keep_only_continuous_single_speaker_segments_at_least_30s():
    segments = [
        {"speaker_id": "spk_a", "start_time_sec": 0, "end_time_sec": 15},
        {"speaker_id": "spk_a", "start_time_sec": 17, "end_time_sec": 31},
        {"speaker_id": "spk_b", "start_time_sec": 40, "end_time_sec": 55},
        {"speaker_id": "spk_a", "start_time_sec": 70, "end_time_sec": 85},
    ]
    passages = speaker_passages(segments)
    assert passages == [{"speaker_id": "spk_a", "passage_index": 1, "start_time_sec": 0.0, "end_time_sec": 31.0}]


def test_unlabeled_transcript_is_attributed_by_diarization_overlap():
    diarization = [
        {"speaker_id": "spk_a", "start_time_sec": 0.0, "end_time_sec": 4.0},
        {"speaker_id": "spk_b", "start_time_sec": 4.0, "end_time_sec": 9.0},
    ]
    transcript = [
        {"start_time_sec": 1.0, "end_time_sec": 3.0, "text": "A's line"},
        {"start_time_sec": 5.0, "end_time_sec": 8.0, "text": "B's line"},
        {"start_time_sec": 1.0, "end_time_sec": 2.0, "text": "explicit B", "speaker_id": "spk_b"},
    ]
    result = transcript_for_passage(transcript, diarization, speaker_id="spk_a", start=0, end=9)
    assert [item["text"] for item in result] == ["A's line"]
