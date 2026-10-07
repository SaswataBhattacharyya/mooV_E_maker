"""Utility functions for the preprocessing pipeline."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def ensure_dir(path: str) -> None:
    """Ensure directory exists, create if it doesn't."""
    Path(path).mkdir(parents=True, exist_ok=True)


def get_track_files(data_dir: str, class_name: str) -> Dict[str, Dict[str, str]]:
    """
    Scan a class directory and return track files.
    
    Returns:
        Dict mapping track_name -> {'mp3': path, 'prompt': path, 'lyrics': path}
    """
    class_dir = os.path.join(data_dir, class_name)
    if not os.path.isdir(class_dir):
        return {}
    
    tracks = {}
    for filename in os.listdir(class_dir):
        if filename.endswith('.mp3'):
            track_name = filename[:-4]  # Remove .mp3
            tracks[track_name] = {
                'mp3': os.path.join(class_dir, filename),
                'prompt': os.path.join(class_dir, f"{track_name}_prompt.txt"),
                'lyrics': os.path.join(class_dir, f"{track_name}_lyrics.txt")
            }
    
    return tracks


def check_output_exists(output_path: str, force: bool = False) -> bool:
    """Check if output exists and should be skipped."""
    if force:
        return False
    return os.path.exists(output_path)


def save_json(data: Dict, path: str) -> None:
    """Save dictionary to JSON file."""
    ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> Dict:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def read_text_file(path: str) -> Optional[str]:
    """Read text file, return None if file doesn't exist."""
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def get_segment_name(segment_idx: int) -> str:
    """Generate segment filename (e.g., seg000, seg001)."""
    return f"seg{segment_idx:03d}"
