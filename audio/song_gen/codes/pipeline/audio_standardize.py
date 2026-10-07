"""Audio standardization module - convert MP3 to standardized WAV."""

import os
import subprocess
import logging
from typing import Optional

from .utils import ensure_dir, check_output_exists

logger = logging.getLogger(__name__)


def standardize_audio(
    input_mp3: str,
    output_wav: str,
    sample_rate: int = 44100,
    channels: int = 2,
    force: bool = False,
    dry_run: bool = False
) -> bool:
    """
    Convert MP3 to standardized WAV format using ffmpeg.
    
    Args:
        input_mp3: Path to input MP3 file
        output_wav: Path to output WAV file
        sample_rate: Target sample rate (default: 44100)
        channels: Number of channels (default: 2 for stereo)
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(input_mp3):
        logger.error(f"Input file not found: {input_mp3}")
        return False
    
    if check_output_exists(output_wav, force):
        logger.info(f"Skipping (already exists): {output_wav}")
        return True
    
    if dry_run:
        logger.info(f"[DRY RUN] Would convert: {input_mp3} -> {output_wav}")
        return True
    
    try:
        ensure_dir(os.path.dirname(output_wav))
        
        # ffmpeg command: convert to WAV, resample, set channels
        cmd = [
            'ffmpeg',
            '-i', input_mp3,
            '-ar', str(sample_rate),
            '-ac', str(channels),
            '-sample_fmt', 's16',  # 16-bit PCM
            '-y',  # Overwrite output file
            output_wav
        ]
        
        logger.debug(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if os.path.exists(output_wav):
            file_size = os.path.getsize(output_wav)
            logger.info(f"Converted: {output_wav} ({file_size / 1024 / 1024:.2f} MB)")
            return True
        else:
            logger.error(f"Output file not created: {output_wav}")
            return False
            
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error standardizing audio: {e}")
        return False
