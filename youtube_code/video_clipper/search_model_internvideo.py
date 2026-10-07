#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
from pathlib import Path

from search_config import MOCK_SCORER_SEED


class InternVideoSearcher:
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock
        self.model = None
        self.processor = None

        if not self.use_mock:
            self._load_real_model()

    def _load_real_model(self):
        # TODO: adapt model loading to exact InternVideo2 repo layout
        # Keep this wrapper stable and adjust imports/loading here after you
        # confirm the real repo package structure and checkpoint names.
        raise NotImplementedError(
            "Real InternVideo2 loading is not wired yet. "
            "Edit search_model_internvideo.py to connect the exact repo layout, "
            "or run the pipeline with mock scoring."
        )

    def score_window(self, frame_paths: list[Path], query: str) -> float:
        if self.use_mock:
            return self._mock_score(frame_paths, query)
        return self._real_score(frame_paths, query)

    def _real_score(self, frame_paths: list[Path], query: str) -> float:
        # TODO: adapt model loading to exact InternVideo2 repo layout
        # Expected behavior:
        # 1. Load frames from frame_paths
        # 2. Build model inputs for the exact InternVideo2-CLIP 1B API
        # 3. Return a similarity score in [0, 1] or a comparable float
        raise NotImplementedError("Real scoring not implemented yet.")

    def _mock_score(self, frame_paths: list[Path], query: str) -> float:
        frame_fingerprints = []
        for path in frame_paths:
            try:
                stat = path.stat()
                frame_fingerprints.append(f"{path.name}:{stat.st_size}")
            except FileNotFoundError:
                frame_fingerprints.append(f"{path.name}:missing")

        digest_input = f"{query}|{len(frame_paths)}|" + "|".join(frame_fingerprints)
        digest = hashlib.sha256(f"{MOCK_SCORER_SEED}|{digest_input}".encode("utf-8")).hexdigest()
        value = int(digest[:8], 16) / 0xFFFFFFFF
        return round(float(value), 4)
