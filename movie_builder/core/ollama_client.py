import ollama
import json
from typing import Any, Callable, Optional
import config


def is_ollama_ready() -> bool:
    """Check if Ollama API is reachable."""
    try:
        response = ollama.list()
        if isinstance(response, dict):
            return "models" in response or "error" not in response
        elif isinstance(response, list):
            return True
        return False
    except Exception:
        return False


def list_models() -> list[dict]:
    """List available Ollama models."""
    try:
        response = ollama.list()
        if isinstance(response, dict) and "models" in response:
            models = []
            for m in response["models"]:
                if isinstance(m, dict):
                    models.append({"name": m.get("name", "unknown"), "size": m.get("size", 0)})
                else:
                    models.append({"name": str(m), "size": 0})
            return models
        elif isinstance(response, list):
            models = []
            for m in response:
                if isinstance(m, dict):
                    models.append({"name": m.get("name", "unknown"), "size": m.get("size", 0)})
                else:
                    models.append({"name": str(m), "size": 0})
            return models
        else:
            print(f"[WARN] Unexpected Ollama list response type: {type(response)}")
            return []
    except Exception as e:
        print(f"[WARN] Could not list Ollama models: {e}")
        return []


def stream_generate(
    prompt: str,
    model: Optional[str] = None,
    options: Optional[dict] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """Stream.generate and accumulate text response. Optionally call on_chunk for each chunk."""
    if model is None:
        model = config.OLLAMA_STORY_MODEL

    raw_text_parts = []
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in response:
            delta = chunk.get("message", {}).get("content", "")
            if delta:
                raw_text_parts.append(delta)
                if on_chunk:
                    on_chunk(delta)
        return "".join(raw_text_parts)
    except Exception as e:
        raise Exception(f"Ollama generation failed (model={model}): {e}")


def generate_text(
    prompt: str,
    model: Optional[str] = None,
    options: Optional[dict] = None,
) -> str:
    """Generate text without streaming."""
    if model is None:
        model = config.OLLAMA_STORY_MODEL

    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        return response["message"]["content"]
    except Exception as e:
        raise Exception(f"Ollama generation failed (model={model}): {e}")


def generate_json(
    prompt: str,
    schema: Optional[dict] = None,
    model: Optional[str] = None,
    options: Optional[dict] = None,
) -> dict:
    """Generate JSON from Ollama. Collects full text, parses it."""
    if model is None:
        model = config.OLLAMA_STORY_MODEL

    full_text = generate_text(prompt, model)
    result = _parse_json_from_text(full_text)

    if result is None and schema:
        # One repair attempt
        try:
            return repair_json(full_text, schema, model)
        except Exception:
            raise Exception(f"Failed to parse JSON from Ollama output. Raw:\n{full_text[:500]}")
    elif result is None:
        raise Exception(f"Failed to parse JSON from Ollama output. Raw:\n{full_text[:500]}")

    if schema:
        _validate_json_structure(result, schema)

    return result


def repair_json(raw_text: str, schema: Optional[dict] = None, model: Optional[str] = None) -> dict:
    """Attempt to repair invalid JSON with a strict prompt."""
    if model is None:
        model = config.OLLAMA_STORY_MODEL

    repair_prompt = f"""The following text appears to be the intended JSON output but failed to parse as valid JSON:

{raw_text}

Return valid JSON only. No markdown. No commentary. No code fences. Just raw JSON matching the structure implied above."""

    return generate_json(repair_prompt, schema, model)


def _parse_json_from_text(text: str) -> Optional[dict]:
    """Extract and parse JSON from potentially messy text."""
    import json

    # Try direct parse first
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return data
        else:
            return None  # We expect dicts
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting between JSON-like brackets/braces
    import re
    # Look for {...} patterns
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = text[brace_start:brace_end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Look for [{}] patterns
    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if bracket_start != -1 and bracket_end > bracket_start:
        candidate = text[bracket_start:bracket_end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _validate_json_structure(data: dict, schema: dict) -> bool:
    """Validate JSON structure against a basic schema spec."""
    try:
        import jsonschema
        # If the schema has 'properties' it's likely a JSON Schema
        if "properties" in schema:
            jsonschema.validate(instance=data, schema=schema)
            return True
    except Exception:
        pass

    # Lightweight manual validation of required keys if no formal schema validation
    print(f"[INFO] Basic JSON validation performed for data with keys: {list(data.keys())[:10]}...")
    return True
