"""Demucs vocal separation module - separate vocals from audio."""

import os
import subprocess
import logging
from typing import Optional

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from demucs.pretrained import load_pretrained
    from demucs.audio import save_audio
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False
    logging.warning("Demucs not available - install with: pip install demucs")

from .utils import ensure_dir, check_output_exists

logger = logging.getLogger(__name__)


def separate_vocals_demucs(
    input_audio: str,
    output_dir: str,
    model_name: str = "htdemucs",
    force: bool = False,
    dry_run: bool = False
) -> Optional[str]:
    """
    Separate vocals from audio using Demucs.
    
    Args:
        input_audio: Path to input audio file
        output_dir: Directory to save separated stems
        model_name: Demucs model name (default: "htdemucs")
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        Path to vocal stem file, or None if failed
    """
    if not DEMUCS_AVAILABLE:
        logger.warning("Demucs not available, skipping vocal separation")
        return None
    
    if not os.path.exists(input_audio):
        logger.error(f"Input file not found: {input_audio}")
        return None
    
    # Expected output structure: output_dir/htdemucs/track_name/vocals.wav
    track_name = os.path.splitext(os.path.basename(input_audio))[0]
    vocal_path = os.path.join(output_dir, model_name, track_name, "vocals.wav")
    
    if check_output_exists(vocal_path, force):
        logger.info(f"Vocal separation already exists: {vocal_path}")
        return vocal_path
    
    if dry_run:
        logger.info(f"[DRY RUN] Would separate vocals: {input_audio} -> {vocal_path}")
        return vocal_path
    
    try:
        ensure_dir(output_dir)
        
        # Use Demucs command-line interface
        cmd = [
            'python', '-m', 'demucs.separate',
            '--out', output_dir,
            '--name', model_name,
            input_audio
        ]
        
        logger.info(f"Running Demucs vocal separation...")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if os.path.exists(vocal_path):
            logger.info(f"Vocal separation complete: {vocal_path}")
            return vocal_path
        else:
            logger.warning(f"Vocal file not found at expected path: {vocal_path}")
            # Try to find it in alternative locations
            alt_paths = [
                os.path.join(output_dir, track_name, "vocals.wav"),
                os.path.join(output_dir, "vocals.wav"),
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    logger.info(f"Found vocal file at: {alt_path}")
                    return alt_path
            return None
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Demucs separation failed: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error in vocal separation: {e}")
        return None


def separate_vocals_python(
    input_audio: str,
    output_dir: str,
    model_name: str = "htdemucs",
    force: bool = False,
    dry_run: bool = False
) -> Optional[str]:
    """
    Separate vocals using Demucs Python API (alternative to CLI).
    
    Args:
        input_audio: Path to input audio file
        output_dir: Directory to save separated stems
        model_name: Demucs model name
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        Path to vocal stem file, or None if failed
    """
    if not DEMUCS_AVAILABLE or not TORCH_AVAILABLE:
        logger.warning("Demucs or PyTorch not available")
        return None
    
    if not os.path.exists(input_audio):
        logger.error(f"Input file not found: {input_audio}")
        return None
    
    track_name = os.path.splitext(os.path.basename(input_audio))[0]
    vocal_path = os.path.join(output_dir, model_name, track_name, "vocals.wav")
    
    if check_output_exists(vocal_path, force):
        logger.info(f"Vocal separation already exists: {vocal_path}")
        return vocal_path
    
    if dry_run:
        logger.info(f"[DRY RUN] Would separate vocals (Python API): {input_audio}")
        return vocal_path
    
    try:
        import torchaudio
        from demucs.pretrained import load_pretrained
        from demucs.audio import save_audio
        
        ensure_dir(output_dir)
        
        # Load model
        logger.info(f"Loading Demucs model: {model_name}")
        model = load_pretrained(model_name)
        model.eval()
        
        # Load audio
        wav, sr = torchaudio.load(input_audio)
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)  # Convert to mono if needed
        
        # Separate
        logger.info("Separating audio...")
        with torch.no_grad():
            stems = model(wav.unsqueeze(0))
        
        # Save vocals (assuming vocals is the 3rd stem: [drums, bass, other, vocals])
        vocals = stems[0, 3]  # [batch, stem, channel, samples]
        
        ensure_dir(os.path.dirname(vocal_path))
        save_audio(vocals, vocal_path, sr=sr)
        
        logger.info(f"Vocal separation complete: {vocal_path}")
        return vocal_path
        
    except Exception as e:
        logger.error(f"Demucs Python API separation failed: {e}")
        return None


def separate_vocals(
    input_audio: str,
    output_dir: str,
    use_python_api: bool = False,
    model_name: str = "htdemucs",
    force: bool = False,
    dry_run: bool = False
) -> Optional[str]:
    """
    Separate vocals from audio using Demucs.
    
    Args:
        input_audio: Path to input audio file
        output_dir: Directory to save separated stems
        use_python_api: Use Python API instead of CLI
        model_name: Demucs model name
        force: Overwrite existing files
        dry_run: If True, only log what would be done
    
    Returns:
        Path to vocal stem file, or None if failed
    """
    if use_python_api:
        return separate_vocals_python(input_audio, output_dir, model_name, force, dry_run)
    else:
        return separate_vocals_demucs(input_audio, output_dir, model_name, force, dry_run)
