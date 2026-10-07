from __future__ import annotations

import json
import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_builder.services import video_repertoire as repertoire


def make_video(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


class VideoRepertoireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repertoire"
        self.legacy = Path(self.temporary.name) / "legacy"
        self.legacy.mkdir()
        self.root_patch = patch.object(repertoire, "REPERTOIRE_ROOT", self.root)
        self.legacy_patch = patch.object(repertoire, "LEGACY_VIDEO_ROOT", self.legacy)
        self.root_patch.start(); self.legacy_patch.start()

    def tearDown(self) -> None:
        self.root_patch.stop(); self.legacy_patch.stop(); self.temporary.cleanup()

    def test_registers_and_deduplicates_asset_by_hash(self):
        video = self.legacy / "sample.mp4"; make_video(video)
        first = repertoire.register_asset(video, source_mode="legacy")
        second = repertoire.register_asset(video, source_mode="legacy")
        self.assertEqual(first["asset_id"], second["asset_id"])
        self.assertEqual(len(repertoire.list_assets()), 1)
        self.assertEqual(first["media"]["width"], 160)

    def test_rejects_path_outside_approved_roots(self):
        outside = Path(self.temporary.name) / "outside.mp4"; make_video(outside)
        with self.assertRaises(ValueError):
            repertoire.register_asset(outside, source_mode="legacy")

    def test_pasted_urls_are_validated_and_deduplicated(self):
        result = repertoire.resolve_youtube_sources(mode="paste", urls_text="https://youtu.be/one\nhttps://youtu.be/one\nhttps://youtu.be/two")
        self.assertEqual(len(result["candidates"]), 2)
        with self.assertRaises(ValueError):
            repertoire.resolve_youtube_sources(mode="paste", urls_text="not-a-url")

    def test_job_lifecycle_and_interrupted_recovery(self):
        job = repertoire.create_job("analysis", {"asset_ids": ["video-one"]})
        stored = repertoire.read_job("analysis", job["job_id"])
        self.assertEqual(stored["status"], "queued")
        stored.update(status="running", pid=99999999)
        repertoire._atomic_json(repertoire.job_path("analysis", job["job_id"]), stored)
        recovered = repertoire.read_job("analysis", job["job_id"])
        self.assertEqual(recovered["status"], "interrupted")

    def test_stop_analysis_job_removes_only_job_owned_outputs_and_keeps_source(self):
        repertoire.ensure_layout()
        source = self.root / "uploads" / "source.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"source-video")
        asset = {"asset_id": "video-owned", "path": str(source), "analysis_ids": []}
        repertoire._atomic_json(repertoire.asset_manifest_path("video-owned"), asset)
        job = repertoire.create_job("analysis", {"asset_ids": ["video-owned"]})
        job_id = job["job_id"]
        job["status"] = "running"
        job["result"] = {"videos": [], "audio_analysis": [{"run_id": "video-owned-run"}]}
        repertoire._atomic_json(repertoire.job_path("analysis", job_id), job)
        job_dir = repertoire.job_path("analysis", job_id).parent
        (job_dir / "worker.log").write_text("log")
        own_output = self.root / "analyses" / job_id
        own_output.mkdir(parents=True)
        (own_output / "partial.json").write_text("partial")
        own_clip = self.root / "clips" / "video-owned" / f"{job_id}_scene_1.mp4"
        shared_clip = self.root / "clips" / "video-owned" / "other-job_scene_1.mp4"
        own_clip.parent.mkdir(parents=True)
        own_clip.write_bytes(b"own")
        shared_clip.write_bytes(b"shared")
        analyzer_run = repertoire.analyzer_runs_root() / "video-owned-run"
        analyzer_run.mkdir(parents=True)
        (analyzer_run / "job_owner.json").write_text(json.dumps({"job_id": job_id}))
        promoted = self.root / "manifests" / "analyzer-runs" / "video-owned-run.json"
        promoted.parent.mkdir(parents=True, exist_ok=True)
        promoted.write_text(json.dumps({"run_id": "video-owned-run", "job_id": job_id}))
        with patch.object(repertoire, "_pid_alive", return_value=False):
            result = repertoire.stop_and_delete_analysis_job(job_id)
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(job_dir.exists())
        self.assertFalse(own_output.exists())
        self.assertFalse(own_clip.exists())
        self.assertFalse(analyzer_run.exists())
        self.assertFalse(promoted.exists())
        self.assertTrue(shared_clip.exists())
        self.assertTrue(source.exists())
        self.assertEqual(repertoire._read_json(repertoire.asset_manifest_path("video-owned"))["analysis_ids"], [])

    def test_stop_analysis_job_reports_output_permission_errors_actionably(self):
        job = repertoire.create_job("analysis", {})
        with patch.object(repertoire, "_pid_alive", return_value=False), patch.object(
            repertoire, "_remove_analysis_job_outputs", side_effect=PermissionError(13, "Permission denied", "/generated/run")
        ):
            with self.assertRaisesRegex(RuntimeError, "host UID/GID"):
                repertoire.stop_and_delete_analysis_job(job["job_id"])

    def test_cancel_analysis_stops_only_containers_with_the_exact_job_label(self):
        import subprocess
        job_id = "analysis-owned-123456789abc"
        responses = [
            subprocess.CompletedProcess([], 0, stdout="0123456789abcdef\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="0123456789abcdef\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        ]
        commands = []
        def run(command, **_kwargs):
            commands.append(command)
            return responses.pop(0)
        with patch.object(repertoire.shutil, "which", return_value="/usr/bin/docker"), patch.object(
                repertoire.subprocess, "run", side_effect=run):
            stopped = repertoire._stop_analysis_job_containers(job_id)
        self.assertEqual(stopped, ["0123456789abcdef"])
        self.assertIn("label=story-builder.analysis-job=analysis-owned-123456789abc", commands[0])
        self.assertEqual(commands[1][-1], "0123456789abcdef")
        self.assertEqual(commands[2][0:3], ["/usr/bin/docker", "ps", "--no-trunc"])

    def test_running_analysis_cancel_waits_for_owned_containers_and_worker(self):
        job = repertoire.create_job("analysis", {"asset_ids": [], "settings": {}})
        job.update(status="running", pid=4321)
        repertoire._atomic_json(repertoire.job_path("analysis", job["job_id"]), job)
        calls = []
        with patch.object(repertoire, "_stop_analysis_job_containers", side_effect=lambda job_id: calls.append(job_id)), \
             patch.object(repertoire, "_pid_alive", return_value=True), \
             patch.object(repertoire, "_owned_worker_process", return_value=True), \
             patch.object(repertoire, "_wait_for_process_exit", return_value=True), \
             patch.object(repertoire.os, "killpg") as killpg:
            cancelled = repertoire.cancel_job("analysis", job["job_id"])
        self.assertEqual(calls, [job["job_id"], job["job_id"]])
        killpg.assert_called_once_with(4321, repertoire.signal.SIGTERM)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIn("containers and worker process have exited", cancelled["message"])

    def test_unverifiable_analysis_cancel_stays_pending_and_keeps_worker(self):
        job = repertoire.create_job("analysis", {"asset_ids": [], "settings": {}})
        job.update(status="running", pid=4322)
        repertoire._atomic_json(repertoire.job_path("analysis", job["job_id"]), job)
        with patch.object(repertoire, "_stop_analysis_job_containers", side_effect=RuntimeError("docker unavailable")), \
             patch.object(repertoire, "_pid_alive", return_value=True), \
             patch.object(repertoire.os, "killpg") as killpg:
            with self.assertRaisesRegex(RuntimeError, "docker unavailable"):
                repertoire.cancel_job("analysis", job["job_id"])
        killpg.assert_not_called()
        current = repertoire._read_json(repertoire.job_path("analysis", job["job_id"]))
        self.assertEqual(current["status"], "cancel_requested")

    def test_cancel_signals_only_a_live_worker_owned_process_group(self):
        import os
        import sys
        import time
        job_id = "analysis-process-group-123"
        worker_root = self.root / "worker-fixture"
        worker_file = worker_root / "story_builder" / "services" / "video_repertoire_worker.py"
        worker_file.parent.mkdir(parents=True)
        (worker_root / "story_builder" / "__init__.py").write_text("")
        (worker_root / "story_builder" / "services" / "__init__.py").write_text("")
        worker_file.write_text("import time\ntime.sleep(60)\n")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(worker_root)
        process = subprocess.Popen([sys.executable, "-m", "story_builder.services.video_repertoire_worker", "analysis", job_id],
            cwd=worker_root, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            job = repertoire.create_job("analysis", {"asset_ids": [], "settings": {"analysis_backend": "legacy"}})
            job["job_id"] = job_id
            job.update(status="running", pid=process.pid)
            repertoire._atomic_json(repertoire.job_path("analysis", job_id), job)
            deadline = time.monotonic() + 2
            while not repertoire._owned_worker_process(process.pid, "analysis", job_id) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(repertoire._owned_worker_process(process.pid, "analysis", job_id))
            stopped = repertoire.cancel_job("analysis", job_id)
            self.assertEqual(stopped["status"], "cancelled")
            self.assertEqual(process.wait(timeout=2), -repertoire.signal.SIGTERM)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=2)

    def test_delete_endpoint_returns_conflict_instead_of_internal_server_error(self):
        from fastapi import HTTPException
        from story_builder.api import main as api_main

        with patch.object(repertoire, "delete_analysis_job", side_effect=RuntimeError("permission denied")):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(api_main.delete_video_analysis_job("analysis-denied"))
        self.assertEqual(raised.exception.status_code, 409)

    def test_job_path_rejects_traversal(self):
        with self.assertRaises(ValueError):
            repertoire.job_path("analysis", "../../outside")

    def test_search_reads_normalized_scene_results(self):
        job = repertoire.create_job("analysis", {})
        job.update(status="completed", result={"videos": [{"asset_id": "video-one", "title": "Craft", "scenes": [{"scene_id": "scene_0001", "start_time_sec": 0, "end_time_sec": 2, "summary": "An artisan weaves silk", "transcript": "careful weaving", "keywords": ["artisan"], "clip_path": "clips/a.mp4"}]}]})
        repertoire._atomic_json(repertoire.job_path("analysis", job["job_id"]), job)
        results = repertoire.search_records("artisan silk")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["scene_id"], "scene_0001")

    def test_audio_library_lists_only_manifest_collected_assets_and_filters_category(self):
        repertoire.ensure_layout()
        asset_path = self.root / "music" / "music-one" / "sample.wav"
        asset_path.parent.mkdir(parents=True)
        asset_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        repertoire._atomic_json(self.root / "manifests" / "source-video.json", {
            "video_id": "source-video", "project_id": "project-1", "collected_assets": [{
                "asset_id": "music-one", "category": "music", "label": "Tense music",
                "start_time_sec": 2.5, "end_time_sec": 8.0, "confidence": 0.91,
                "path": str(asset_path),
            }],
        })
        listed = repertoire.list_audio_assets()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["category"], "music")
        self.assertEqual(listed[0]["source_video_id"], "source-video")
        self.assertEqual(repertoire.list_audio_assets("voices"), [])
        self.assertEqual(repertoire.list_audio_assets("music")[0]["asset_id"], "music-one")

    def test_audio_library_lists_sam_isolation_with_sidecar_provenance(self):
        isolated = self.root / "audio" / "isolated"
        isolated.mkdir(parents=True)
        wav = isolated / "sam-example.wav"
        wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        repertoire._atomic_json(wav.with_suffix(".json"), {
            "asset_type": "sam_audio_isolation", "model": "facebook/sam-audio-large-tv",
            "prompt": "footsteps", "provenance": {"video_id": "source-video", "start_time_sec": 4.0, "end_time_sec": 6.0},
        })
        listed = repertoire.list_audio_assets("isolated")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["category"], "isolated")
        self.assertEqual(listed[0]["label"], "footsteps")
        self.assertEqual(listed[0]["source_video_id"], "source-video")

    def test_audio_library_reads_assets_inside_canonical_analyzer_runs_without_copying(self):
        repertoire.ensure_layout()
        run_id = "a" * 16
        asset_path = self.root / "analyses" / "video_audio_analyzer" / run_id / "collected" / "sfx" / "impact.wav"
        asset_path.parent.mkdir(parents=True)
        asset_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        repertoire._atomic_json(self.root / "manifests" / "analyzer-runs" / f"{run_id}.json", {
            "run_id": run_id, "video_id": "source-video", "project_id": "project-1",
            "collected_assets": [{"asset_id": "impact-1", "category": "sfx", "label": "Metal impact",
                "path": asset_path.relative_to(self.root).as_posix()}],
        })

        listed = repertoire.list_audio_assets("sfx")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["project_id"], "project-1")
        self.assertTrue(listed[0]["content_url"].endswith(asset_path.relative_to(self.root).as_posix()))
        self.assertTrue(asset_path.is_file())
        self.assertFalse((self.root / "sfx" / "impact-1" / "impact.wav").exists())

    def test_audio_library_rejects_unknown_category_and_skips_external_paths(self):
        repertoire.ensure_layout()
        outside = Path(self.temporary.name) / "outside.wav"
        outside.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        repertoire._atomic_json(self.root / "manifests" / "bad.json", {
            "collected_assets": [{"asset_id": "escape", "category": "music", "path": str(outside)}],
        })
        with self.assertRaises(ValueError):
            repertoire.list_audio_assets("everything")
        self.assertEqual(repertoire.list_audio_assets(), [])

    def test_uploaded_extension_is_restricted(self):
        with self.assertRaises(ValueError):
            repertoire.create_uploaded_asset("notes.txt", b"not video")


if __name__ == "__main__":
    unittest.main()
