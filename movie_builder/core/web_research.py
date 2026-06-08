def web_research_available() -> bool:
    """Check if web research backend is configured."""
    return False


def research_style_or_genre(query: str) -> dict:
    """Research genre/style online (placeholder)."""
    return {
        "available": False,
        "message": "Web research is not configured. Continuing with local genre/style options.",
    }
