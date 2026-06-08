"""Tests for core.structure_engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
import pytest


INITIAL_INDEX = {
    "project_type": "Movie / Short Film",
    "items": [
        {"act_id": "act_001", "position": 1, "title": "Act 1", "short_description": "Setup", "scenes": []},
        {"act_id": "act_002", "position": 2, "title": "Act 2", "short_description": "Confrontation", "scenes": []},
    ],
}

def _reset_index():
    from core.state_manager import save_json, project_path
    p = project_path("structure", "structure_index.json")
    save_json(p, INITIAL_INDEX)


@pytest.fixture(autouse=True)
def fresh_structure_index(request, tmp_path):
    from core.state_manager import save_json
    p = str(Path(config.PROJECT_STATE_DIR) / "structure" / "structure_index.json")
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    save_json(p, INITIAL_INDEX)
    yield


class TestStructureEngine:
    def test_load_structure_index(self):
        from core.structure_engine import load_structure_index
        s = load_structure_index()
        assert len(s["items"]) == 2
    
    def test_find_item_act_001(self):
        from core.structure_engine import find_structure_item
        _reset_index()
        item = find_structure_item("act_001")
        assert item is not None and item.get("title") == "Act 1"
    
    def test_move_item_down(self):
        from core.structure_engine import move_structure_item, load_structure_index
        _reset_index()
        struct = move_structure_item("act_001", "down")
        ids = [i["act_id"] for i in struct["items"]]
        assert ids == ["act_002", "act_001"]

    def test_update_description(self):
        from core.structure_engine import update_structure_item_description, load_structure_index
        _reset_index()
        update_structure_item_description("act_001", "New description")
        s = load_structure_index()
        item_ids = [i["act_id"] for i in s["items"]]
        # Should find act_001 and set its description
        if item_ids[0] == "act_001":
            assert s["items"][0]["short_description"] == "New description"
        else:
            assert s["items"][1]["short_description"] == "New description"

    def test_delete_item(self):
        from core.structure_engine import delete_structure_item, load_structure_index
        _reset_index()
        struct = delete_structure_item("act_001")
        remaining_ids = [i["act_id"] for i in struct["items"]]
        assert "act_001" not in remaining_ids

    def test_add_item(self):
        from core.structure_engine import add_structure_item, load_structure_index
        _reset_index()
        add_structure_item({"act_id": "act_003", "title": "Act 3"})
        s = load_structure_index()
        assert len(s["items"]) == 3


class TestUnitEngine:
    def test_get_unit_options_movie(self):
        from core.unit_engine import get_unit_options
        options = get_unit_options("Movie / Short Film", {"items": [{"act_id": "a1"}]})
        assert options["type"] == "movie" or options["prefix"] != ""
        assert options["acts"] is not None

    def test_get_unit_options_comic(self):
        from core.unit_engine import get_unit_options
        options = get_unit_options("Comic / Graphic Novel", {"items": [{"chapter_id": "c1"}]})
        assert options["chapters"] is not None or options.get("prefix") != ""

    def test_get_unit_options_book(self):
        from core.unit_engine import get_unit_options
        options = get_unit_options("Book / Novel", {"items": [{"chapter_id": "c1", "sections": []}]})
        assert options["chapters"] is not None or options.get("prefix") != ""


class TestWebResearch:
    def test_placeholder_returns_false(self):
        from core.web_research import web_research_available, research_style_or_genre
        assert web_research_available() is False
        result = research_style_or_genre("horror")
        assert "available" in result and not result["available"]


class TestPromptTemplatesCoverage:
    def test_all_prompts_exist(self):
        from core.prompt_templates import (
            build_story_generation_prompt,
            build_story_revision_prompt,
            build_story_summary_prompt,
            build_character_index_prompt,
            build_character_detail_prompt,
            build_character_revision_prompt,
            build_world_bible_prompt,
            build_structure_index_prompt,
            build_unit_generation_prompt,
            build_unit_block_revision_prompt,
        )

    def test_build_story_summary(self):
        from core.prompt_templates import build_story_summary_prompt
        p = build_story_summary_prompt({"expanded_story": "A tale."})
        assert "return valid json" in p.lower() or "valid json" in p.lower()

    def test_build_character_detail_movie(self):
        from core.prompt_templates import build_character_detail_prompt
        p = build_character_detail_prompt(
            {"story_summary_for_context": "S"},
            {"name": "Homer", "role": "protagonist"},
            "Movie / Short Film"
        )
        assert "Homer" in p

    def test_build_character_revision(self):
        from core.prompt_templates import build_character_revision_prompt
        p = build_character_revision_prompt(
            {"story_summary_for_context": "S"},
            {"character_id": "char_001", "name": "Homer"},
            "Make him angry"
        )
        assert "angry" in p.lower() or "anger" in p.lower()

    def test_build_world_bible(self):
        from core.prompt_templates import build_world_bible_prompt
        p = build_world_bible_prompt(
            {"expanded_story": "A world."},
            {"characters": [{"name": "John"}]},
            "Movie / Short Film"
        )
        assert "world" in p.lower() or "World" in p

    def test_build_character_delete_repair(self):
        from core.prompt_templates import build_character_delete_repair_prompt
        p = build_character_delete_repair_prompt(
            {"story_summary": "S"},
            {"name": "Deleted", "short_description": "was here"}
        )
        assert "deleted" in p.lower() or "Deleted" in p
