"""Tests for config and constants."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
import config


class TestConfig:
    def test_defaults(self):
        assert config.OLLAMA_HOST == "http://127.0.0.1:11434"
        assert config.MOVIE_BUILDER_PORT == "8501"
        assert config.PROJECT_STATE_DIR is not None

class TestConstants:
    def test_v1_types_count(self):
        from core.constants import SUPPORTED_PROJECT_TYPES_V1
        assert len(SUPPORTED_PROJECT_TYPES_V1) == 3
    
    def test_all_types_count(self):
        from core.constants import PROJECT_TYPES
        assert len(PROJECT_TYPES) == 9
    
    def test_enums_populated(self):
        from core.constants import GENRES, TONES
        assert len(GENRES) > 0 and len(TONES) > 0
