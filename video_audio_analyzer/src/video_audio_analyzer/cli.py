from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import AnalyzerOptions, analyze_video
from .preflight import run_preflight


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated video/audio analyzer")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--extract-fps", type=float, default=4.0)
    parser.add_argument("--scene-threshold", type=float, default=0.26)
    parser.add_argument("--min-scene-seconds", type=float, default=0.5)
    parser.add_argument("--cut-boundary-threshold", type=float, default=0.18)
    parser.add_argument("--min-cut-seconds", type=float, default=0.5)
    parser.add_argument("--extract-cut-clips", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--frame-change-threshold", type=float, default=0.08)
    parser.add_argument("--adaptive-sampling", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--preserve-scene-anchors", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--keep-intermediate-samples", action="store_true")
    parser.add_argument("--extract-source-audio", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--extract-mp3", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--run-demucs", choices=("AUTO", "off", "2-stem", "4-stem", "6-stem"), default="AUTO")
    parser.add_argument("--detect-speech", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--detect-music", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--detect-sfx", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--create-audio-embeddings", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--create-av-embeddings", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--diarize-speakers", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--collect-voice-examples", action="store_true")
    parser.add_argument("--collect-music-clips", action="store_true")
    parser.add_argument("--collect-sfx-clips", action="store_true")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--persist-selected-frames", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--analyze-frame-evidence", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.preflight:
        print(json.dumps(run_preflight(args.root), indent=2))
    if args.video:
        if args.project_id:
            os.environ["VIDEO_AUDIO_ANALYZER_PROJECT_ID"] = args.project_id
        options = AnalyzerOptions(extract_fps=args.extract_fps, scene_threshold=args.scene_threshold,
            min_scene_seconds=args.min_scene_seconds, cut_boundary_threshold=args.cut_boundary_threshold,
            min_cut_seconds=args.min_cut_seconds, extract_cut_clips=args.extract_cut_clips,
            frame_change_threshold=args.frame_change_threshold,
            adaptive_sampling=args.adaptive_sampling, preserve_scene_anchors=args.preserve_scene_anchors,
            keep_intermediate_samples=args.keep_intermediate_samples,
            delete_intermediate_samples=not args.keep_intermediate_samples,
            extract_source_audio=args.extract_source_audio, extract_preview_mp3=args.extract_mp3,
            run_demucs=args.run_demucs,
            detect_speech=args.detect_speech, detect_music=args.detect_music, detect_sfx=args.detect_sfx,
            create_audio_embeddings=args.create_audio_embeddings, create_av_embeddings=args.create_av_embeddings,
            diarize_speakers=args.diarize_speakers, collect_voice_examples=args.collect_voice_examples,
            collect_music_clips=args.collect_music_clips, collect_sfx_clips=args.collect_sfx_clips,
            persist_selected_frames=args.persist_selected_frames, analyze_frame_evidence=args.analyze_frame_evidence)
        result = analyze_video(args.video, args.root, options)
        print(json.dumps({"video_id": result["source"]["video_id"], "run_id": result["run_id"], "run_dir": result["run_dir"], "scenes": len(result["scenes"]), "statuses": result["statuses"]}, indent=2))


if __name__ == "__main__":
    main()
