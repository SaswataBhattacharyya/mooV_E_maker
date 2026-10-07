"""Opt-in live smoke for dynamic local H3 R2V; leaves one reviewed output.

Run from the repository root with:
  PYTHONPATH=/home/riki/web_dev python3 scripts/smoke_minimax_h3_dynamic.py

This script uses the small project fixtures named below, stages only temporary
ComfyUI input copies, requires an idle ComfyUI queue and at least 20 GiB free
according to ComfyUI, saves its final result under one disposable output
project, removes only this run's ComfyUI output after a hash-verified copy,
and asks ComfyUI to release models after the queue returns to idle.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from story_builder.services.audio_catalog import comfyui_root
from story_builder.services.media_jobs import MediaJobError, collect_outputs, submit_and_wait
from story_builder.services.minimax_h3_graph_compiler import (
    AudioReference, ImageReference, ReferencePlan, ResolvedAsset, VideoReference,
    compile_r2v_graph, load_base_graph, validate_comfy_capabilities,
)
from story_builder.services.minimax_h3_media import (
    cleanup_owned_media, probe_media, sha256_file, stage_audio_reference,
    stage_image_reference, stage_video_reference,
)


ROOT = Path(__file__).resolve().parents[1]
COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3008").rstrip("/")
PROJECT_ID = "disposable-h3-reference-smoke"
VIDEO_FIXTURE = ROOT / "plan" / "Brother eww what’s that？💀 #meme.mp4"
IMAGE_FIXTURE = ROOT / "plan" / "image.png"
VOICE_FIXTURE = ROOT / "audio" / "StyleTTS2_app" / "outputs" / "Dipa.mp3"
MIN_FREE_VRAM = 20 * 1024**3


def request_json(path: str, *, timeout: int = 10) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ComfyUI preflight failed at {path}: {type(exc).__name__}: {exc}") from exc


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_model_files(graph: dict[str, Any], model_root: Path) -> list[dict[str, str]]:
    subdirs = {"UNETLoader": "diffusion_models", "CLIPLoader": "text_encoders", "VAELoader": "vae"}
    found: list[dict[str, str]] = []
    for node in graph.values():
        class_type = node.get("class_type")
        key = {"UNETLoader": "unet_name", "CLIPLoader": "clip_name", "VAELoader": "vae_name"}.get(class_type)
        if not key:
            continue
        filename = str(node.get("inputs", {}).get(key, ""))
        path = model_root / subdirs[class_type] / filename
        if not filename or not path.is_file():
            raise RuntimeError(f"Required H3 model file is unavailable: {path}")
        found.append({"node": class_type, "filename": filename})
    return found


def remove_hash_verified_comfy_outputs(history: dict[str, Any], *, comfy_output_root: Path,
                                       run_id: str, copied_outputs: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Remove only verified copies; report retained files without failing a completed render."""
    output_root = comfy_output_root.resolve()
    copied_paths = [Path(row["absolute_path"]).resolve() for row in copied_outputs if row.get("absolute_path")]
    # ComfyUI returns the base subfolder without a trailing slash when the
    # generated filename itself is a direct child of that folder.
    owned_subfolder = f"story_builder/{run_id}"
    removed: list[str] = []
    retained: list[dict[str, str]] = []
    for node_output in history.get("outputs", {}).values():
        records = list(node_output.get("images", [])) + list(node_output.get("gifs", [])) + list(node_output.get("videos", [])) + list(node_output.get("audio", [])) + list(node_output.get("audios", []))
        for record in records:
            if record.get("type", "output") != "output":
                continue
            subfolder = str(record.get("subfolder", ""))
            filename = str(record.get("filename", ""))
            relative = Path(subfolder) / filename
            source = (output_root / relative).resolve()
            try:
                source.relative_to(output_root)
            except ValueError:
                continue
            if not source.is_file() or not (
                subfolder == owned_subfolder or subfolder.startswith(owned_subfolder + "/")
            ):
                continue
            matching_copy = next((target for target in copied_paths if target.name.endswith("_" + source.name)), None)
            if matching_copy is None or not matching_copy.is_file():
                continue
            if sha256_file(source) != sha256_file(matching_copy):
                continue
            try:
                source.unlink()
                removed.append(str(relative))
            except OSError as exc:
                # The project-owned output is already safely copied. ComfyUI may
                # own its output directory under another UID; never change its
                # permissions or turn a successful render into a failed job.
                retained.append({
                    "path": str(relative),
                    "reason": f"{type(exc).__name__}: {exc}",
                })
    return {"removed": removed, "retained": retained}


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Publish a complete recovery record before starting the remote render."""
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one guarded disposable dynamic H3 R2V render.")
    parser.add_argument("--preview", action="store_true",
        help="Use a reduced 0.4 MP, 5-second, 8-step preview; does not change production defaults.")
    parser.add_argument("--case", choices=("mixed_reference", "voice_only", "image_voice",
        "video_no_audio", "paired_video_two_voices", "previous_cut_continuity"), default="mixed_reference",
        help="Run one exact disposable reference combination; only selected fixtures are staged.")
    parser.add_argument("--reference-video", type=Path, default=None,
        help="Optional source MP4 for video cases; previous_cut_continuity uses this as the preceding generated cut.")
    args = parser.parse_args()
    render_profile = ({"name": "preview", "resolution_preset": 0.4, "duration_seconds": 5.0, "steps": 8}
                      if args.preview else
                      {"name": "final", "resolution_preset": 0.98, "duration_seconds": 5.0, "steps": 20})
    run_id = f"phase-a-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    shot_id = "smoke-shot-1"
    comfy_root = comfyui_root()
    comfy_input = Path(os.environ.get("COMFYUI_INPUT_DIR", str(comfy_root / "input"))).resolve()
    owner_root = ROOT / "storage" / "projects" / PROJECT_ID / "comfy_staging"
    output_root = ROOT / "output" / PROJECT_ID / "runs" / run_id
    output_root.mkdir(parents=True, exist_ok=False)
    manifest_path = output_root / "manifest.json"
    started = time.monotonic()
    manifest: dict[str, Any] = {
        "schema_version": 1, "status": "preflight", "project_id": PROJECT_ID,
        "run_id": run_id, "shot_id": shot_id, "comfyui_url": COMFY_URL,
        "started_at": datetime.now(timezone.utc).isoformat(), "staged_assets": [],
        "outputs": [], "cleanup": {}, "render_profile": render_profile,
        "smoke_case": args.case,
    }
    history: dict[str, Any] | None = None
    submission_may_be_live = False
    try:
        needs_video = args.case in {"mixed_reference", "video_no_audio", "paired_video_two_voices", "previous_cut_continuity"}
        needs_image = args.case in {"mixed_reference", "image_voice"}
        voice_count = {"mixed_reference": 1, "voice_only": 1, "image_voice": 1,
                       "video_no_audio": 0, "paired_video_two_voices": 2,
                       "previous_cut_continuity": 0}[args.case]
        reference_video = (args.reference_video.resolve() if args.reference_video else VIDEO_FIXTURE)
        required_fixtures = ([reference_video] if needs_video else []) + ([IMAGE_FIXTURE] if needs_image else []) + ([VOICE_FIXTURE] if voice_count else [])
        if not all(path.is_file() for path in required_fixtures):
            missing = [str(path) for path in required_fixtures if not path.is_file()]
            raise RuntimeError(f"Required disposable smoke fixture(s) missing: {missing}")
        stats = request_json("/system_stats")
        devices = stats.get("devices", [])
        if not devices:
            raise RuntimeError("ComfyUI reports no compute device; refusing to submit the GPU smoke.")
        device = devices[0]
        free_vram = int(device.get("vram_free", 0))
        if free_vram < MIN_FREE_VRAM:
            raise RuntimeError(f"Only {free_vram / 1024**3:.1f} GiB free in ComfyUI device report; at least 20 GiB is required for this guarded smoke.")
        manifest["comfyui"] = {"version": stats.get("system", {}).get("comfyui_version"),
                                "python": stats.get("system", {}).get("python_version"),
                                "torch": stats.get("system", {}).get("pytorch_version"),
                                "device": device.get("name"), "vram_total_bytes": device.get("vram_total"),
                                "vram_free_before_bytes": free_vram}
        queue = request_json("/queue")
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise RuntimeError(f"ComfyUI queue is not idle; smoke was not submitted: running={len(queue.get('queue_running', []))}, pending={len(queue.get('queue_pending', []))}.")
        node_names = ("MiniMaxH3ReferenceToVideo", "LoadImage", "LoadAudio", "VHS_LoadVideo", "CreateVideo", "SaveVideo")
        object_info = {name: request_json(f"/object_info/{name}")[name] for name in node_names}
        manifest["capabilities"] = validate_comfy_capabilities(object_info)
        base_graph = load_base_graph()
        manifest["models"] = verify_model_files(base_graph, comfy_root / "models")

        staged_assets: list[dict[str, Any]] = []
        images: list[ImageReference] = []
        videos: list[VideoReference] = []
        standalone_audios: list[AudioReference] = []
        asset_index: dict[str, ResolvedAsset] = {}
        if needs_image:
            image = stage_image_reference(IMAGE_FIXTURE, asset_id="fixture-image", owner_id=run_id,
                                          comfy_input_dir=comfy_input, owner_root=owner_root)
            staged_assets.append({"asset_id": image.asset_id, "kind": "image", "filename": image.filename, "sha256": image.sha256})
            asset_index[image.asset_id] = ResolvedAsset(image.asset_id, "image", image.filename, image.sha256)
            images.append(ImageReference(image.asset_id, "appearance_reference", "Use visual appearance only."))
        if needs_video:
            paired = args.case in {"mixed_reference", "paired_video_two_voices", "previous_cut_continuity"}
            previous_cut = args.case == "previous_cut_continuity"
            source_probe = probe_media(reference_video)
            video_start = 0.0 if previous_cut else 0.2
            video_end = min(5.2, source_probe.duration_seconds)
            video_asset_id = "previous-approved-cut" if previous_cut else "fixture-video"
            video_role = "previous_cut_state" if previous_cut else "motion_camera_reference"
            video_intent = ("Use the approved preceding cut for same-scene state, screen direction and camera continuity; generate the next beat rather than repeating it."
                            if previous_cut else "Transfer motion and camera timing.")
            video = stage_video_reference(reference_video, asset_id=video_asset_id, owner_id=run_id,
                comfy_input_dir=comfy_input, owner_root=owner_root, start_sec=video_start,
                end_sec=video_end, include_audio=paired)
            staged_assets.append({"asset_id": video.asset_id, "kind": "video", "filename": video.filename,
                "sha256": video.sha256, "interval": [video.source_start_sec, video.source_end_sec],
                "paired_audio": video.has_audio, "fps": video.fps})
            asset_index[video.asset_id] = ResolvedAsset(video.asset_id, "video", video.filename,
                video.sha256, video.source_start_sec, video.source_end_sec, video.has_audio)
            videos.append(VideoReference(video.asset_id, video_role,
                video_intent, video.source_start_sec, video.source_end_sec,
                paired, "Use the preceding cut's sound only for continuity; do not repeat its dialogue." if previous_cut else
                ("Use source ambience and timing, not its dialogue." if paired else None)))
        for index in range(voice_count):
            asset_id = "fixture-voice" if voice_count == 1 else f"fixture-voice-s{index + 1}"
            voice = stage_audio_reference(VOICE_FIXTURE, asset_id=asset_id, owner_id=run_id,
                comfy_input_dir=comfy_input, owner_root=owner_root, start_sec=0.0, end_sec=5.0)
            staged_assets.append({"asset_id": voice.asset_id, "kind": "standalone_audio",
                "filename": voice.filename, "sha256": voice.sha256, "duration_seconds": voice.duration_seconds})
            asset_index[voice.asset_id] = ResolvedAsset(voice.asset_id, "audio", voice.filename, voice.sha256)
            standalone_audios.append(AudioReference(voice.asset_id, "voice_timbre", "Voice timbre only.", f"S{index + 1}"))
        manifest["staged_assets"] = staged_assets

        prompt_parts = ["[reference generation + audio reference]"]
        if images:
            prompt_parts.append("<Picture 1> is a visual appearance reference.")
        if videos:
            if args.case == "previous_cut_continuity":
                prompt_parts.append("<Video 1> is the immediately preceding approved cut from the same scene; preserve current character state, environment, screen direction and camera continuity while generating the next beat rather than repeating the prior action.")
            else:
                prompt_parts.append("<Video 1> provides motion, camera movement and timing.")
        audio_index = 1
        if videos and videos[0].include_paired_soundtrack:
            prompt_parts.append("<Audio 1> is the synchronized soundtrack of <Video 1>; use its ambience and timing only.")
            audio_index = 2
        for index, audio in enumerate(standalone_audios):
            prompt_parts.append(f"<Audio {audio_index + index}> is a clean voice-timbre reference for the visible speaker ({audio.speaker_id}); do not repeat its source words.")
        prompt_parts.append("Generate one short cinematic shot with one clear movement, stable framing and natural lighting. No new spoken words are required.")
        prompt = " ".join(prompt_parts)
        plan = ReferencePlan(
            schema_version=1, project_id=PROJECT_ID, run_id=run_id, shot_id=shot_id,
            prompt=prompt, duration_seconds=render_profile["duration_seconds"],
            resolution_preset=render_profile["resolution_preset"],
            aspect_ratio="16:9", steps=render_profile["steps"], ref_image_size="match", seed=20261001,
            images=tuple(images), videos=tuple(videos), standalone_audios=tuple(standalone_audios),
        )
        compiled = compile_r2v_graph(plan, asset_index, base_graph=base_graph)
        manifest.update({"status": "compiled", "reference_map": compiled.reference_map.as_dict(),
                         "resolution": [compiled.width, compiled.height], "fps": 24,
                         "frame_count": compiled.frame_count, "graph_sha256": sha256_json(compiled.graph),
                         "model_files": manifest["models"]})
        (output_root / "compiled_graph.json").write_text(json.dumps(compiled.graph, indent=2), encoding="utf-8")
        write_manifest(manifest_path, manifest)
        # Recheck shared queue immediately before submission; do not interfere with another UI/user.
        queue = request_json("/queue")
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise RuntimeError("ComfyUI queue became busy after preflight; this smoke was not submitted.")
        # Reserve and persist the exact remote ID before POST, including when
        # the response is lost or the host restarts while the GPU is rendering.
        reserved_prompt_id = str(uuid.uuid4())
        manifest.update({"status": "submitting", "comfy_prompt_id": reserved_prompt_id})
        write_manifest(manifest_path, manifest)
        submission_may_be_live = True
        prompt_id, history = submit_and_wait(dict(compiled.graph), comfy_url=COMFY_URL,
                                            timeout_seconds=3600, prompt_id=reserved_prompt_id,
                                            telemetry_path=output_root / "gpu_telemetry.jsonl",
                                            workload_id=run_id)
        submission_may_be_live = False
        collected = collect_outputs(history, destination_dir=output_root / "media", comfy_url=COMFY_URL)
        output_rows = []
        for row in collected:
            path = output_root / "media" / row["relative_path"]
            item = {**row, "absolute_path": str(path.resolve()), "sha256": sha256_file(path) if path.is_file() else None}
            if row["kind"] == "video" and path.is_file():
                probe = probe_media(path)
                item["probe"] = {"duration_seconds": probe.duration_seconds, "width": probe.width,
                                 "height": probe.height, "fps": probe.frame_rate, "has_audio": probe.has_audio,
                                 "audio_codec": probe.audio_codec}
            output_rows.append(item)
        if not any(row.get("kind") == "video" and row.get("probe", {}).get("has_audio") for row in output_rows):
            raise RuntimeError(f"H3 smoke completed but no collected playable video with native audio was found. Outputs: {output_rows}")
        comfy_output_cleanup = remove_hash_verified_comfy_outputs(
            history, comfy_output_root=comfy_root / "output", run_id=run_id,
            copied_outputs=output_rows)
        manifest.update({"status": "completed", "comfy_prompt_id": prompt_id,
                         "outputs": output_rows,
                         "removed_comfy_output_duplicates": comfy_output_cleanup["removed"],
                         "retained_comfy_output_duplicates": comfy_output_cleanup["retained"],
                         "elapsed_seconds": round(time.monotonic() - started, 2)})
        print(json.dumps({"status": "completed", "manifest": str(manifest_path),
                          "outputs": output_rows, "reference_map": compiled.reference_map.as_dict(),
                          "removed_comfy_output_duplicates": comfy_output_cleanup["removed"],
                          "retained_comfy_output_duplicates": comfy_output_cleanup["retained"]}, indent=2))
        return 0
    except KeyboardInterrupt:
        manifest.update({"status": "recovery_pending" if submission_may_be_live else "interrupted", "failure": {
            "type": "KeyboardInterrupt",
            "message": "Smoke client was interrupted; reconcile the saved prompt ID before retrying if submission was attempted.",
        }, "elapsed_seconds": round(time.monotonic() - started, 2)})
        print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path),
                          "failure": manifest["failure"]}, indent=2))
        return 130
    except Exception as exc:
        if isinstance(exc, MediaJobError):
            submission_may_be_live = exc.remote_state_unknown
            if exc.prompt_id:
                manifest["comfy_prompt_id"] = exc.prompt_id
        manifest.update({"status": "recovery_pending" if submission_may_be_live else "failed",
                         "failure": {"type": type(exc).__name__, "message": str(exc)},
                         "elapsed_seconds": round(time.monotonic() - started, 2)})
        print(json.dumps({"status": manifest["status"], "manifest": str(manifest_path), "failure": manifest["failure"]}, indent=2))
        return 1
    finally:
        if submission_may_be_live:
            # The remote job can still need these inputs after this client exits.
            manifest["cleanup"] = {"status": "deferred", "reason": "remote_prompt_state_unknown"}
        else:
            try:
                manifest["cleanup"] = cleanup_owned_media(run_id, comfy_input_dir=comfy_input, owner_root=owner_root)
            except Exception as cleanup_error:
                manifest["cleanup"] = {"status": "failed", "error": f"{type(cleanup_error).__name__}: {cleanup_error}"}
        # submit_and_wait already releases models after confirmed completion,
        # while holding the submission lease. Do not issue a second global unload
        # here, especially after preflight failure or an ambiguous submission.
        manifest["model_release"] = {"status": "handled_by_submit_and_wait" if history is not None else "not_requested"}
        write_manifest(manifest_path, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
