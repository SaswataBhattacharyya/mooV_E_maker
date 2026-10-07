from pathlib import Path

from scripts.smoke_minimax_h3_dynamic import remove_hash_verified_comfy_outputs


def test_removes_only_hash_verified_output_in_owned_run_folder(tmp_path: Path) -> None:
    comfy_output = tmp_path / "comfy-output"
    run_folder = comfy_output / "story_builder" / "run-123"
    run_folder.mkdir(parents=True)
    comfy_copy = run_folder / "shot_00001_.mp4"
    comfy_copy.write_bytes(b"same bytes")
    project_copy = tmp_path / "project" / "uuid_shot_00001_.mp4"
    project_copy.parent.mkdir()
    project_copy.write_bytes(b"same bytes")

    cleanup = remove_hash_verified_comfy_outputs(
        {"outputs": {"save": {"images": [{
            "filename": comfy_copy.name,
            "subfolder": "story_builder/run-123",
            "type": "output",
        }]}}},
        comfy_output_root=comfy_output,
        run_id="run-123",
        copied_outputs=[{"absolute_path": str(project_copy)}],
    )

    assert cleanup == {"removed": ["story_builder/run-123/shot_00001_.mp4"], "retained": []}
    assert not comfy_copy.exists()
    assert project_copy.read_bytes() == b"same bytes"


def test_does_not_remove_other_run_or_hash_mismatch(tmp_path: Path) -> None:
    comfy_output = tmp_path / "comfy-output"
    other_folder = comfy_output / "story_builder" / "other-run"
    other_folder.mkdir(parents=True)
    comfy_copy = other_folder / "shot.mp4"
    comfy_copy.write_bytes(b"comfy bytes")
    project_copy = tmp_path / "project" / "uuid_shot.mp4"
    project_copy.parent.mkdir()
    project_copy.write_bytes(b"different bytes")

    cleanup = remove_hash_verified_comfy_outputs(
        {"outputs": {"save": {"images": [{
            "filename": comfy_copy.name,
            "subfolder": "story_builder/other-run",
            "type": "output",
        }]}}},
        comfy_output_root=comfy_output,
        run_id="run-123",
        copied_outputs=[{"absolute_path": str(project_copy)}],
    )

    assert cleanup == {"removed": [], "retained": []}
    assert comfy_copy.read_bytes() == b"comfy bytes"


def test_permission_error_retains_comfy_copy_without_failing_render(tmp_path: Path, monkeypatch) -> None:
    comfy_output = tmp_path / "comfy-output"
    run_folder = comfy_output / "story_builder" / "run-456"
    run_folder.mkdir(parents=True)
    comfy_copy = run_folder / "shot_00001_.mp4"
    comfy_copy.write_bytes(b"same bytes")
    project_copy = tmp_path / "project" / "uuid_shot_00001_.mp4"
    project_copy.parent.mkdir()
    project_copy.write_bytes(b"same bytes")

    original_unlink = Path.unlink

    def denied_unlink(path: Path, *args, **kwargs):
        if path == comfy_copy:
            raise PermissionError("not owned by analyzer user")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied_unlink)
    cleanup = remove_hash_verified_comfy_outputs(
        {"outputs": {"save": {"videos": [{
            "filename": comfy_copy.name,
            "subfolder": "story_builder/run-456",
            "type": "output",
        }]}}},
        comfy_output_root=comfy_output,
        run_id="run-456",
        copied_outputs=[{"absolute_path": str(project_copy)}],
    )

    assert cleanup["removed"] == []
    assert cleanup["retained"] == [{
        "path": "story_builder/run-456/shot_00001_.mp4",
        "reason": "PermissionError: not owned by analyzer user",
    }]
    assert comfy_copy.read_bytes() == b"same bytes"
    assert project_copy.read_bytes() == b"same bytes"
