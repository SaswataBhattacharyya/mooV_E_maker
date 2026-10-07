"""Ollama API client for story analysis stages."""
import json
import urllib.request


class OllamaClient:
    """Wrapper around Ollama /api/chat endpoint."""

    def __init__(self, api_url="http://127.0.0.1:11434/v1", model="qwen3.6:35b"):
        self.api_url = api_url.rstrip("/") + "/api"
        self.model = model

    def chat(self, messages, temperature=0.3):
        """Send a chat request and return the assistant's response text.
        
        Args:
            messages: list of {"role": "user"|"assistant"|"system", "content": str}
            temperature: float 0-1
            
        Returns:
            response text or None on failure
        """
        url = f"{self.api_url}/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
        return data.get("message", {}).get("content")

    def is_available(self):
        """Quick health check."""
        try:
            url = f"{self.api_url}/tags"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                json.loads(resp.read())
            return True
        except Exception:
            return False

    def list_models(self):
        """Return available models."""
        if "v1" in self.api_url:
            # OpenAI-compatible URL (ends in /v1)
            return None
        url = f"{self.api_url}/tags"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        return data.get("models", [])


def create_client(api_url="http://127.0.0.1:11434/v1", model="qwen3.6:35b"):
    """Factory function to create an OllamaClient."""
    return OllamaClient(api_url=api_url, model=model)
