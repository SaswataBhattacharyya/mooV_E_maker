"""Tests for core.chunking."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestChunking:
    def test_get_story_context_has_keys(self):
        from core.chunking import get_story_context
        ctx = get_story_context()
        assert "story_text" in ctx

    def test_get_character_missing(self):
        from core.chunking import get_character_context
        result = get_character_context("char_999")
        if isinstance(result, dict):
            assert "current_character" not in result or result.get("current_character") is None
        else:
            assert result is None

    def test_find_references_nested(self):
        from core.chunking import _find_references
        data = {"list": [{"id": "char_001"}, {"other": "ref"}]}
        refs = _find_references(data, "char_001")
        assert any("char_001" in r for r in refs)

    def test_get_deletion_repair_context(self):
        from core.chunking import get_deletion_repair_context
        ctx = get_deletion_repair_context("character", "char_999")
        assert ctx["object_type"] == "character"


class TestContinuityEngine:
    def test_check_continuity_returns_dict(self):
        from core.continuity_engine import check_continuity_by_unit
        result = check_continuity_by_unit("Movie / Short Film")
        assert isinstance(result, dict)
