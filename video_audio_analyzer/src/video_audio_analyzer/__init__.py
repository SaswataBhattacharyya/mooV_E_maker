"""Isolated multimodal video/audio analyzer.

This package deliberately has no import-time dependency on ComfyUI, Ollama,
or the Story Builder backend. Optional model stages report an unavailable
status instead of preventing the deterministic media pipeline from running.
"""

__version__ = "0.1.0"
