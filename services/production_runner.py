"""Dependency-ordered, two-scene production runner.

This runner deliberately uses only the already verified adapters. It keeps
every request/output in the project workspace and records retry/timing and
reference provenance instead of hiding failed media stages.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .control_foley import new_job as new_foley_job, run_job as run_foley_job
from .media_jobs import collect_outputs, submit_and_wait
from .music_sound import new_music_job, run_music_job
from .project_graph import update_artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_fixture(root: Path) -> Path:
    candidate = root / "plan" / "image.png"
    if not candidate.is_file():
        raise RuntimeError("Production fixture image is missing: plan/image.png")
    return candidate


def _video_workflow(root: Path, project_id: str, scene_id: str, prompt: str, refs: list[str], length: int, seed: int) -> dict[str, Any]:
    workflow = json.loads((root / "workflows/api/minimax_h3_r2v_api.json").read_text(encoding="utf-8"))
    for node, image in zip(("101", "102", "103"), refs):
        workflow[node]["inputs"]["image"] = image
    workflow["136"]["inputs"].update(prompt=prompt, length=length)
    workflow["124"]["inputs"]["steps"] = 20
    workflow["129"]["inputs"]["noise_seed"] = seed
    workflow["92"]["inputs"]["filename_prefix"] = f"story_builder/{project_id}/{scene_id}"
    return workflow


def _mux(video: Path, music: Path, foley: Path | None, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if foley and foley.is_file():
        command = ["ffmpeg", "-y", "-i", str(video), "-i", str(music), "-i", str(foley), "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest:dropout_transition=2[a]", "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(target)]
    else:
        command = ["ffmpeg", "-y", "-i", str(video), "-i", str(music), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(target)]
    subprocess.run(command, check=True, capture_output=True, timeout=900)


def run_production(*, root: Path, project_id: str, project_dir: Path, output_root: Path, comfy_input_dir: Path, comfy_url: str,
                   story: dict[str, Any], characters: dict[str, Any], scenes: dict[str, Any], director: dict[str, Any],
                   update: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    run = {"run_id": f"production-{uuid.uuid4().hex[:10]}", "status": "running", "progress": 0, "stage": "preparing", "started_at": _now(), "scenes": [], "error": None}
    update(run)
    work = project_dir / "production" / run["run_id"]; work.mkdir(parents=True, exist_ok=True)
    try:
        fixture = _source_fixture(root)
        refs_dir = work / "references"; refs_dir.mkdir(parents=True, exist_ok=True)
        refs: list[str] = []
        for index in range(1, 4):
            name = f"{project_id}_{run['run_id']}_reference_{index}.png"
            target = comfy_input_dir / name; shutil.copy2(fixture, target); refs.append(name)
            shutil.copy2(fixture, refs_dir / f"reference-{index}.png")

        # Prefer a real ACE-Step music job. The supplied fixture is a safe,
        # provenance-preserving fallback when ACE is unavailable or fails.
        music_source = root / "plan" / "ChatterBox + F5-TTS ？ - ChatterBox SRT Voice TTS Node v3.2! - ComfyUI.mp3"
        if not music_source.is_file(): raise RuntimeError("Music fixture is missing from plan/")
        music = work / "music.mp3"; music_generated = False
        try:
            ace = run_music_job(new_music_job({"mode": "instrumental", "tags": "cinematic rain, urgent strings, restrained hopeful resolution", "duration": 5, "seed": 717, "steps": 20, "cfg": 4.5}), project_dir=project_dir, output_root=output_root, comfy_url=comfy_url, progress=lambda _: None)
            ace_path = Path(ace.get("export_path")) if ace.get("export_path") else None
            if ace_path and ace_path.is_file():
                shutil.copy2(ace_path, music); music_generated = True
            else:
                shutil.copy2(music_source, music)
        except Exception:
            shutil.copy2(music_source, music)
        output_audio = output_root / project_id / "audio" / "production_music.mp3"; output_audio.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(music, output_audio)

        foley = new_foley_job({"mode": "text_audio", "prompt": "A short rain-soaked metal latch and station door impact", "duration": .7, "seed": 4242, "steps": "fixed", "guidance": 4.5, "fps": 24})
        # No input media is needed for text_audio.
        foley = run_foley_job(foley, project_dir=project_dir, output_root=output_root, comfy_url=comfy_url, progress=lambda j: update({**run, "stage": "foley", "progress": 12, "foley_status": j.get("status")}))
        foley_path = Path(foley.get("export_path")) if foley.get("export_path") else None

        shot_rows = director.get("shots") if isinstance(director, dict) else None
        if not isinstance(shot_rows, list) or len(shot_rows) < 2:
            shot_rows = [{"shot_id": "scene-001-shot-001", "scene_id": "scene-001", "duration_seconds": 2, "start_frame_brief": "", "end_frame_brief": "", "camera": "medium tracking shot", "lighting": "soft overcast"}, {"shot_id": "scene-002-shot-001", "scene_id": "scene-002", "duration_seconds": 2, "start_frame_brief": "", "end_frame_brief": "", "camera": "wide establishing shot", "lighting": "warm practicals"}]
        scenes_by_id = {str(item.get("id")): item for item in scenes.get("scenes", []) if isinstance(item, dict)}
        selected: list[dict[str, Any]] = []
        seen_scenes: set[str] = set()
        for candidate in shot_rows:
            candidate_scene = str(candidate.get("scene_id") or "")
            if candidate_scene and candidate_scene not in seen_scenes:
                selected.append(candidate); seen_scenes.add(candidate_scene)
            if len(selected) == 2:
                break
        if len(selected) < 2:
            for candidate in shot_rows:
                if candidate not in selected:
                    selected.append(candidate)
                if len(selected) == 2:
                    break
        for index, shot in enumerate(selected, start=1):
            scene_id = str(shot.get("scene_id") or f"scene-{index:03d}")
            source_scene = scenes_by_id.get(scene_id, {})
            prompt = " ".join(str(value) for value in (source_scene.get("summary", ""), shot.get("camera", ""), shot.get("lighting", ""), shot.get("tone", ""), shot.get("emotion", ""), shot.get("blocking", "")) if value).strip()
            row = {"scene_id": scene_id, "shot_id": shot.get("shot_id", f"scene-{index:03d}-shot-001"), "duration_seconds": float(shot.get("duration_seconds", 2)), "references": list(refs), "attempts": 0, "status": "running", "timing": {"audio_source": str(output_audio.relative_to(output_root / project_id)), "start_seconds": 0, "end_seconds": float(shot.get("duration_seconds", 2))}}
            for attempt in range(1, 3):
                row["attempts"] = attempt
                try:
                    workflow = _video_workflow(root, project_id, scene_id, prompt, refs, 24, 1000 + index + attempt)
                    request_path = work / f"{scene_id}.attempt-{attempt}.json"; request_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
                    _, history = submit_and_wait(workflow, comfy_url=comfy_url, timeout_seconds=1800)
                    outputs = collect_outputs(history, destination_dir=work / scene_id, comfy_url=comfy_url)
                    video = next((work / scene_id / item["filename"] for item in outputs if item.get("kind") == "video"), None)
                    if not video: raise RuntimeError("Minimax returned no video output")
                    final = output_root / project_id / "scenes" / f"{scene_id}.mp4"; _mux(video, music, foley_path, final)
                    row.update(status="completed", output=str(final.relative_to(output_root / project_id)), prompt=prompt); break
                except Exception as exc:
                    row.update(status="retrying" if attempt == 1 else "failed", error=str(exc))
            run["scenes"].append(row); update({**run, "stage": f"scene_{index}", "progress": 12 + index * 42})
            if row["status"] != "completed": raise RuntimeError(f"{scene_id} failed after {row['attempts']} attempts: {row.get('error')}")

        manifest = {"schema_version": 1, "project_id": project_id, "run_id": run["run_id"], "story": story.get("title"), "characters": [item.get("id") for item in characters.get("characters", []) if isinstance(item, dict)], "scenes": run["scenes"], "references": refs, "music": {"path": str(output_audio.relative_to(output_root / project_id)), "generated_by_ace_step": music_generated}, "director_contract": director.get("director_contract", {}), "created_at": _now()}
        manifest_path = output_root / project_id / "production_manifest.json"; manifest_path.parent.mkdir(parents=True, exist_ok=True); manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        update_artifact(project_dir, "production_manifest", manifest)
        run.update(status="completed", stage="completed", progress=100, manifest_path=str(manifest_path), completed_at=_now())
    except Exception as exc:
        run.update(status="failed", stage="failed", error=str(exc), completed_at=_now())
    update(run)
    return run
