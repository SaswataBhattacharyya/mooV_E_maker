#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

from search_config import JSON_INDENT


def save_video_results(json_path: Path, payload: dict):
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=JSON_INDENT), encoding="utf-8")


def merge_matches(raw_matches: list[dict], top_k: int) -> list[dict]:
    if not raw_matches:
        return []

    ordered = sorted(raw_matches, key=lambda item: (item["start_sec"], item["end_sec"]))
    merged = []

    current = {
        "start_sec": ordered[0]["start_sec"],
        "end_sec": ordered[0]["end_sec"],
        "scores": [ordered[0]["score"]],
    }

    for item in ordered[1:]:
        if item["start_sec"] <= current["end_sec"]:
            current["end_sec"] = max(current["end_sec"], item["end_sec"])
            current["scores"].append(item["score"])
            continue

        merged.append(_finalize_merged(current))
        current = {
            "start_sec": item["start_sec"],
            "end_sec": item["end_sec"],
            "scores": [item["score"]],
        }

    merged.append(_finalize_merged(current))
    merged.sort(key=lambda item: item["score_max"], reverse=True)
    return merged[: max(1, top_k)]


def _finalize_merged(item: dict) -> dict:
    scores = item["scores"]
    return {
        "start_sec": round(item["start_sec"], 3),
        "end_sec": round(item["end_sec"], 3),
        "score_max": round(max(scores), 4),
        "score_mean": round(sum(scores) / len(scores), 4),
    }
