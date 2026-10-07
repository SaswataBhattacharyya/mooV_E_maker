from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_audio_analyzer import clap_adapter
from video_audio_analyzer import retrieval
from video_audio_analyzer.retrieval import build_index, search


def test_index_keeps_separate_embedding_spaces(tmp_path: Path) -> None:
    manifest = {
        "source": {"video_id": "v1", "file_name": "demo.mp4"},
        "scenes": [{"scene_id": "scene_1", "frames": [{"frame_id": "f1", "timestamp_sec": 0.0, "path": "frame.jpg", "evidence": {"lighting": {"brightness_level": "bright"}, "measurements": {"orientation": "portrait"}}}]}],
        "audio_events": [{"event_id": "a1", "start_time_sec": 0, "end_time_sec": 2, "label": "audio_activity"}],
        "audio": {"preview_mp3": "preview.mp3"},
    }
    report = build_index(manifest, tmp_path)
    assert report["vector_fields"]["clap_vector"] is None
    assert report["vector_fields"]["pe_av_vector"] is None
    assert report["late_fusion"].find("concatenation") >= 0
    result = search(tmp_path / "index", "bright portrait", top_n=1, mode="keyword")
    assert result["results"]


def test_reindex_preserves_only_exact_dimension_compatible_clap_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = tmp_path / "legacy-index"
    legacy.mkdir()
    (legacy / "index_manifest.json").write_text(json.dumps({
        "clap": {"status": "completed", "dimension": 3},
        "vector_fields": {"clap_vector": 3},
    }), encoding="utf-8")
    old_rows = [
        {"record_id": "f1", "kind": "frame", "clap_vector": [0.1, 0.2, 0.3], "clap_embedding_backend": "laion_clap"},
        {"record_id": "wrong-dimension", "kind": "frame", "clap_vector": [0.1, 0.2], "clap_embedding_backend": "laion_clap"},
        {"record_id": "not-in-new-index", "kind": "audio_event", "clap_vector": [0.1, 0.2, 0.3], "clap_embedding_backend": "laion_clap"},
    ]
    (legacy / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in old_rows), encoding="utf-8")
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", raising=False)
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL", raising=False)
    manifest = {"source": {"video_id": "v1", "file_name": "demo.mp4"},
        "scenes": [{"scene_id": "scene_1", "frames": [{"frame_id": "f1", "timestamp_sec": 0, "path": "f1.jpg", "evidence": {}}]}],
        "audio_events": [{"event_id": "new-event", "start_time_sec": 0, "end_time_sec": 1, "label": "Speech", "event_type": "speech"}]}

    report = build_index(manifest, tmp_path / "rebuilt", preserve_clap_from=legacy)
    rows = retrieval._load_records(tmp_path / "rebuilt" / "index")
    frame = next(row for row in rows if row["kind"] == "frame")
    scene = next(row for row in rows if row["kind"] == "scene_clip")

    assert frame["clap_vector"] == [0.1, 0.2, 0.3]
    assert frame["clap_embedding_backend"] == "laion_clap"
    assert scene["clap_vector"] is None
    assert report["clap"]["status"] == "completed"
    assert report["clap"]["preserved_record_count"] == 1
    assert report["vector_fields"]["clap_vector"] == 3


def test_keyword_and_next_page_do_not_repeat(tmp_path: Path) -> None:
    manifest = {"source": {"video_id": "v1", "file_name": "demo.mp4"}, "scenes": [], "audio_events": [{"event_id": f"a{i}", "start_time_sec": i, "end_time_sec": i + 1, "label": "audio_activity"} for i in range(4)], "audio": {}}
    build_index(manifest, tmp_path)
    first = search(tmp_path / "index", "audio", top_n=2, mode="keyword")
    second = search(tmp_path / "index", "audio", top_n=2, mode="keyword", offset=first["next_offset"] or 0)
    assert {item["record_id"] for item in first["results"]}.isdisjoint({item["record_id"] for item in second["results"]})


def test_search_uses_clap_as_late_reranker_without_concatenating_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from video_audio_analyzer.retrieval import _hash_vector
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    semantic = _hash_vector("query")
    near_match = [value * 0.99 for value in semantic]
    unrelated = [0.0] * len(semantic)
    rows = [
        {"record_id": "semantic-best", "kind": "audio_event", "text": "first", "pe_av_vector": semantic, "index_embedding_backend": "pe_av", "clap_vector": [0.0, 1.0], "clap_embedding_backend": "laion_clap"},
        {"record_id": "clap-best", "kind": "audio_event", "text": "second", "pe_av_vector": near_match, "index_embedding_backend": "pe_av", "clap_vector": [1.0, 0.0], "clap_embedding_backend": "laion_clap"},
        {"record_id": "semantic-low", "kind": "audio_event", "text": "third", "pe_av_vector": unrelated, "index_embedding_backend": "pe_av", "clap_vector": [0.0, 1.0], "clap_embedding_backend": "laion_clap"},
    ]
    (index_dir / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    class FakeCLAP:
        def text(self, _texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0]]

    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL", "http://unused-worker")
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", raising=False)
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", raising=False)
    monkeypatch.setattr(clap_adapter, "configured_adapter", lambda: FakeCLAP())
    result = search(index_dir, "query", top_n=2, mode="semantic")
    assert result["clap_backend"] == "laion_clap"
    assert result["fusion"] == "late_score_fusion_no_vector_concatenation"
    assert result["results"][0]["record_id"] == "clap-best"
    assert len(result["results"][0]["pe_av_vector"]) == 256
    assert len(result["results"][0]["clap_vector"]) == 2


def test_corpus_search_is_global_paginated_and_disambiguates_duplicate_record_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    vector = [1.0, 0.0, 0.0]
    for run_id, filename in (("run-one", "one.mp4"), ("run-two", "two.mp4")):
        run_dir = runs / run_id
        (run_dir / "index").mkdir(parents=True)
        (run_dir / "manifest.json").write_text(json.dumps({
            "run_id": run_id, "source": {"video_id": run_id, "file_name": filename},
            "embeddings": {"pe_av": {"status": "completed"}},
        }), encoding="utf-8")
        (run_dir / "index" / "index_manifest.json").write_text(json.dumps({
            "record_schema_version": 2,
            "model": {"backend": "pe_av", "status": "completed"},
            "vector_fields": {"pe_av_vector": len(vector)},
        }), encoding="utf-8")
        (run_dir / "index" / "records.jsonl").write_text(json.dumps({
            "record_id": "scene_1", "kind": "scene_clip", "text": f"bright {filename}",
            "pe_av_vector": vector, "index_embedding_backend": "pe_av", "clap_vector": None,
        }) + "\n", encoding="utf-8")
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", raising=False)
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: (vector, "pe_av", None, "unavailable"))
    first = retrieval.search_all(runs, "bright", top_n=1, mode="semantic")
    second = retrieval.search_all(runs, "bright", top_n=1, mode="semantic", offset=1)
    assert first["corpus_run_count"] == 2
    assert first["results"][0]["result_id"] != second["results"][0]["result_id"]
    assert first["results"][0]["record_id"] == second["results"][0]["record_id"]
    assert first["results"][0]["run_id"] != second["results"][0]["run_id"]


def test_corpus_semantic_hides_non_peav_and_withholds_when_query_embedding_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    for run_id, backend, status in (("real", "pe_av", "completed"), ("fallback", "deterministic_fallback", "unavailable")):
        run_dir = runs / run_id
        (run_dir / "index").mkdir(parents=True)
        (run_dir / "manifest.json").write_text(json.dumps({
            "source": {"video_id": run_id, "file_name": f"{run_id}.mp4"},
            "embeddings": {"pe_av": {"status": status}},
        }), encoding="utf-8")
        (run_dir / "index" / "index_manifest.json").write_text(json.dumps({
            "record_schema_version": 2,
            "model": {"backend": backend}, "vector_fields": {"pe_av_vector": 3},
        }), encoding="utf-8")
        (run_dir / "index" / "records.jsonl").write_text(json.dumps({
            "record_id": "event_1", "text": "music", "pe_av_vector": [1.0, 0.0, 0.0], "clap_vector": None,
        }) + "\n", encoding="utf-8")
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: ([0.0] * 256, "deterministic_fallback", None, "unavailable"))
    result = retrieval.search_all(runs, "music", mode="semantic")
    assert result["query_backend"] == "deterministic_fallback"
    assert result["results"] == []
    assert result["reason"].startswith("No real PE-AV or CLAP text query embedding")


def test_peav_semantic_query_does_not_return_clap_only_zero_score_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [1.0, 0.0]
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: (vector, "pe_av", None, "unavailable"))
    rows = [
        {"record_id": "peav", "kind": "scene_clip", "text": "actual semantic candidate", "pe_av_vector": vector,
         "index_embedding_backend": "pe_av", "clap_vector": None},
        {"record_id": "clap-only", "kind": "audio_event", "text": "CLAP-only candidate", "pe_av_vector": None,
         "index_embedding_backend": "deterministic_fallback", "clap_vector": [0.5, 0.5], "clap_embedding_backend": "laion_clap"},
    ]

    result = retrieval.search_records(rows, "candidate", top_n=5, mode="semantic")

    assert [row["record_id"] for row in result["results"]] == ["peav"]


def test_corpus_keyword_search_keeps_fallback_runs_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "runs" / "fallback"
    (run_dir / "index").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"source": {"video_id": "fallback", "file_name": "fallback.mp4"}}), encoding="utf-8")
    (run_dir / "index" / "index_manifest.json").write_text(json.dumps({"model": {"backend": "deterministic_fallback"}, "vector_fields": {"pe_av_vector": 3}}), encoding="utf-8")
    (run_dir / "index" / "records.jsonl").write_text(json.dumps({
        "record_id": "audio_1", "text": "ominous footsteps", "pe_av_vector": [1.0, 0.0, 0.0], "clap_vector": None,
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: ([0.0, 0.0, 0.0], "deterministic_fallback", None, "unavailable"))
    result = retrieval.search_all(tmp_path / "runs", "footsteps", mode="keyword")
    assert result["results"][0]["record_id"] == "audio_1"
    assert result["results"][0]["keyword_score"] == 1.0


def test_corpus_search_api_uses_analyzer_runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from video_audio_analyzer import api

    run_dir = tmp_path / "runs" / "fixture-run"
    (run_dir / "index").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "source": {"video_id": "fixture-video", "file_name": "fixture.mp4"}
    }), encoding="utf-8")
    (run_dir / "index" / "index_manifest.json").write_text(json.dumps({
        "record_schema_version": 2,
        "model": {"backend": "deterministic_fallback"},
        "vector_fields": {"pe_av_vector": None},
    }), encoding="utf-8")
    (run_dir / "index" / "records.jsonl").write_text(json.dumps({
        "record_id": "audio_event_1", "kind": "audio_event", "text": "metal footsteps",
        "pe_av_vector": [1.0, 0.0, 0.0], "clap_vector": None,
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(api, "ROOT", tmp_path)

    response = api.search_all(api.CorpusSearchRequest(query="footsteps", mode="keyword", top_n=1))

    assert response["corpus_run_count"] == 1
    assert response["results"][0]["result_id"] == "fixture-run:audio_event_1"
    assert response["results"][0]["source_file"] == "fixture.mp4"


def test_remote_peav_query_embedding_is_used_for_semantic_search(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [0.0] * 256
    vector[0] = 1.0
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", raising=False)
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "http://127.0.0.1:8034")
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL", raising=False)
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_CLAP_CHECKPOINT", raising=False)
    monkeypatch.setattr(retrieval, "_remote_peav_text", lambda query: vector)
    record = {"record_id": "peav-record", "text": "a person speaking", "pe_av_vector": vector,
              "index_embedding_backend": "pe_av", "clap_vector": None}

    result = retrieval.search_records([record], "someone speaking", mode="semantic")

    assert result["query_backend"] == "pe_av"
    assert result["results"][0]["record_id"] == "peav-record"
    assert result["results"][0]["semantic_score"] == pytest.approx(1.0)


def test_scene_clip_is_the_only_record_to_inherit_scene_av_embedding() -> None:
    manifest = {
        "source": {"video_id": "v1", "file_name": "scene.mp4"},
        "embeddings": {"pe_av": {"status": "completed"}},
        "scenes": [{"scene_id": "scene_1", "start_time_sec": 1.0, "end_time_sec": 4.0,
            "embeddings": {"provider": "facebook/pe-av-base", "audio_video": [0.1, 0.9]},
            "frames": [{"frame_id": "frame_1", "timestamp_sec": 1.0, "path": "frame.jpg", "evidence": {}}]}],
        "audio_events": [{"event_id": "audio_1", "start_time_sec": 1.0, "end_time_sec": 4.0, "label": "Speech", "event_type": "speech"}],
        "transcript": {"segments": [{"start_time_sec": 2.0, "end_time_sec": 3.0, "text": "We should go."}]},
    }

    records = list(retrieval._records(manifest))
    scene = next(row for row in records if row["kind"] == "scene_clip")
    frame = next(row for row in records if row["kind"] == "frame")
    event = next(row for row in records if row["kind"] == "audio_event")
    assert scene["pe_av_vector"] == [0.1, 0.9]
    assert "We should go." in scene["text"]
    assert frame["pe_av_vector"] is None
    assert event["pe_av_vector"] is None


def test_internvideo_clip_and_full_summary_text_vectors_are_indexed_separately() -> None:
    manifest = {
        "source": {"video_id": "v1", "file_name": "scene.mp4", "duration_sec": 8.0},
        "embeddings": {"pe_av": {"text_summary": {"status": "completed"}}},
        "scenes": [{"scene_id": "scene_1", "start_time_sec": 0.0, "end_time_sec": 8.0,
            "summary": "A man speaks then gestures to his right.",
            "embeddings": {"text_summary": [0.1, 0.9]}, "frames": []}],
        "internvideo3": {"full_video_summary": "A man speaks in a close-up and gestures.",
            "full_video_summary_embedding": {"vector": [0.2, 0.8]}},
    }
    records = list(retrieval._records(manifest))
    clip = next(row for row in records if row["kind"] == "scene_clip")
    full = next(row for row in records if row["kind"] == "video_summary")
    assert clip["pe_av_vector"] is None
    assert clip["pe_av_text_vector"] == [0.1, 0.9]
    assert "man speaks" in clip["text"]
    assert full["pe_av_text_vector"] == [0.2, 0.8]
    assert (full["start_time_sec"], full["end_time_sec"]) == (0.0, 8.0)


def test_semantic_search_uses_text_vectors_without_concatenating_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = [0.2, 0.8]
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", raising=False)
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_AUDIO_WORKER_URL", raising=False)
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_PE_AV_WORKER_URL", "http://fake")
    monkeypatch.setattr(retrieval, "_remote_peav_text", lambda query: vector)
    records = [
        {"record_id": "clip", "kind": "scene_clip", "text": "gesture",
         "pe_av_vector": [1.0, 0.0], "index_embedding_backend": "pe_av",
         "pe_av_text_vector": vector, "pe_av_text_embedding_backend": "pe_av"},
        {"record_id": "video", "kind": "video_summary", "text": "full video",
         "pe_av_vector": None, "index_embedding_backend": "deterministic_fallback",
         "pe_av_text_vector": vector, "pe_av_text_embedding_backend": "pe_av"},
    ]
    result = retrieval.search_records(records, "gesture", mode="semantic")
    assert result["query_backend"] == "pe_av"
    assert {row["record_id"] for row in result["results"]} == {"clip", "video"}
    clip = next(row for row in result["results"] if row["record_id"] == "clip")
    assert clip["semantic_text_score"] == 1.0
    assert clip["semantic_video_score"] == pytest.approx(0.242536)


def test_corpus_semantic_results_are_scene_clips_not_reused_event_vectors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "runs" / "clip-run"
    index_dir = run_dir / "index_v2"
    index_dir.mkdir(parents=True)
    manifest = {"source": {"video_id": "v1", "file_name": "clip.mp4"},
        "embeddings": {"pe_av": {"status": "completed"}}}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (index_dir / "index_manifest.json").write_text(json.dumps({"record_schema_version": 2,
        "model": {"backend": "pe_av", "status": "completed"}, "clap": {"status": "unavailable"},
        "vector_fields": {"pe_av_vector": 2, "clap_vector": None}}), encoding="utf-8")
    rows = [
        {"record_id": "scene_1", "kind": "scene_clip", "text": "speaker and music", "pe_av_vector": [1.0, 0.0], "index_embedding_backend": "pe_av"},
        {"record_id": "audio_1", "kind": "audio_event", "text": "music", "pe_av_vector": None, "index_embedding_backend": "deterministic_fallback"},
    ]
    (index_dir / "records.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: ([1.0, 0.0], "pe_av", None, "unavailable"))

    result = retrieval.search_all(tmp_path / "runs", "speaker and music", mode="semantic")

    assert [row["kind"] for row in result["results"]] == ["scene_clip"]
    assert [row["record_id"] for row in result["results"]] == ["scene_1"]


def test_corpus_search_collapses_duplicate_analysis_runs_for_same_source_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = tmp_path / "runs"
    vector = [1.0, 0.0]
    for run_id, text in (("old", "older description"), ("latest", "latest description")):
        run_dir = runs / run_id
        index_dir = run_dir / "index_v2"
        index_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(json.dumps({"source": {"video_id": "same-video", "file_name": "same.mp4"},
            "embeddings": {"pe_av": {"status": "completed"}}}), encoding="utf-8")
        (index_dir / "index_manifest.json").write_text(json.dumps({"record_schema_version": 2,
            "model": {"backend": "pe_av"}, "vector_fields": {"pe_av_vector": 2}}), encoding="utf-8")
        (index_dir / "records.jsonl").write_text(json.dumps({"record_id": "scene_1", "kind": "scene_clip", "text": text,
            "pe_av_vector": vector, "index_embedding_backend": "pe_av"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(retrieval, "_query_embeddings", lambda query, records, mode: (vector, "pe_av", None, "unavailable"))

    result = retrieval.search_all(runs, "latest", mode="semantic")

    assert result["corpus_run_count"] == 2
    assert result["corpus_video_count"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["run_id"] == "latest"


def test_index_excludes_unreliable_or_unbounded_sound_labels_from_search_text() -> None:
    giant_label = ", ".join([f"label_{index}" for index in range(150)])
    manifest = {"source": {"video_id": "v1", "file_name": "audio.mp4"},
        "scenes": [{"scene_id": "scene_1", "start_time_sec": 0, "end_time_sec": 5, "frames": []}],
        "audio_events": [
            {"event_id": "false_sfx", "start_time_sec": 0, "end_time_sec": 5, "label": "Explosion", "confidence": 0.5, "event_type": "sfx_ambience"},
            {"event_id": "giant_sfx", "start_time_sec": 0, "end_time_sec": 5, "label": giant_label, "confidence": 0.99, "event_type": "sfx_ambience"},
            {"event_id": "music", "start_time_sec": 0, "end_time_sec": 5, "label": "Music", "confidence": 0.58, "event_type": "music"},
        ]}

    records = list(retrieval._records(manifest))

    assert "Explosion" not in next(row for row in records if row["kind"] == "scene_clip")["text"]
    assert "Music" in next(row for row in records if row["kind"] == "scene_clip")["text"]
    assert "giant_sfx" not in {row["record_id"] for row in records}


def test_peav_worker_health_and_lazy_text_embedding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from video_audio_analyzer import peav_worker

    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "model.safetensors").write_bytes(b"fixture")
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_PE_AV_PATH", str(tmp_path))

    class FakeAdapter:
        def embed(self, *, text: str) -> dict[str, list[list[float]]]:
            assert text == "a person speaking"
            return {"text_audio_video_embeds": [[0.25, 0.75]]}

    monkeypatch.setattr(peav_worker, "_adapter", lambda: FakeAdapter())
    assert peav_worker.health()["status"] == "checkpoint_ready_lazy_load"
    response = peav_worker.embed_text("a person speaking")
    assert response == {"model": "facebook/pe-av-base", "dimension": 2, "embedding": [0.25, 0.75]}
