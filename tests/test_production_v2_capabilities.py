from pathlib import Path
import asyncio

from story_builder.services import production_v2_capabilities as capabilities


def _make_required_files(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    (project_root / "workflows" / "api").mkdir(parents=True)
    (project_root / "workflows" / "api" / "minimax_h3_r2v_api.json").write_text("{}")
    comfy = tmp_path / "comfy"
    for relative in (
        "models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "models/vae/minimax_h3_video_vae_fp16.safetensors",
        "models/vae/minimax_h3_audio_vae_fp32.safetensors",
    ):
        path = comfy / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(capabilities, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(capabilities, "comfyui_root", lambda: comfy)
    monkeypatch.setattr(capabilities, "_last_live_smoke", lambda: {
        "status": "completed", "has_audio": True, "resolution": [1344, 768],
        "fps": 24, "duration_seconds": 5.167, "run_id": "test-run",
    })


def test_dynamic_capability_is_fail_closed_by_default(monkeypatch, tmp_path: Path) -> None:
    _make_required_files(tmp_path, monkeypatch)
    monkeypatch.delenv(capabilities.FEATURE_FLAG, raising=False)

    result = capabilities.dynamic_h3_capability()

    assert result["workflow_id"] == "minimax_h3_r2v_dynamic_v1"
    assert result["feature_enabled"] is False
    assert result["available"] is False
    assert capabilities.FEATURE_FLAG in result["disabled_reason"]


def test_dynamic_capability_requires_files_and_live_smoke(monkeypatch, tmp_path: Path) -> None:
    _make_required_files(tmp_path, monkeypatch)
    monkeypatch.setenv(capabilities.FEATURE_FLAG, "true")

    assert capabilities.dynamic_h3_capability()["available"] is True

    monkeypatch.setattr(capabilities, "_last_live_smoke", lambda: None)
    result = capabilities.dynamic_h3_capability()
    assert result["available"] is False
    assert "No successful live H3" in result["disabled_reason"]


def test_new_catalog_keeps_legacy_workflow_entries(monkeypatch) -> None:
    monkeypatch.delenv(capabilities.FEATURE_FLAG, raising=False)
    from story_builder.api.main import production_v2_workflows

    result = asyncio.run(production_v2_workflows())
    workflow_ids = {item["workflow_id"] for item in result}

    assert "minimax_h3_r2v_dynamic_v1" in workflow_ids
    assert "minimax_references" in workflow_ids
    dynamic = next(item for item in result if item["workflow_id"] == "minimax_h3_r2v_dynamic_v1")
    assert dynamic["available"] is False
