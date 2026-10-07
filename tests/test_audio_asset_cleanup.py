import json

import pytest

from story_builder.services import video_repertoire as repertoire


def _seed_audio_store(root):
    run_root = root / "analyses" / "video_audio_analyzer" / "run-a"
    derived_a = run_root / "audio" / "collected" / "sfx" / "thunder-01.wav"
    derived_b = run_root / "audio" / "collected" / "sfx" / "thunder-02.wav"
    derived_c = run_root / "audio" / "collected" / "sfx" / "thunder-03.wav"
    source = root / "audio" / "source_mix.wav"
    for path in (derived_a, derived_b, derived_c, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"same-derived-audio")
    derived_c.write_bytes(b"different thunder occurrence")
    manifest_dir = root / "manifests" / "analyzer-runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"project_id": "project-a", "video_id": "video-a", "collected_assets": [
        {"asset_id": "thunder-01", "category": "sfx", "label": "thunder", "path": derived_a.relative_to(root).as_posix(), "start_time_sec": 1.0, "end_time_sec": 2.0},
        {"asset_id": "thunder-02", "category": "sfx", "label": "thunder", "path": derived_b.relative_to(root).as_posix(), "start_time_sec": 3.0, "end_time_sec": 4.0},
        {"asset_id": "thunder-03", "category": "sfx", "label": "Thunder", "path": derived_c.relative_to(root).as_posix(), "start_time_sec": 5.0, "end_time_sec": 6.0},
    ], "source_audio": source.relative_to(root).as_posix()}
    manifest_path = manifest_dir / "run-a.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return derived_a, derived_b, derived_c, source, manifest_path


def test_audio_duplicate_grouping_uses_exact_hash_and_is_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(repertoire, "REPERTOIRE_ROOT", tmp_path / "repertoire")
    a, b, c, _, _ = _seed_audio_store(repertoire.REPERTOIRE_ROOT)
    rows = repertoire.list_audio_assets("sfx")
    assert len(rows) == 3
    exact = [row for row in rows if row.get("duplicate")]
    assert len(exact) == 2
    assert exact[0]["duplicate_basis"] == "exact_file_hash"
    assert exact[0]["duplicate_project_id"] == "project-a"
    # Third thunder occurrence has different bytes: grouped by classifier for
    # review, but not represented as a confirmed duplicate or auto-selected.
    distinct = next(row for row in rows if row["relative_path"].endswith("thunder-03.wav"))
    assert distinct["classification_duplicate_candidate"] is True
    assert distinct["classification_group_size"] == 3
    assert distinct.get("duplicate") is not True


def test_audio_delete_removes_only_selected_derived_file_and_preserves_event_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(repertoire, "REPERTOIRE_ROOT", tmp_path / "repertoire")
    a, b, c, source, manifest_path = _seed_audio_store(repertoire.REPERTOIRE_ROOT)
    relative = a.relative_to(repertoire.REPERTOIRE_ROOT).as_posix()
    result = repertoire.delete_audio_assets([relative], confirmed=True)
    assert result["deleted"] == [relative]
    assert result["occurrence_metadata_preserved"] is True
    assert not a.exists() and b.exists() and c.exists() and source.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["collected_assets"][0]["asset_deleted"] is True
    assert manifest["collected_assets"][0]["start_time_sec"] == 1.0
    assert repertoire.list_audio_assets("sfx")[0]["available"] is False


def test_audio_delete_requires_confirmation_and_rejects_unregistered_source_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(repertoire, "REPERTOIRE_ROOT", tmp_path / "repertoire")
    _, _, _, source, _ = _seed_audio_store(repertoire.REPERTOIRE_ROOT)
    with pytest.raises(ValueError, match="Explicit confirmation"):
        repertoire.delete_audio_assets(["audio/source_mix.wav"], confirmed=False)
    with pytest.raises(ValueError, match="Not a registered derived audio asset"):
        repertoire.delete_audio_assets(["audio/source_mix.wav"], confirmed=True)
    assert source.exists()
