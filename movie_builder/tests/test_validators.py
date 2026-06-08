"""Tests for core.validators."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestValidators:
    def test_required_keys_present(self):
        from core.validators import validate_required_keys
        validate_required_keys({"a": 1, "b": 2}, ["a", "b"])

    def test_required_keys_missing(self):
        from core.validators import validate_required_keys
        from pytest import raises
        with raises(ValueError, match="Missing required keys"):
            validate_required_keys({"a": 1}, ["a", "b"])

    def test_ensure_stable_id_ok(self):
        from core.validators import ensure_stable_id
        data = {"name": "Homer"}
        ensure_stable_id("char_001", data)
        assert data["character_id"] == "char_001"

    def test_ensure_stable_id_mismatch(self):
        from core.validators import ensure_stable_id
        from pytest import raises
        data = {"character_id": "char_099"}
        with raises(ValueError, match="Stable ID mismatch"):
            ensure_stable_id("char_001", data)

    def test_validate_type_valid(self):
        from core.validators import validate_project_type
        assert validate_project_type("Movie / Short Film") is True

    def test_validate_type_invalid(self):
        from core.validators import validate_project_type
        assert validate_project_type("Not a real type") is False

    def test_v1_support_movie(self):
        from core.validators import validate_supported_v1_project_type
        ok, _ = validate_supported_v1_project_type("Movie / Short Film")
        assert ok is True

    def test_v1_reject_game(self):
        from core.validators import validate_supported_v1_project_type
        ok, _ = validate_supported_v1_project_type("Game / Visual Novel")
        assert ok is False

    def test_validate_positions_valid(self):
        from core.validators import validate_positions
        items = [{"position": 1}, {"position": 2}]
        assert validate_positions(items) is True

    def test_validate_positions_invalid(self):
        from core.validators import validate_positions
        items = [{"position": 1}, {"position": 5}]
        assert validate_positions(items) is False
