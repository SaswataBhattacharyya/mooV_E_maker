# 4. Video Repertoire and Video/Audio Analyzer

## Purpose

Video Repertoire is both a source-video library and a reference-analysis workspace. It supports YouTube resolution/download, local upload, importing existing references, video analysis, results review, searching, selected audio asset review, and handoff of selected media to Manual Director.

The `/video-summariser` route aliases the same frontend component as `/video-repertoire`. The backend still retains both a direct analyzer path and a legacy analyzer path, selected via analysis settings; the direct path is the default in `services/video_repertoire_worker.py`.

## Current direct-analysis path

For the direct backend, the worker calls `video_audio_analyzer/run_peav_worker.sh` on each source asset. It disables persisted selected-frame artifacts and frame-evidence analysis, runs clip-oriented summarization, overlays available Codex Director review, promotes registered output into Video Repertoire, then exposes scene clip records with timestamps, transcript segments, and audio events. It records the analyzer run and model statuses and measures best-effort host compute-memory samples.

The analyzer's manifest is the truthful record of which stages completed. Model unavailable/fallback statuses matter: a configured stage must not be reported as a real embedding, diarization, or sound label if that model did not run.

Key paths: `services/video_repertoire_worker.py`, `video_audio_analyzer/src/video_audio_analyzer/pipeline.py`, `internvideo3_stage.py`, `internvideo3_captioner.py`, `peav_adapter.py`, `retrieval.py`, `repertoire.py`, `README.md`.

## Intake and data lifecycle

1. A local video is uploaded, a YouTube URL is resolved/downloaded, or an existing file is registered.
2. The source video is recorded in a manifest and retained as a reusable source asset (YouTube downloads are not analysis derivatives).
3. An analysis job receives the selected asset IDs and settings; progress/events are persisted.
4. Analyzer working outputs are produced under its run area and promoted/registered in the shared `video_repertoire` structure for website access.
5. Results and library UI read the repertoire manifests and artifact endpoints; selected reusable audio appears in Audio Assets, while original source/analysis tracks are intentionally not shown as reusable clips.
6. Job deletion and asset deletion are distinct actions; reviewers should verify the exact scope in UI/API. Deleting a job should not delete the source YouTube download unless the explicit source asset is deleted.

Storage details can change; inspect `services/video_repertoire.py` and analyzer `repertoire.py` for the current promotion/deletion rules.

## Scene, cut, and frame concepts

- **Scene detection** finds higher-level visual segments and remains a core timeline feature.
- **Cut detection** can subdivide scenes into shot/cut clips.
- **Support-frame sampling/shaving** is an analysis aid; it is not the same thing as the clip video. The direct website path requests no persisted selected frames and no frame-evidence pass, while sampling may still occur internally for boundary/change analysis or model support.
- The user-facing controls include sampling FPS, visual-change threshold, adaptive sampling, preserve scene anchors, keep intermediates, and cut-level extraction options. Confirm how each setting maps to the exact direct-path CLI flags before interpreting a run.

## Audio settings and outputs

The page exposes independent audio options alongside visual controls. They include source-audio extraction and MP3 preview extraction, speech/transcript detection, diarization, music and SFX detection, audio/AV embeddings, Demucs mode, and optional collection of voice/music/SFX clips. Reusable voice/music/SFX collection is opt-in in the current UI. Demucs `AUTO` is a policy, not unconditional separation.

Important distinction: Demucs separates stems such as vocals/drums/bass/other; it does not semantically separate “thunder”, “car”, or “footsteps”. Sound-event labels depend on the detector actually available; ASR and diarization are separate. Music measurements (energy/spectral/onsets/tempo) are not equivalent to reliable natural-language mood classification.

## Search and results

- **Keyword/word search** searches available text/metadata and can work without a loaded semantic model.
- **Semantic search** requires real query and indexed embeddings, plus a reachable PE-AV query worker. If the query worker or vectors are unavailable, the UI should say so and semantic results should not be fabricated; keyword search remains a separate path.
- Embedding retrieval is primarily clip/scene-level and may include transcript/summary semantics depending on index content; it is not a guarantee that every audio modality has an independent searchable index.
- Results include recent analyses, full-video summary, scenes/cuts, transcript and audio cues, and asset selection/handoff. The user should verify what is actually populated from a completed run, rather than assume each detected event has a saved standalone WAV.

## SAM Audio and voice identity

SAM Audio is a lazy, on-demand isolation tool. A detected event is not automatically isolated or permanently stored. Temporary previews require explicit review/save action to become a repertoire asset; temporary data should expire/clean up when not saved. Availability depends on the isolated worker, local gated checkpoint/access and GPU resources.

Voice diarization, ECAPA same-speaker embeddings, and Director/Codex review are distinct. Within-project identity candidates are supported; a candidate match is not by itself a safe identity merge. Cross-project identity is not a required user goal in the current direction. Anonymous aliases should not imply a real person's name.

## Legacy path warning

The legacy analyzer code remains present for compatibility. Its existence does not mean the direct clip-first path is using it. Conversely, old standalone summarizer artifacts/settings may still be referenced by legacy code. Do not delete the `video_summariser` tree until all API imports/settings dependencies are verified absent and the direct analyzer path has been tested after the switch.

