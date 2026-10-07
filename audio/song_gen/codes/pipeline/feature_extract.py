"""Feature extraction module - extract audio features using Essentia and Librosa."""

import os
import logging
import numpy as np
from typing import Dict, Optional

try:
    import essentia.standard as es
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False
    logging.warning("Essentia not available, will skip Essentia features")

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logging.warning("Librosa not available, will skip Librosa features")

from .utils import check_output_exists

logger = logging.getLogger(__name__)


def extract_essentia_features(audio_path: str) -> Dict:
    """Extract features using Essentia."""
    if not ESSENTIA_AVAILABLE:
        return {}
    
    try:
        # Load audio
        loader = es.MonoLoader(filename=audio_path)
        audio = loader()
        
        # Extract features
        features = {}
        
        # BPM estimation
        try:
            rhythm_extractor = es.RhythmExtractor2013(method="multifeature")
            bpm, beats, beats_confidence, _, beats_intervals = rhythm_extractor(audio)
            features['bpm'] = float(bpm)
            features['beats_confidence'] = float(beats_confidence)
        except Exception as e:
            logger.warning(f"Could not extract BPM: {e}")
            features['bpm'] = None
        
        # Key detection
        try:
            key_extractor = es.KeyExtractor()
            key, scale, strength = key_extractor(audio)
            features['key'] = key
            features['scale'] = scale
            features['key_strength'] = float(strength)
        except Exception as e:
            logger.warning(f"Could not extract key: {e}")
            features['key'] = None
            features['scale'] = None
        
        # Loudness
        try:
            loudness = es.Loudness()
            features['loudness'] = float(loudness(audio))
        except Exception as e:
            logger.warning(f"Could not extract loudness: {e}")
            features['loudness'] = None
        
        # Energy
        try:
            energy = es.Energy()
            features['energy'] = float(energy(audio))
        except Exception as e:
            logger.warning(f"Could not extract energy: {e}")
            features['energy'] = None
        
        # Danceability (simplified)
        try:
            danceability = es.Danceability()
            d_val = danceability(audio)
            features['danceability'] = float(d_val)
        except Exception as e:
            logger.warning(f"Could not extract danceability: {e}")
            features['danceability'] = None
        
        return features
        
    except Exception as e:
        logger.error(f"Essentia feature extraction failed: {e}")
        return {}


def extract_librosa_features(audio_path: str, sr: int = 44100) -> Dict:
    """Extract features using Librosa."""
    if not LIBROSA_AVAILABLE:
        return {}
    
    try:
        # Load audio
        y, sr_actual = librosa.load(audio_path, sr=sr)
        
        features = {}
        
        # Spectral centroid
        try:
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr_actual)[0]
            features['spectral_centroid_mean'] = float(np.mean(spectral_centroids))
            features['spectral_centroid_std'] = float(np.std(spectral_centroids))
        except Exception as e:
            logger.warning(f"Could not extract spectral centroid: {e}")
        
        # Spectral rolloff
        try:
            rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr_actual)[0]
            features['spectral_rolloff_mean'] = float(np.mean(rolloff))
            features['spectral_rolloff_std'] = float(np.std(rolloff))
        except Exception as e:
            logger.warning(f"Could not extract spectral rolloff: {e}")
        
        # Chroma features
        try:
            chroma = librosa.feature.chroma_stft(y=y, sr=sr_actual)
            features['chroma_mean'] = [float(x) for x in np.mean(chroma, axis=1)]
            features['chroma_std'] = [float(x) for x in np.std(chroma, axis=1)]
        except Exception as e:
            logger.warning(f"Could not extract chroma: {e}")
        
        # Tempo
        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr_actual)
            features['tempo'] = float(tempo)
        except Exception as e:
            logger.warning(f"Could not extract tempo: {e}")
            features['tempo'] = None
        
        # Harmonic/percussive separation
        try:
            y_harmonic, y_percussive = librosa.effects.hpss(y)
            harmonic_ratio = np.sum(y_harmonic**2) / (np.sum(y**2) + 1e-10)
            features['harmonic_ratio'] = float(harmonic_ratio)
            features['percussive_ratio'] = float(1.0 - harmonic_ratio)
        except Exception as e:
            logger.warning(f"Could not extract harmonic/percussive ratio: {e}")
        
        # Zero crossing rate
        try:
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            features['zero_crossing_rate_mean'] = float(np.mean(zcr))
            features['zero_crossing_rate_std'] = float(np.std(zcr))
        except Exception as e:
            logger.warning(f"Could not extract zero crossing rate: {e}")
        
        return features
        
    except Exception as e:
        logger.error(f"Librosa feature extraction failed: {e}")
        return {}


def extract_demucs_features(vocal_path: Optional[str]) -> Dict:
    """
    Extract features from Demucs vocal separation output.
    This is a placeholder - actual Demucs processing should be done separately.
    """
    features = {}
    
    if vocal_path and os.path.exists(vocal_path):
        try:
            if LIBROSA_AVAILABLE:
                y, sr = librosa.load(vocal_path, sr=44100)
                # Simple vocal presence score based on energy
                energy = np.sum(y**2) / len(y)
                features['vocal_presence_score'] = float(energy)
                features['vocal_duration'] = float(len(y) / sr)
        except Exception as e:
            logger.warning(f"Could not extract Demucs features: {e}")
    
    return features


def extract_all_features(
    audio_path: str,
    vocal_path: Optional[str] = None,
    sr: int = 44100
) -> Dict:
    """
    Extract all features from audio file.
    
    Returns:
        Dictionary with all extracted features
    """
    features = {
        'essentia': {},
        'librosa': {},
        'demucs': {}
    }
    
    if ESSENTIA_AVAILABLE:
        logger.debug("Extracting Essentia features...")
        features['essentia'] = extract_essentia_features(audio_path)
    
    if LIBROSA_AVAILABLE:
        logger.debug("Extracting Librosa features...")
        features['librosa'] = extract_librosa_features(audio_path, sr=sr)
    
    if vocal_path:
        logger.debug("Extracting Demucs features...")
        features['demucs'] = extract_demucs_features(vocal_path)
    
    return features
