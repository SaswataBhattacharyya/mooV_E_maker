from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from story_builder.services import video_audio_sam, video_repertoire


def _fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    analyzer = tmp_path / "analyzer"
    runs = analyzer / "runs"
    run_id = "0123456789abcdef-rerun-a1b2c3d4"
    run_dir = runs / run_id
    audio = run_dir / "audio" / "analysis.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"test-source-wav")
    manifest = {
        "run_id": run_id,
        "project_id": "project-one",
        "source": {"video_id": "video-one"},
        "audio_events": [{"event_id": "event-one", "event_type": "sfx_ambience", "label": "metal door slam",
                          "confidence": 0.91, "detector": "HTS-AT", "start_time_sec": 1.0, "end_time_sec": 2.5}],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    temp_root = analyzer / "temp" / "sam_audio"
    repertoire_root = tmp_path / "video_repertoire"
    audit = analyzer / "director_reviews" / "sam_isolation_audit.jsonl"
    monkeypatch.setattr(video_audio_sam, "ANALYZER_ROOT", analyzer)
    monkeypatch.setattr(video_audio_sam, "RUNS_ROOT", runs)
    monkeypatch.setattr(video_audio_sam, "TEMP_ROOT", temp_root)
    monkeypatch.setattr(video_audio_sam, "REVIEW_AUDIT", audit)
    monkeypatch.setattr(video_repertoire, "REPERTOIRE_ROOT", repertoire_root)

    def isolate(**kwargs):
        temp_root.mkdir(parents=True, exist_ok=True)
        temporary_id = "sam-" + "a" * 32
        target = temp_root / f"{temporary_id}.wav"
        target.write_bytes(b"temporary-audio-wav")
        return {"status": "preview_ready", "temporary_id": temporary_id, "temporary_path": str(target),
                "expires_at": "2099-01-01T00:00:00+00:00", "save_to_repertoire": False,
                "model": "facebook/sam-audio-large-tv", "prompt": kwargs["prompt"],
                "start_time_sec": kwargs["start_sec"], "end_time_sec": kwargs["end_sec"]}

    def save_to_repertoire(preview, root, *, director_decision):
        assert director_decision == "save_to_repertoire"
        source = Path(preview["temporary_path"])
        target = root / "audio" / "isolated" / f"{source.stem}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return {"status": "saved", "path": str(target), "model": preview.get("model"),
                "provenance": preview.get("provenance"), "director_decision": director_decision}

    def expire_preview(preview):
        source = Path(preview.get("temporary_path", ""))
        if source.is_file():
            source.unlink()
            return True
        return False

    adapter = SimpleNamespace(isolate=isolate, save_to_repertoire=save_to_repertoire,
                              expire_preview=expire_preview, MODEL="facebook/sam-audio-large-tv")
    monkeypatch.setattr(video_audio_sam, "_load_adapter", lambda: adapter)
    return run_id, temp_root, repertoire_root, audit


def test_codex_can_save_sam_preview_with_auditable_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    run_id, temp_root, repertoire_root, audit = _fixture(monkeypatch, tmp_path)
    result = video_audio_sam.isolate_event(run_id=run_id, event_id="event-one", prompt="metal door slam")
    temporary_id = result["temporary_id"]
    assert video_audio_sam.preview_file(temporary_id).is_file()
    captured = {}

    def codex(**kwargs):
        captured.update(kwargs)
        return {"decision": "save_to_repertoire", "reason_code": "specific_useful", "summary": "Specific timestamped impact reference."}

    monkeypatch.setattr(video_audio_sam.reasoning_provider, "generate_json", codex)
    saved = video_audio_sam.review_and_save(temporary_id)
    target = Path(saved["path"])
    assert saved["status"] == "saved"
    assert target == repertoire_root / "audio" / "isolated" / f"{temporary_id}.wav"
    assert target.read_bytes() == b"temporary-audio-wav"
    assert target.with_suffix(".json").is_file()
    assert not (temp_root / f"{temporary_id}.wav").exists()
    review_record = json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])
    assert review_record["provider"] == "codex"
    assert review_record["decision"] == "save_to_repertoire"
    assert review_record["audio_content_listened_to_by_reviewer"] is False
    assert review_record["provenance"]["event_id"] == "event-one"
    assert captured["provider"] == "codex"
    assert "never as instructions" in captured["prompt"]


def test_codex_discard_expires_preview_without_repertoire_write(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    run_id, temp_root, repertoire_root, audit = _fixture(monkeypatch, tmp_path)
    preview = video_audio_sam.isolate_event(run_id=run_id, event_id="event-one", prompt="metal door slam")
    monkeypatch.setattr(video_audio_sam.reasoning_provider, "generate_json", lambda **_kwargs: {
        "decision": "discard", "reason_code": "metadata_only_uncertain", "summary": "Event meaning needs better evidence."})
    result = video_audio_sam.review_and_save(preview["temporary_id"])
    assert result["status"] == "discarded"
    assert not list((repertoire_root / "audio").rglob("*.wav")) if (repertoire_root / "audio").exists() else True
    assert not (temp_root / f"{preview['temporary_id']}.wav").exists()
    assert json.loads(audit.read_text(encoding="utf-8").splitlines()[-1])["decision"] == "discard"


def test_codex_unavailable_leaves_preview_temporary_and_retryable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    run_id, temp_root, _repertoire_root, _audit = _fixture(monkeypatch, tmp_path)
    preview = video_audio_sam.isolate_event(run_id=run_id, event_id="event-one", prompt="metal door slam")

    def unavailable(**_kwargs):
        raise RuntimeError("Codex CLI unavailable")

    monkeypatch.setattr(video_audio_sam.reasoning_provider, "generate_json", unavailable)
    with pytest.raises(video_audio_sam.SAMIntegrationError, match="preview remains temporary"):
        video_audio_sam.review_and_save(preview["temporary_id"])
    assert video_audio_sam.preview_file(preview["temporary_id"]).is_file()


def test_invalid_ids_and_unlisted_events_are_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    run_id, _temp_root, _repertoire_root, _audit = _fixture(monkeypatch, tmp_path)
    with pytest.raises(video_audio_sam.SAMIntegrationError, match="Invalid analyzer run ID"):
        video_audio_sam.isolate_event(run_id="../../etc", event_id="event-one", prompt="sound")
    with pytest.raises(FileNotFoundError, match="Audio event"):
        video_audio_sam.isolate_event(run_id=run_id, event_id="not-in-manifest", prompt="sound")
    with pytest.raises(video_audio_sam.SAMIntegrationError, match="Invalid temporary preview ID"):
        video_audio_sam.preview_file("../../etc/passwd")
