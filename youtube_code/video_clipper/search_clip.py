#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import shutil
import subprocess
import tempfile
from pathlib import Path

from search_config import (
    DEFAULT_CLIP_LEN_SEC,
    DEFAULT_EXTRACT_CLIPS,
    DEFAULT_OUT_DIR,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_OVERLAP_SEC,
    DEFAULT_QUERY,
    DEFAULT_SCORE_THRESHOLD,
    DEFAULT_TOP_K,
    DEFAULT_USE_LLM_REFINEMENT,
    DEFAULT_VIDEO_DIR,
    VIDEO_EXTS,
)
from search_json_utils import merge_matches, save_video_results
from search_model_internvideo import InternVideoSearcher
from search_query_utils import prompt_bool, refine_query_variants, slugify
from search_video_utils import extract_clip, generate_windows, get_video_duration, require_ffmpeg, sample_window_frames


def prompt_float(label: str, default: float) -> float:
    raw = input(f"{label} [{default}]: ").strip()
    return float(raw) if raw else float(default)


def prompt_int(label: str, default: int) -> int:
    raw = input(f"{label} [{default}]: ").strip()
    return int(raw) if raw else int(default)


def build_output_paths(output_root: Path, query_slug: str) -> tuple[Path, Path]:
    root = output_root / query_slug
    return root / "json", root / "clips"


def choose_query_variants(query: str, use_llm_refinement: bool, ollama_model: str) -> list[str]:
    if not use_llm_refinement:
        return [query]
    return refine_query_variants(query, model_name=ollama_model)


def score_window_against_queries(searcher: InternVideoSearcher, frame_paths: list[Path], query_variants: list[str]) -> tuple[float, str]:
    best_score = float("-inf")
    best_query = query_variants[0]

    for query in query_variants:
        score = searcher.score_window(frame_paths, query)
        if score > best_score:
            best_score = score
            best_query = query

    return round(best_score, 4), best_query


def process_video(
    video_path: Path,
    json_dir: Path,
    clips_dir: Path,
    query_original: str,
    query_variants: list[str],
    clip_len_sec: float,
    overlap_sec: float,
    threshold: float,
    top_k: int,
    extract_clips_enabled: bool,
    searcher: InternVideoSearcher,
):
    duration_sec = get_video_duration(video_path)
    windows = generate_windows(duration_sec, clip_len_sec, overlap_sec)
    raw_matches = []
    total_windows = len(windows)
    json_path = json_dir / f"{slugify(video_path.stem)}_matches.json"

    print(f"\n→ {video_path.name}: {total_windows} windows", flush=True)

    def save_progress(final: bool = False):
        merged_matches = merge_matches(raw_matches, top_k=top_k) if final else []
        payload = {
            "video": str(video_path),
            "query_original": query_original,
            "query_variants": query_variants,
            "clip_len_sec": clip_len_sec,
            "overlap_sec": overlap_sec,
            "threshold": threshold,
            "raw_matches": raw_matches,
            "merged_matches": merged_matches,
            "progress": {
                "processed_windows": processed_windows,
                "total_windows": total_windows,
                "complete": final,
            },
        }
        save_video_results(json_path, payload)

    processed_windows = 0
    save_progress(final=False)

    for index, window in enumerate(windows, start=1):
        start_sec = window["start_sec"]
        end_sec = window["end_sec"]
        temp_dir = Path(tempfile.mkdtemp(prefix="search_clip_window_"))

        if index == 1 or index % 10 == 0 or index == total_windows:
            print(
                f"   progress {index}/{total_windows} "
                f"({start_sec:.1f}s -> {end_sec:.1f}s)",
                flush=True,
            )

        try:
            frame_paths = sample_window_frames(video_path, start_sec, end_sec, temp_root=temp_dir)
            if not frame_paths:
                continue
            score, matched_query = score_window_against_queries(searcher, frame_paths, query_variants)
        except subprocess.CalledProcessError as exc:
            print(f"   frame sampling failed for {start_sec:.3f}-{end_sec:.3f}: {exc} (skipping window)")
            continue
        except Exception as exc:
            print(f"   window scoring failed for {start_sec:.3f}-{end_sec:.3f}: {exc} (skipping window)")
            continue
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            processed_windows = index

        if index % 10 == 0 or index == total_windows:
            save_progress(final=False)

        if score >= threshold:
            raw_matches.append(
                {
                    "start_sec": round(start_sec, 3),
                    "end_sec": round(end_sec, 3),
                    "score": score,
                    "matched_query": matched_query,
                }
            )
            print(
                f"   match {start_sec:.1f}-{end_sec:.1f}s score={score:.4f} query={matched_query}",
                flush=True,
            )
            save_progress(final=False)

    merged_matches = merge_matches(raw_matches, top_k=top_k)
    payload = {
        "video": str(video_path),
        "query_original": query_original,
        "query_variants": query_variants,
        "clip_len_sec": clip_len_sec,
        "overlap_sec": overlap_sec,
        "threshold": threshold,
        "raw_matches": raw_matches,
        "merged_matches": merged_matches,
        "progress": {
            "processed_windows": total_windows,
            "total_windows": total_windows,
            "complete": True,
        },
    }

    save_video_results(json_path, payload)
    print(f"   saved JSON -> {json_path}")

    if not extract_clips_enabled:
        return

    for item in merged_matches:
        clip_name = (
            f"{slugify(video_path.stem)}_"
            f"{int(item['start_sec']):06d}_"
            f"{int(item['end_sec']):06d}.mp4"
        )
        clip_path = clips_dir / clip_name
        try:
            extract_clip(video_path, clip_path, item["start_sec"], item["end_sec"])
            print(f"   clip -> {clip_path.name}")
        except subprocess.CalledProcessError as exc:
            print(f"   clip extraction failed for {clip_path.name}: {exc} (skipping clip)")


def main():
    require_ffmpeg()

    video_dir = input(f"Video folder [{DEFAULT_VIDEO_DIR}]: ").strip() or DEFAULT_VIDEO_DIR
    out_root = input(f"Output folder [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR
    query = input(f"Text query [{DEFAULT_QUERY}]: ").strip() or DEFAULT_QUERY
    use_llm_refinement = prompt_bool("LLM query refinement", DEFAULT_USE_LLM_REFINEMENT)
    ollama_model = DEFAULT_OLLAMA_MODEL
    if use_llm_refinement:
        ollama_model = input(f"Ollama model [{DEFAULT_OLLAMA_MODEL}]: ").strip() or DEFAULT_OLLAMA_MODEL

    clip_len_sec = prompt_float("Clip length in seconds", DEFAULT_CLIP_LEN_SEC)
    overlap_sec = prompt_float("Overlap in seconds", DEFAULT_OVERLAP_SEC)
    threshold = prompt_float("Score threshold", DEFAULT_SCORE_THRESHOLD)
    top_k = prompt_int("Top-k clips per video", DEFAULT_TOP_K)
    extract_clips_enabled = prompt_bool("Extract clips (otherwise JSON only)", DEFAULT_EXTRACT_CLIPS)
    use_mock = prompt_bool("Use mock scorer mode", True)

    if clip_len_sec <= 0:
        raise ValueError("clip_len_sec must be > 0")
    if overlap_sec < 0 or overlap_sec >= clip_len_sec:
        raise ValueError("overlap_sec must satisfy 0 <= overlap_sec < clip_len_sec")
    if top_k <= 0:
        raise ValueError("top_k must be > 0")

    video_dir = Path(video_dir)
    out_root = Path(out_root)
    query_slug = slugify(query) or "query"
    json_dir, clips_dir = build_output_paths(out_root, query_slug)
    json_dir.mkdir(parents=True, exist_ok=True)
    clips_dir.mkdir(parents=True, exist_ok=True)

    videos = [
        path for path in sorted(video_dir.glob("*"))
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS
    ]
    if not videos:
        print(f"No videos found in: {video_dir}")
        return

    query_variants = choose_query_variants(query, use_llm_refinement, ollama_model)
    print(f"\nUsing {len(query_variants)} query variant(s):")
    for item in query_variants:
        print(f"  - {item}")

    searcher = InternVideoSearcher(use_mock=use_mock)

    for video_path in videos:
        try:
            process_video(
                video_path=video_path,
                json_dir=json_dir,
                clips_dir=clips_dir,
                query_original=query,
                query_variants=query_variants,
                clip_len_sec=clip_len_sec,
                overlap_sec=overlap_sec,
                threshold=threshold,
                top_k=top_k,
                extract_clips_enabled=extract_clips_enabled,
                searcher=searcher,
            )
        except subprocess.CalledProcessError as exc:
            print(f"   ffmpeg/ffprobe failed for {video_path.name}: {exc} (skipping video)")
        except Exception as exc:
            print(f"   failed on {video_path.name}: {exc} (skipping video)")


if __name__ == "__main__":
    main()
