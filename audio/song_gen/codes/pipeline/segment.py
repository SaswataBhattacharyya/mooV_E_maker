"""Audio segmentation module - split audio into fixed-length segments."""

import os
import subprocess
import logging
import math
from typing import List, Tuple

from .utils import ensure_dir, check_output_exists, get_segment_name

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logger.error(f"Failed to get audio duration: {e}")
        return 0.0


def calculate_segments(
    duration: float,
    segment_len: float = 20.0,
    overlap: float = 2.0
) -> List[Tuple[float, float]]:
    """
    Calculate segment start and end times.
    
    Args:
        duration: Total audio duration in seconds
        segment_len: Length of each segment in seconds
        overlap: Overlap between segments in seconds
    
    Returns:
        List of (start, end) tuples in seconds
    """
    if duration <= 0:
        return []
    
    segments = []
    start = 0.0
    step = segment_len - overlap
    
    while start < duration:
        end = min(start + segment_len, duration)
        segments.append((start, end))
        start += step
        
        # If next segment would be shorter than overlap, merge with previous
        if start < duration and (duration - start) < overlap:
            break
    
    return segments


def create_segment(
    input_wav: str,
    output_seg: str,
    start: float,
    end: float,
    force: bool = False,
    dry_run: bool = False
) -> bool:
    """
    Create a single audio segment using ffmpeg.
    
    Args:
        input_wav: Path to input WAV file
        output_seg: Path to output segment WAV file
        start: Start time in seconds
        end: End time in seconds
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        True if successful, False otherwise
    """
    if check_output_exists(output_seg, force):
        logger.debug(f"Skipping (already exists): {output_seg}")
        return True
    
    if dry_run:
        logger.debug(f"[DRY RUN] Would create segment: {output_seg} ({start:.2f}s - {end:.2f}s)")
        return True
    
    try:
        ensure_dir(os.path.dirname(output_seg))
        
        duration = end - start
        
        cmd = [
            'ffmpeg',
            '-i', input_wav,
            '-ss', str(start),
            '-t', str(duration),
            '-acodec', 'copy',  # Copy codec for speed
            '-y',
            output_seg
        ]
        
        logger.debug(f"Creating segment: {output_seg} ({start:.2f}s - {end:.2f}s)")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if os.path.exists(output_seg):
            return True
        else:
            logger.error(f"Segment file not created: {output_seg}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg failed for segment {output_seg}: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error creating segment: {e}")
        return False


def segment_audio(
    input_wav: str,
    output_dir: str,
    segment_len: float = 20.0,
    overlap: float = 2.0,
    force: bool = False,
    dry_run: bool = False
) -> List[Tuple[str, float, float]]:
    """
    Segment audio file into fixed-length segments.
    
    Args:
        input_wav: Path to input WAV file
        output_dir: Directory to save segments
        segment_len: Length of each segment in seconds
        overlap: Overlap between segments in seconds
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        List of (segment_path, start_time, end_time) tuples
    """
    if not os.path.exists(input_wav):
        logger.error(f"Input file not found: {input_wav}")
        return []
    
    duration = get_audio_duration(input_wav)
    if duration <= 0:
        logger.error(f"Invalid audio duration: {duration}")
        return []
    
    segments_info = calculate_segments(duration, segment_len, overlap)
    logger.info(f"Creating {len(segments_info)} segments from {duration:.2f}s audio")
    
    created_segments = []
    
    for idx, (start, end) in enumerate(segments_info):
        seg_name = get_segment_name(idx)
        seg_path = os.path.join(output_dir, f"{seg_name}.wav")
        
        if create_segment(input_wav, seg_path, start, end, force, dry_run):
            created_segments.append((seg_path, start, end))
        else:
            logger.warning(f"Failed to create segment {idx}")
    
    return created_segments
