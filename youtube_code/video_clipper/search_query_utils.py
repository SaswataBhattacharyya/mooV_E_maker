#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import subprocess

from search_config import DEFAULT_OLLAMA_MODEL


def slugify(name: str) -> str:
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def prompt_bool(label: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    raw = input(f"{label} [{default_text}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1", "on"}


def build_query_refine_prompt(query: str) -> str:
    return (
        "You refine short video-search queries.\n"
        "Return strict JSON with this schema:\n"
        '{"refined_query": "...", "alternatives": ["...", "...", "..."]}\n'
        "Rules:\n"
        "- Keep each query short and concrete.\n"
        "- Preserve the original meaning.\n"
        "- Avoid explanations.\n"
        f"Original query: {query}\n"
    )


def parse_query_refine_output(raw_text: str, original_query: str) -> list[str]:
    text = raw_text.strip()
    if not text:
        return [original_query]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return [original_query]
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [original_query]

    candidates = [original_query]
    refined = str(data.get("refined_query", "")).strip()
    if refined:
        candidates.append(refined)

    for item in data.get("alternatives", []):
        variant = str(item).strip()
        if variant:
            candidates.append(variant)

    seen = set()
    unique = []
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique or [original_query]


def refine_query_variants(query: str, model_name: str = DEFAULT_OLLAMA_MODEL) -> list[str]:
    prompt = build_query_refine_prompt(query)
    cmd = ["ollama", "run", model_name, prompt]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [query]

    return parse_query_refine_output(result.stdout, query)
