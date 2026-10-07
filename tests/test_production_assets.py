from __future__ import annotations

import io
import json
import subprocess

import pytest
from PIL import Image

from story_builder.services import production_assets as assets


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (7, 5), color=(30, 80, 120)).save(output, format="PNG")
    return output.getvalue()


def _fake_probe(*_args, **_kwargs):
    return subprocess.CompletedProcess(args=["ffprobe"], returncode=0,
        stdout=json.dumps({"format": {"duration": "2.5", "format_name": "mov,mp4"},
                           "streams": [{"codec_type": "video", "codec_name": "h264", "width": 640, "height": 360}]}), stderr="")


def test_upload_registers_once_with_project_scope_hash_role_and_safe_content(tmp_path):
    project_id = "sample-project"
    png = _png_bytes()
    first = assets.register_upload(tmp_path / "projects", project_id,
        filename="portrait.png", content=png, role="character_master")
    second = assets.register_upload(tmp_path / "projects", project_id,
        filename="same.png", content=png, role="character_angle")
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert first["asset_id"] == second["asset_id"]
    assert set(second["roles"]) == {"character_master", "character_angle"}
    assert first["content_url"].endswith(f"/{first['asset_id']}/content")
    result = assets.list_assets(tmp_path / "projects", project_id, role="character_angle")
    assert result["total"] == 1 and result["assets"][0]["filename"] == "portrait.png"
    path, media_type, filename = assets.resolve_content(tmp_path / "projects", tmp_path / "output", project_id, first["asset_id"])
    assert path.is_file() and media_type == "image/png" and filename == "portrait.png"
    assert len(list((tmp_path / "projects" / project_id / "inputs" / "production_assets").glob("*.png"))) == 1


def test_upload_structured_metadata_is_durable_and_conflicts_are_not_silently_overwritten(tmp_path):
    png = _png_bytes()
    metadata = {"dialogue_take": {"run_id": "run-1", "transcript": "We made it."}}
    first = assets.register_upload(tmp_path / "projects", "sample-project", filename="line.png",
        content=png, role="project_image", metadata=metadata)
    repeated = assets.register_upload(tmp_path / "projects", "sample-project", filename="same.png",
        content=png, role="project_image", metadata=metadata)
    assert first["metadata"] == repeated["metadata"] == metadata
    with pytest.raises(assets.ProductionAssetError) as conflict:
        assets.register_upload(tmp_path / "projects", "sample-project", filename="same.png",
            content=png, role="project_image", metadata={"dialogue_take": {"transcript": "Different words."}})
    assert conflict.value.code == "asset_metadata_conflict"


def test_upload_rejects_path_traversal_extensions_magic_bytes_and_wrong_role(tmp_path):
    with pytest.raises(assets.ProductionAssetError) as traversal:
        assets.register_upload(tmp_path / "projects", "../other", filename="x.png", content=_png_bytes(), role="project_image")
    assert traversal.value.code == "invalid_project_id"
    for filename, data, role, code in [
        ("script.py", b"print(1)", "project_audio", "unsupported_asset_format"),
        ("fake.png", b"not png bytes", "project_image", "asset_signature_mismatch"),
        ("sound.wav", b"RIFF0000WAVE", "character_master", "asset_role_type_mismatch"),
    ]:
        with pytest.raises(assets.ProductionAssetError) as error:
            assets.register_upload(tmp_path / "projects", "project", filename=filename, content=data, role=role)
        assert error.value.code == code


def test_video_upload_is_probed_and_corrupt_or_mismatched_media_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.subprocess, "run", _fake_probe)
    content = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + b"body"
    record = assets.register_upload(tmp_path / "projects", "project", filename="clip.mp4",
                                    content=content, role="action_reference_video")
    assert record["media"]["duration_seconds"] == 2.5
    assert record["media"]["streams"][0]["codec_name"] == "h264"

    monkeypatch.setattr(assets.subprocess, "run", lambda *_args, **_kwargs:
        subprocess.CompletedProcess(args=["ffprobe"], returncode=1, stdout="", stderr="invalid input"))
    with pytest.raises(assets.ProductionAssetError) as invalid:
        assets.register_upload(tmp_path / "projects", "project", filename="bad.mp4",
            content=b"\x00\x00\x00\x18ftypmp42bad", role="project_video")
    assert invalid.value.code == "media_probe_failed"
    files = list((tmp_path / "projects" / "project" / "inputs" / "production_assets").glob("*"))
    assert len(files) == 1  # failed probe removed its partial uploaded asset


def test_output_assets_are_indexed_without_copy_and_cannot_escape_output_root(tmp_path):
    source = tmp_path / "output" / "project" / "characters" / "maya.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(_png_bytes())
    registered = assets.register_output(tmp_path / "projects", tmp_path / "output", "project",
                                        relative_path="characters/maya.png", role="character_master")
    assert registered["source"] == "project_output"
    assert source.exists()
    assert not (tmp_path / "projects" / "project" / "inputs").exists()
    with pytest.raises(assets.ProductionAssetError) as outside:
        assets.register_output(tmp_path / "projects", tmp_path / "output", "project",
                               relative_path="../../elsewhere/file.png", role="character_master")
    assert outside.value.code == "asset_output_not_found"


def test_repertoire_links_are_id_only_deduplicated_and_serve_from_owner_url(tmp_path):
    video_asset = {"asset_id": "video-123", "title": "Source clip", "filename": "source.mp4", "sha256": "abc", "size": 10}
    video = assets.link_repertoire_asset(tmp_path / "projects", "project", repertoire_kind="video",
        external_asset_id="video-123", get_video_asset=lambda _asset_id: video_asset, get_audio_assets=lambda: [])
    again = assets.link_repertoire_asset(tmp_path / "projects", "project", repertoire_kind="video",
        external_asset_id="video-123", get_video_asset=lambda _asset_id: video_asset, get_audio_assets=lambda: [])
    assert video["deduplicated"] is False and again["deduplicated"] is True
    assert video["source"] == "external_video_repertoire_video"
    assert video["content_url"] == "/api/video-repertoire/assets/video-123/content"
    assert not (tmp_path / "projects" / "project" / "inputs").exists()

    audio = assets.link_repertoire_asset(tmp_path / "projects", "project", repertoire_kind="audio",
        external_asset_id="audio-44", get_video_asset=lambda _asset_id: {}, get_audio_assets=lambda: [
            {"asset_id": "audio-44", "available": True, "category": "music", "content_url": "/api/video-repertoire/audio-assets/content/music/ref.wav"}])
    assert audio["content_url"].endswith("/music/ref.wav")
    with pytest.raises(assets.ProductionAssetError) as missing:
        assets.link_repertoire_asset(tmp_path / "projects", "project", repertoire_kind="audio",
            external_asset_id="missing", get_video_asset=lambda _asset_id: {}, get_audio_assets=lambda: [])
    assert missing.value.code == "repertoire_asset_not_found"


def test_content_resolution_refuses_tampered_manifest_paths(tmp_path):
    result = assets.register_upload(tmp_path / "projects", "project", filename="a.png", content=_png_bytes(), role="project_image")
    root = tmp_path / "projects" / "project"
    manifest_path = root / "production" / "assets.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["assets"][0]["relative_path"] = "../../outside.png"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(assets.ProductionAssetError) as error:
        assets.resolve_content(tmp_path / "projects", tmp_path / "output", "project", result["asset_id"])
    assert error.value.code == "unsafe_asset_path"


def test_asset_index_pagination_and_invalid_filters(tmp_path):
    png = _png_bytes()
    for index in range(3):
        image = io.BytesIO()
        Image.new("RGB", (index + 1, 2), color=(index, 80, 120)).save(image, format="PNG")
        assets.register_upload(tmp_path / "projects", "project", filename=f"{index}.png", content=image.getvalue(), role="project_image")
    page = assets.list_assets(tmp_path / "projects", "project", kind="image", limit=2, offset=1)
    assert page["total"] == 3 and len(page["assets"]) == 2
    with pytest.raises(assets.ProductionAssetError) as filter_error:
        assets.list_assets(tmp_path / "projects", "project", kind="image/../../", limit=20)
    assert filter_error.value.code == "invalid_asset_filter"
