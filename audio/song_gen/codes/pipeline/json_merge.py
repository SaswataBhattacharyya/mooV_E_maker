"""JSON merge module - combine features and metadata into analysis JSON."""

import os
import logging
from typing import Dict, Optional

from .utils import save_json, read_text_file

logger = logging.getLogger(__name__)


def merge_track_analysis(
    track_features: Dict,
    raga_result: Optional[Dict] = None,
    track_metadata: Optional[Dict] = None
) -> Dict:
    """
    Merge all track-level analysis into a single JSON structure.
    
    Args:
        track_features: Features from feature_extract module
        raga_result: Raga classification result (optional)
        track_metadata: Additional metadata (optional)
    
    Returns:
        Merged analysis dictionary
    """
    analysis = {
        'features': track_features,
        'metadata': track_metadata or {}
    }
    
    if raga_result:
        analysis['raga'] = raga_result
    
    return analysis


def create_segment_analysis(
    track_analysis: Dict,
    segment_start: float,
    segment_end: float,
    segment_idx: int
) -> Dict:
    """
    Create segment-level analysis JSON from track-level analysis.
    
    Args:
        track_analysis: Track-level analysis dictionary
        segment_start: Start time of segment in seconds
        segment_end: End time of segment in seconds
        segment_idx: Segment index
    
    Returns:
        Segment analysis dictionary
    """
    segment_analysis = track_analysis.copy()
    segment_analysis['segment'] = {
        'index': segment_idx,
        'start': segment_start,
        'end': segment_end,
        'duration': segment_end - segment_start
    }
    
    return segment_analysis


def save_track_analysis(
    analysis: Dict,
    output_path: str,
    force: bool = False,
    dry_run: bool = False
) -> bool:
    """Save track-level analysis to JSON file."""
    if dry_run:
        logger.info(f"[DRY RUN] Would save track analysis: {output_path}")
        return True
    
    try:
        save_json(analysis, output_path)
        logger.debug(f"Saved track analysis: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save track analysis: {e}")
        return False


def save_segment_analysis(
    analysis: Dict,
    output_path: str,
    force: bool = False,
    dry_run: bool = False
) -> bool:
    """Save segment-level analysis to JSON file."""
    if dry_run:
        logger.info(f"[DRY RUN] Would save segment analysis: {output_path}")
        return True
    
    try:
        save_json(analysis, output_path)
        logger.debug(f"Saved segment analysis: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save segment analysis: {e}")
        return False


def copy_text_files_for_segment(
    track_prompt_path: Optional[str],
    track_lyrics_path: Optional[str],
    segment_dir: str,
    segment_name: str,
    force: bool = False,
    dry_run: bool = False
) -> bool:
    """
    Copy prompt and lyrics files for a segment.
    
    Args:
        track_prompt_path: Path to track-level prompt file
        track_lyrics_path: Path to track-level lyrics file
        segment_dir: Directory to save segment files
        segment_name: Segment name (e.g., "seg000")
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        True if successful
    """
    success = True
    
    # Copy prompt
    if track_prompt_path:
        prompt_content = read_text_file(track_prompt_path)
        if prompt_content is not None:
            prompt_output = os.path.join(segment_dir, f"{segment_name}_prompt.txt")
            if dry_run:
                logger.debug(f"[DRY RUN] Would copy prompt: {prompt_output}")
            else:
                try:
                    os.makedirs(segment_dir, exist_ok=True)
                    with open(prompt_output, 'w', encoding='utf-8') as f:
                        f.write(prompt_content)
                    logger.debug(f"Copied prompt: {prompt_output}")
                except Exception as e:
                    logger.error(f"Failed to copy prompt: {e}")
                    success = False
        else:
            logger.warning(f"Prompt file not found or empty: {track_prompt_path}")
    
    # Copy lyrics
    if track_lyrics_path:
        lyrics_content = read_text_file(track_lyrics_path)
        if lyrics_content is not None:
            lyrics_output = os.path.join(segment_dir, f"{segment_name}_lyrics.txt")
            if dry_run:
                logger.debug(f"[DRY RUN] Would copy lyrics: {lyrics_output}")
            else:
                try:
                    os.makedirs(segment_dir, exist_ok=True)
                    with open(lyrics_output, 'w', encoding='utf-8') as f:
                        f.write(lyrics_content)
                    logger.debug(f"Copied lyrics: {lyrics_output}")
                except Exception as e:
                    logger.error(f"Failed to copy lyrics: {e}")
                    success = False
        else:
            logger.warning(f"Lyrics file not found or empty: {track_lyrics_path}")
    
    return success
