"""Raga inference module - classify raga using automatic-raga-recognition repo."""

import os
import sys
import logging
import torch
import numpy as np
from typing import Dict, Optional, Tuple
from pathlib import Path

# Add raga recognition repo to path
RAGA_REPO_PATH = "/home/saswata/web_dev/video maker/audio/song_gen/automatic-raga-recognition"
RAGA_SRC_PATH = os.path.join(RAGA_REPO_PATH, "src")
RAGA_MODELS_PATH = os.path.join(RAGA_REPO_PATH, "models")

if os.path.exists(RAGA_SRC_PATH):
    sys.path.insert(0, RAGA_SRC_PATH)

try:
    from deepSRGM import DeepSRGM
    from test_utils import predict10, mapping10
    RAGA_AVAILABLE = True
except ImportError:
    RAGA_AVAILABLE = False
    logging.warning("Raga recognition modules not available")

logger = logging.getLogger(__name__)


def load_raga_model(model_type: str = "lstm") -> Optional[torch.nn.Module]:
    """
    Load raga classification model.
    
    Args:
        model_type: "lstm" or "gru"
    
    Returns:
        Loaded model or None if failed
    """
    if not RAGA_AVAILABLE:
        logger.warning("Raga recognition not available")
        return None
    
    try:
        # Model parameters (from the repo)
        model_params = {
            'rnn': model_type,
            'input_length': 5000,
            'embedding_size': 128,
            'hidden_size': 768,
            'num_layers': 1,
            'num_classes': 10,
            'vocab_size': 209,
            'drop_prob': 0.3
        }
        
        model = DeepSRGM(**model_params)
        
        # Load checkpoint
        checkpoint_name = f"{model_type}_25_checkpoint.pth"
        checkpoint_path = os.path.join(RAGA_MODELS_PATH, checkpoint_name)
        
        if not os.path.exists(checkpoint_path):
            logger.warning(f"Checkpoint not found: {checkpoint_path}")
            return None
        
        checkpoint = torch.load(checkpoint_path, map_location='cpu')
        model.load_state_dict(checkpoint)
        model.eval()
        
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)
        
        logger.info(f"Loaded raga model: {checkpoint_name}")
        return model
        
    except Exception as e:
        logger.error(f"Failed to load raga model: {e}")
        return None


def preprocess_audio_for_raga(audio_path: str) -> Optional[np.ndarray]:
    """
    Preprocess audio for raga classification.
    
    NOTE: This is a simplified placeholder. The actual preprocessing requires:
    1. Pitch extraction (using external tools)
    2. Tonic detection
    3. Feature conversion to the format expected by the model
    
    For now, this returns None and logs a warning.
    The full preprocessing pipeline would need to be implemented separately.
    """
    logger.warning(
        "Raga preprocessing requires pitch extraction and tonic detection. "
        "This is a placeholder - full preprocessing not implemented yet."
    )
    return None


def classify_raga(
    audio_path: str,
    model: Optional[torch.nn.Module] = None,
    model_type: str = "lstm",
    threshold: float = 0.6
) -> Dict:
    """
    Classify raga from audio file.
    
    Args:
        audio_path: Path to audio file (should be vocal-separated for best results)
        model: Pre-loaded model (if None, will load)
        model_type: "lstm" or "gru"
        threshold: Confidence threshold for classification
    
    Returns:
        Dictionary with 'raga', 'confidence', 'votes', 'status'
    """
    if not RAGA_AVAILABLE:
        return {
            'raga': None,
            'confidence': 0.0,
            'votes': 0.0,
            'status': 'unavailable'
        }
    
    try:
        # Load model if not provided
        if model is None:
            model = load_raga_model(model_type)
            if model is None:
                return {
                    'raga': None,
                    'confidence': 0.0,
                    'votes': 0.0,
                    'status': 'model_load_failed'
                }
        
        # Preprocess audio (placeholder - needs full implementation)
        X = preprocess_audio_for_raga(audio_path)
        if X is None:
            return {
                'raga': None,
                'confidence': 0.0,
                'votes': 0.0,
                'status': 'preprocessing_not_implemented'
            }
        
        # Convert to tensor
        X_tensor = torch.from_numpy(X).long()
        
        # Predict
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        X_tensor = X_tensor.to(device)
        
        result = predict10(model, X_tensor, threshold=threshold, mapping=mapping10)
        
        # Parse result
        if "CONFUSED" in result:
            # Extract raga and confidence from "CONFUSED - Closest raga predicted is X with Y% votes"
            parts = result.split("is ")[1].split(" with ")
            raga = parts[0].strip()
            votes_str = parts[1].split("%")[0]
            votes = float(votes_str) / 100.0
            return {
                'raga': raga,
                'confidence': votes,
                'votes': votes,
                'status': 'confused'
            }
        else:
            # Extract raga from "Input music sample belongs to the X raga"
            raga = result.split("the ")[1].split(" raga")[0]
            return {
                'raga': raga,
                'confidence': 1.0,
                'votes': 1.0,
                'status': 'confident'
            }
            
    except Exception as e:
        logger.error(f"Raga classification failed: {e}")
        return {
            'raga': None,
            'confidence': 0.0,
            'votes': 0.0,
            'status': f'error: {str(e)}'
        }


def run_raga_classification(
    audio_path: str,
    vocal_path: Optional[str] = None,
    model_type: str = "lstm"
) -> Dict:
    """
    Run raga classification on audio (prefer vocal-separated if available).
    
    Args:
        audio_path: Path to audio file
        vocal_path: Path to vocal-separated audio (optional, preferred)
        model_type: "lstm" or "gru"
    
    Returns:
        Dictionary with raga classification results
    """
    # Use vocal path if available (better for raga classification)
    input_path = vocal_path if vocal_path and os.path.exists(vocal_path) else audio_path
    
    if not os.path.exists(input_path):
        logger.warning(f"Audio file not found: {input_path}")
        return {
            'raga': None,
            'confidence': 0.0,
            'votes': 0.0,
            'status': 'file_not_found'
        }
    
    return classify_raga(input_path, model_type=model_type)
