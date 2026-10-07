from __future__ import annotations

import json
from pathlib import Path

import pytest

from video_audio_analyzer.clap_adapter import RemoteCLAPAdapter, late_fusion
from video_audio_analyzer.identity import associate_speakers
from video_audio_analyzer.htsat_adapter import _as_probabilities
from video_audio_analyzer.nemo_adapter import diarize
from video_audio_analyzer.sam_audio_adapter import cleanup_expired_previews, expire_preview, readiness, save_to_repertoire
from video_audio_analyzer.voice_store import VoiceStore, anonymous_alias


def test_voice_store_project_first_then_global_and_bounded(tmp_path: Path):
    store = VoiceStore(tmp_path / "voices")
    local = store.add_identity(project_id="p1", video_id="v1", speaker_id="s1", embedding=[1, 0, 0], start_time_sec=1, end_time_sec=2)
    global1 = store.add_identity(project_id="p2", video_id="v2", speaker_id="s2", embedding=[0.99, 0.01, 0], start_time_sec=3, end_time_sec=4)
    local_match = store.candidates([0.99, 0.01, 0], "p1", top_k=1)
    assert local_match["scope_used"] == "project"
    assert len(local_match["candidates"]) == 1
    # The local candidate is intentionally not a merge: the director must audit it.
    audit = store.audit_decision(candidate=local_match["candidates"][0], decision="keep_anonymous",
        reviewer="codex", project_id="p1", video_id="v3", timestamp_sec=1.5,
        supporting_evidence={"active_speaker": None}, provenance="unit-test")
    assert audit["reviewer"] == "codex"
    assert (tmp_path / "voices" / "codex_decisions.jsonl").exists()
    # Force an insufficient local candidate: fall through to the global index.
    global_match = store.candidates([0, 1, 0], "p1", top_k=1, local_candidate_floor=0.99)
    assert global_match["scope_used"] == "global"
    assert global_match["candidates"][0]["voice_identity_id"] == global1["voice_identity_id"]
    assert len(store._read()) == 2
    assert local["voice_identity_id"] != global1["voice_identity_id"]
    with pytest.raises(ValueError, match="reviewer"):
        store.audit_decision(candidate=local_match["candidates"][0], decision="keep_anonymous",
            reviewer="hermes", project_id="p1", video_id="v3", timestamp_sec=1.5,
            supporting_evidence={}, provenance="disallowed-provider")


def test_anonymous_alias_is_collision_safe_and_uuid_identity_immutable(tmp_path: Path):
    alias = anonymous_alias({"Character-0000"})
    row = VoiceStore(tmp_path).add_identity(project_id="p", video_id="v", speaker_id="s", embedding=[0.2, 0.8], start_time_sec=0, end_time_sec=1)
    assert alias.startswith("Character-")
    assert row["display_name"].startswith("Character-")
    assert row["character_id"] and row["voice_identity_id"]


def test_voice_store_reruns_are_idempotent_for_same_timed_example(tmp_path: Path):
    store = VoiceStore(tmp_path / "voices")
    first = store.add_identity(project_id="p", video_id="v", speaker_id="s", embedding=[1, 0], start_time_sec=1, end_time_sec=2)
    repeated = store.add_identity(project_id="p", video_id="v", speaker_id="s", embedding=[1, 0], start_time_sec=1, end_time_sec=2)
    assert repeated["voice_identity_id"] == first["voice_identity_id"]
    assert repeated["example_count"] == 1
    assert len(repeated["examples"]) == 1


def test_voice_store_codex_link_keeps_immutable_ids_and_deduplicates_candidates(tmp_path: Path):
    store = VoiceStore(tmp_path / "voice-links")
    current = store.add_identity(project_id="p2", video_id="v2", speaker_id="s2", embedding=[0.99, 0.01], start_time_sec=0, end_time_sec=1)
    canonical = store.add_identity(project_id="p1", video_id="v1", speaker_id="s1", embedding=[1, 0], start_time_sec=0, end_time_sec=1)
    linked = store.link_confirmed_identity(current_identity_id=current["voice_identity_id"],
        canonical_identity_id=canonical["voice_identity_id"], decision_id="codex-decision", provenance={"reviewer": "codex"})
    assert linked["voice_identity_id"] == current["voice_identity_id"]
    assert linked["character_id"] == current["character_id"]
    assert linked["canonical_voice_identity_id"] == canonical["voice_identity_id"]
    assert len(store._deduplicate(store._read(), [1, 0])) == 1


def test_voice_store_lancedb_project_then_global_ann(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import os
    if os.environ.get("VIDEO_AUDIO_ANALYZER_RUN_LANCEDB_TESTS") != "1":
        pytest.skip("LanceDB integration runs in the analyzer's pinned Docker runtime, not the host Python env")
    pytest.importorskip("lancedb")
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_VOICE_STORE_ENABLE_LANCEDB", "1")
    store = VoiceStore(tmp_path / "voice-ann")
    local = store.add_identity(project_id="local", video_id="v-local", speaker_id="s-local",
        embedding=[1, 0, 0], start_time_sec=0, end_time_sec=2)
    global_identity = store.add_identity(project_id="other", video_id="v-other", speaker_id="s-other",
        embedding=[0, 1, 0], start_time_sec=3, end_time_sec=5)
    local_match = store.candidates([0.99, 0.01, 0], "local", top_k=2)
    assert local_match["backend"] == "lancedb_ann"
    assert local_match["scope_used"] == "project"
    assert local_match["candidates"][0]["voice_identity_id"] == local["voice_identity_id"]
    global_match = store.candidates([0, 1, 0], "local", top_k=1, local_candidate_floor=0.99)
    assert global_match["backend"] == "lancedb_ann"
    assert global_match["scope_used"] == "global"
    assert global_match["candidates"][0]["voice_identity_id"] == global_identity["voice_identity_id"]


def test_clap_late_fusion_uses_scores_and_not_feature_concatenation():
    scores = late_fusion([0.2, 0.8], {"a": 0.9, "b": 0.1}, ["a", "b"])
    assert scores == pytest.approx([0.35, 0.65])
    assert late_fusion([0.2], {}, ["a"]) == [0.2]


def test_htsat_probabilities_are_not_sigmoided_twice():
    import numpy as np
    assert _as_probabilities(np.array([0.02, 0.6, 0.98], dtype="float32")) == pytest.approx([0.02, 0.6, 0.98])
    assert _as_probabilities(np.array([-2.0, 0.0, 2.0], dtype="float32")) == pytest.approx([0.1192, 0.5, 0.8808], abs=1e-3)


def test_remote_clap_batches_large_text_lists(monkeypatch: pytest.MonkeyPatch):
    import requests
    batch_sizes: list[int] = []

    class Response:
        def __init__(self, size: int):
            self.size = size

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[list[float]]]:
            return {"embeddings": [[0.0] * 512 for _ in range(self.size)]}

    def post(_url: str, *, json: dict[str, list[str]], timeout: int) -> Response:
        batch_sizes.append(len(json["texts"]))
        return Response(len(json["texts"]))

    monkeypatch.setattr(requests, "post", post)
    result = RemoteCLAPAdapter("http://worker").text([f"phrase {index}" for index in range(257)])
    assert batch_sizes == [256, 1]
    assert len(result) == 257
    assert all(len(row) == 512 for row in result)


def test_active_speaker_association_needs_explicit_asd_score():
    utterance = [{"speaker_id": "speaker_0", "start_time_sec": 1, "end_time_sec": 3}]
    tracks = [{"track_id": "person_1", "start_time_sec": 0, "end_time_sec": 4}]
    no_asd = associate_speakers(utterance, tracks, [])
    assert no_asd[0]["candidate_track_id"] is None
    assert no_asd[0]["association_state"] == "anonymous_unassociated"
    yes_asd = associate_speakers(utterance, tracks, [{"track_id": "person_1", "timestamp_sec": 2, "score": 0.91}])
    assert yes_asd[0]["candidate_track_id"] == "person_1"
    assert yes_asd[0]["association_state"] == "candidate_needs_director_confirmation"
    assert yes_asd[0]["identity_merge_allowed"] is False


def test_talknet_face_track_scores_convert_to_timestamped_candidates():
    import numpy as np
    from video_audio_analyzer.talknet_worker import _compact_tracks

    tracks, scores = _compact_tracks([
        {"track": {"frame": np.asarray([25, 26, 27])},
         "proc_track": {"x": [100, 101, 102], "y": [80, 80, 81], "s": [24, 24, 25]}}
    ], [np.asarray([1.5, 1.5, 1.5])])
    assert len(tracks) == 1
    assert tracks[0]["track_id"] == "talknet_face_track_0001"
    assert tracks[0]["start_time_sec"] == 1.0
    assert len(scores) == 3
    assert scores[-1]["timestamp_sec"] == 1.08
    assert all(row["face_box"] for row in scores)
    joined = associate_speakers(
        [{"speaker_id": "speaker_0", "start_time_sec": 1.0, "end_time_sec": 1.12}],
        tracks, scores,
    )
    assert joined[0]["candidate_track_id"] == "talknet_face_track_0001"
    assert joined[0]["identity_merge_allowed"] is False


def test_nemo_missing_checkpoints_is_nonblocking_and_offline(tmp_path: Path):
    result = diarize(tmp_path / "audio.wav", tmp_path / "nemo")
    assert result["status"] == "unavailable"
    assert result["offline_only"] is True
    assert "required" in result["reason"]


def test_preflight_report_can_be_routed_into_shared_repertoire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import urllib.request
    from video_audio_analyzer.preflight import run_preflight

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self):
            return b'{"ok":true,"available":true}'

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    target = tmp_path / "video_repertoire" / "manifests" / "preflight.json"
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_PREFLIGHT_PATH", str(target))
    run_preflight(tmp_path / "analyzer")
    assert target.is_file()
    assert not (tmp_path / "analyzer" / "manifests" / "preflight.json").exists()


def test_sam_is_lazy_and_persistence_requires_director_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL", raising=False)
    status = readiness()
    assert status["auto_download"] is False
    preview_path = tmp_path / "temporary.wav"
    preview_path.write_bytes(b"audio")
    preview = {"status": "preview_ready", "temporary_path": str(preview_path), "temporary_id": "tmp1", "model": "facebook/sam-audio-large-tv", "provenance": {"event_id": "event1"}}
    with pytest.raises(PermissionError):
        save_to_repertoire(preview, tmp_path / "repertoire", director_decision="keep_temporary")
    saved = save_to_repertoire(preview, tmp_path / "repertoire", director_decision="save_to_repertoire")
    assert Path(saved["path"]).read_bytes() == b"audio"
    assert expire_preview(preview) is True
    assert not preview_path.exists()
    expired = tmp_path / "sam-expired.wav"
    expired.write_bytes(b"audio")
    import os, time
    os.utime(expired, (time.time() - 7200, time.time() - 7200))
    assert cleanup_expired_previews(tmp_path, ttl_hours=1) == 1
    assert not expired.exists()


def test_sam_large_checkpoint_readiness_and_alias_avoid_weight_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from video_audio_analyzer import sam_audio_worker
    checkpoint = tmp_path / "sam-audio-large-tv"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text(json.dumps({"text_encoder": {"name": "t5-base"},
        "span_predictor": "pe-a-frame-large", "text_ranker": {}, "visual_ranker": {}}), encoding="utf-8")
    weights = checkpoint / "sam-audio-large-tv_checkpoint.pt"
    weights.write_bytes(b"test-checkpoint")
    monkeypatch.setattr(sam_audio_worker, "CHECKPOINT", checkpoint)
    monkeypatch.setattr(sam_audio_worker, "CHECKPOINT_FILENAME", weights.name)
    monkeypatch.setattr(sam_audio_worker, "_model_alias_dir", None)
    assert sam_audio_worker._checkpoint_ready()
    alias = sam_audio_worker._loader_checkpoint_dir()
    assert (alias / "checkpoint.pt").is_symlink()
    assert (alias / "checkpoint.pt").resolve() == weights.resolve()
    aliased_config = json.loads((alias / "config.json").read_text(encoding="utf-8"))
    assert aliased_config["text_encoder"]["name"] == str(sam_audio_worker.T5_CHECKPOINT)
    assert aliased_config["span_predictor"] is None
    assert aliased_config["text_ranker"] is None and aliased_config["visual_ranker"] is None
    assert sam_audio_worker.health()["model"] == "facebook/sam-audio-large-tv"


def test_collection_toggles_create_only_opted_in_event_assets(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from video_audio_analyzer.pipeline import _collect_audio_event_clips

    source = tmp_path / "analysis.wav"
    sf.write(source, np.zeros(2 * 16000, dtype="float32"), 16000)
    events = [
        {"event_id": "music1", "event_type": "music", "label": "Music", "confidence": 0.9,
         "start_time_sec": 0.0, "end_time_sec": 1.0},
        {"event_id": "sfx1", "event_type": "sfx_ambience", "label": "Door slam", "confidence": 0.8,
         "start_time_sec": 1.0, "end_time_sec": 2.0},
        {"event_id": "weak", "event_type": "sfx_ambience", "label": "Unknown sound", "confidence": 0.2,
         "start_time_sec": 0.0, "end_time_sec": 1.0},
    ]
    out = tmp_path / "collected"
    music = _collect_audio_event_clips(source, events, out, collect_music=True, collect_sfx=False)
    assert [asset["category"] for asset in music] == ["music"]
    assert Path(music[0]["path"]).is_file()
    sfx = _collect_audio_event_clips(source, events, out, collect_music=False, collect_sfx=True)
    assert [asset["category"] for asset in sfx] == ["sfx"]
    assert all(Path(asset["path"]).is_file() for asset in sfx)


def test_voice_store_can_be_restricted_to_project_scope(tmp_path: Path):
    store = VoiceStore(tmp_path / "voices")
    store.add_identity(project_id="other", video_id="v1", speaker_id="s1", embedding=[1, 0], start_time_sec=0, end_time_sec=1)
    result = store.candidates([1, 0], "current", scope="project_only")
    assert result["scope_used"] == "project"
    assert result["candidates"] == []


def test_sam_api_reports_gated_unavailable_without_fabricating_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi import HTTPException
    from video_audio_analyzer import api
    from video_audio_analyzer.api import SAMIsolateRequest, sam_isolate
    test_root = tmp_path / "api-root"
    run_id = "a" * 16
    run = test_root / "runs" / run_id
    run.mkdir(parents=True)
    (run / "audio").mkdir()
    (run / "audio" / "analysis.wav").write_bytes(b"test audio placeholder")
    manifest = {"source": {"video_id": run_id}, "audio_events": [{"event_id": "event-1",
        "event_type": "speech", "start_time_sec": 0.0, "end_time_sec": 1.0}],
        "audio": {"analysis_wav": str(run / "audio" / "analysis.wav")}}
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(api, "ROOT", test_root)
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL", raising=False)
    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_SAM_TEMP_PATH", str(test_root / "temp" / "sam_audio"))
    request = SAMIsolateRequest(**{
        "run_id": run_id,
        "event_id": "event-1",
        "prompt": "speech",
    })
    with pytest.raises(HTTPException) as response:
        sam_isolate(request)
    assert response.value.status_code == 503
    assert response.value.detail["status"] == "unavailable"
    temp_root = test_root / "temp" / "sam_audio"
    assert not list(temp_root.glob("sam-*.wav")) if temp_root.exists() else True


def test_sam_remote_worker_wav_contract_is_temporary_and_provenance_linked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import io
    import numpy as np
    import requests
    import soundfile as sf
    from video_audio_analyzer.sam_audio_adapter import isolate

    source = tmp_path / "analysis.wav"
    sf.write(source, np.zeros(16000, dtype="float32"), 16000)
    output_bytes = io.BytesIO()
    sf.write(output_bytes, np.zeros(16000, dtype="float32"), 16000, format="WAV")
    received: dict[str, object] = {}

    class Response:
        status_code = 200
        content = output_bytes.getvalue()
        headers = {"content-type": "audio/wav"}
        def raise_for_status(self) -> None:
            return None
        def json(self) -> dict[str, object]:
            return {"ok": True, "checkpoint_present": True}

    def get(_url: str, timeout: int) -> Response:
        return Response()

    def post(_url: str, *, files: dict[str, object], data: dict[str, str], timeout: int) -> Response:
        received.update({"filename": files["audio"][0], "prompt": data["prompt"],
                         "start": data["start_sec"], "end": data["end_sec"]})
        return Response()

    monkeypatch.setenv("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_URL", "http://sam-worker")
    monkeypatch.delenv("VIDEO_AUDIO_ANALYZER_SAM_AUDIO_PATH", raising=False)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    preview = isolate(audio_path=source, prompt="door slam", start_sec=0.2, end_sec=0.8,
        temp_root=tmp_path / "tmp-sam", provenance={"run_id": "run1", "event_id": "event1"})
    assert preview["status"] == "preview_ready"
    assert preview["save_to_repertoire"] is False
    assert preview["provenance"]["event_id"] == "event1"
    assert received == {"filename": "analysis.wav", "prompt": "door slam", "start": "0.2", "end": "0.8"}
    output = Path(str(preview["temporary_path"]))
    assert sf.info(str(output)).duration == pytest.approx(1.0)
