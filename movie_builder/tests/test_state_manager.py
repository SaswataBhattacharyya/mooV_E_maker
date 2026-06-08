"""Tests for core.state_manager."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest.mock import patch
import pytest
import config

@pytest.fixture(autouse=True)
def _tmp(tmp_path):
    with patch.object(config, "PROJECT_STATE_DIR", str(tmp_path)):
        with patch.object(config, "EXPORTS_DIR", str(tmp_path / "exports")):
            yield

class TestStateManager:
    def test_ensure_dirs(self):
        from core.state_manager import ensure_project_dirs
        ensure_project_dirs()

    def test_save_load_json(self, tmp_path):
        from core.state_manager import save_json, load_json
        p = str(tmp_path / "t.json")
        save_json(p, {"key": "val"})
        assert load_json(p) == {"key": "val"}

    def test_load_json_missing(self, tmp_path):
        from core.state_manager import load_json
        r = load_json(str(tmp_path / "/no/such.json"), {"default": True})
        assert r is not None and r.get("default")

    def test_load_json_corrupt(self, tmp_path):
        from core.state_manager import save_text, load_json
        p = str(tmp_path) + "/bad.json"
        save_text(p, "{not json")
        with pytest.raises(Exception):
            load_json(p)

    def test_save_load_text(self, tmp_path):
        from core.state_manager import save_text, load_text
        p = str(tmp_path) + "/t.txt"
        save_text(p, "hello")
        assert load_text(p) == "hello"

    def test_project_path(self):
        from core.state_manager import project_path
        assert "intake" in project_path("intake", "x.json")

    def test_export_path(self):
        from core.state_manager import export_path
        assert "exports" in export_path("s.txt")

    def test_next_id_empty(self):
        from core.state_manager import next_id
        assert next_id("char", []) == "char001"

    def test_next_id_continues(self):
        from core.state_manager import next_id
        assert next_id("char", ["char001"]) == "char002"

    def test_next_id_other_prefix(self):
        from core.state_manager import next_id
        assert next_id("scene", []) == "scene001"

    def test_normalize_positions(self):
        from core.state_manager import normalize_positions
        out = normalize_positions([{"position": 5}, {"position": 2}])
        assert [i["position"] for i in out] == [1, 2]

    def test_insert_position_end(self):
        from core.state_manager import insert_position
        items = [{"position": 1}]
        out = insert_position(items, {"name": "x"})
        assert len(out) == 2 and out[1]["name"] == "x"

    def test_insert_middle(self):
        from core.state_manager import insert_position
        items = [{"position": 1}, {"position": 2}]
        out = insert_position(items, {"name": "m"}, index=0)
        assert len(out) == 3 and out[0]["name"] == "m"

    def test_append_change_log(self):
        from core.state_manager import append_change_log, project_path, load_json
        append_change_log({"action": "test_log"})
        data = load_json(project_path("review", "change_log.json"))
        assert isinstance(data, list) and len(data) >= 1
