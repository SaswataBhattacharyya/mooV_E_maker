"""Tests for core.ollama_client (mocked)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest.mock import patch


class TestOllamaClient:
    @patch("core.ollama_client.ollama")
    def test_list_models_empty(self, m):
        from core.ollama_client import list_models
        m.list.return_value = {"models": []}
        assert list_models() == []

    @patch("core.ollama_client.ollama")
    def test_list_models_with_models(self, m):
        from core.ollama_client import list_models
        m.list.return_value = {"models": [{"name": "qwen3.6:35b", "size": 20e9}]}
        result = list_models()
        assert len(result) == 1 and result[0]["name"] == "qwen3.6:35b"

    @patch("core.ollama_client.ollama")
    def test_is_ollama_ready_true(self, m):
        from core.ollama_client import is_ollama_ready
        m.list.return_value = {"models": []}
        assert is_ollama_ready() is True

    @patch("core.ollama_client.ollama")
    def test_is_ollama_ready_false(self, m):
        from core.ollama_client import is_ollama_ready
        m.list.side_effect = Exception("broken")
        assert is_ollama_ready() is False

    @patch("core.ollama_client.ollama")
    def test_generate_json_parse(self, m):
        from core.ollama_client import generate_json
        fake = '{"logline": "A detective", "themes": ["crime"]}'
        m.chat.return_value = {"message": {"content": fake}}
        result = generate_json("test")
        assert result["logline"] == "A detective"

    @patch("core.ollama_client.ollama")
    def test_generate_json_codefence(self, m):
        from core.ollama_client import generate_json
        fake = '{"x": 1}'
        content = f"```json\n{fake}\n```"
        m.chat.return_value = {"message": {"content": content}}
        result = generate_json("test")
        assert result["x"] == 1

    @patch("core.ollama_client.ollama")
    def test_generate_json_failure(self, m):
        from core.ollama_client import generate_json
        m.chat.return_value = {"message": {"content": "no json!!!"}}
        from pytest import raises
        with raises(Exception, match="Failed to parse JSON"):
            generate_json("test")

    @patch("core.ollama_client.ollama")
    def test_generate_text(self, m):
        from core.ollama_client import generate_text
        m.chat.return_value = {"message": {"content": "Hello"}}
        assert generate_text("prompt") == "Hello"

    @patch("core.ollama_client.ollama")
    def test_stream_accumulates(self, m):
        from core.ollama_client import stream_generate
        m.chat.return_value = [
            {"message": {"content": "A"}},
            {"message": {"content": "B"}},
        ]
        assert stream_generate("prompt") == "AB"

    @patch("core.ollama_client.ollama")
    def test_stream_callback(self, m):
        from core.ollama_client import stream_generate
        chunks = []
        m.chat.return_value = [
            {"message": {"content": "X"}},
            {"message": {"content": "Y"}},
        ]
        stream_generate("prompt", on_chunk=chunks.append)
        assert chunks == ["X", "Y"]
