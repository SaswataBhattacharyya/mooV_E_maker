"""Tests for core.prompt_templates."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestPromptTemplates:
    def test_story_generation_prompt(self):
        from core.prompt_templates import build_story_generation_prompt
        p = build_story_generation_prompt({
            "title": "My Movie", "genre": "Sci-fi", "tone": "Dark",
            "raw_story": "Hero saves world.", "project_type": "Movie / Short Film",
        })
        assert "My Movie" in p and "valid json" in p.lower()

    def test_story_revision_prompt(self):
        from core.prompt_templates import build_story_revision_prompt
        p = build_story_revision_prompt(
            {"expanded_story": "Old story", "logline": "L"}, "More darkness"
        )
        assert "old story" in p.lower() or "Old" in p and "darkness" in p

    def test_character_index_prompt(self):
        from core.prompt_templates import build_character_index_prompt
        p = build_character_index_prompt(
            {"story_summary_for_context": "S"}, "Movie / Short Film"
        )
        assert "valid json" in p.lower() or "json only" in p.lower()

    def test_structure_index_movie(self):
        from core.prompt_templates import build_structure_index_prompt
        p = build_structure_index_prompt(
            {"expanded_story": "S"}, {}, {}, "Movie / Short Film"
        )
        assert "act" in p.lower() or "Act" in p

    def test_build_unit_block_revision(self):
        from core.prompt_templates import build_unit_block_revision_prompt
        p = build_unit_block_revision_prompt(
            {"current_data": {"dialogue": "Old"}},
            {"unit_id": "scene_001"}, "dialogue", "Make it dramatic"
        )
        assert "old" in p.lower() or "Old" in p

    def test_all_prompts_include_json_only(self):
        from core.prompt_templates import (
            build_story_generation_prompt,
            build_story_revision_prompt,
        )
        base = {"title": "T", "genre": "G", "tone": "T"}
        prompts_list = [
            build_story_generation_prompt(base),
            build_story_revision_prompt({"expanded_story": "e"}, "R"),
        ]
        for pt in prompts_list:
            assert "json" in pt.lower(), f"Missing JSON-only instruction: {pt[:80]}..."
