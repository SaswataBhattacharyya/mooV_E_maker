#!/usr/bin/env python3
"""
Main entry script for dataset preparation pipeline.

This script processes audio files through the complete pipeline:
1. Standardize audio (MP3 -> WAV)
2. Extract features (Essentia, Librosa)
3. Optional: Separate vocals (Demucs) and classify raga (for bhajan)
4. Segment audio into fixed windows
5. Create per-segment files (prompt, lyrics, analysis)
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from tqdm import tqdm

# Add codes directory to path
CODES_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODES_DIR)

from pipeline import (
    utils,
    audio_standardize,
    feature_extract,
    raga_infer,
    segment,
    json_merge,
    demucs_separate
)

# Default root directory
ROOT_DIR = "/home/saswata/web_dev/video maker/audio/song_gen"
DEFAULT_DATA_DIR = os.path.join(ROOT_DIR, "data")


def process_track(
    track_name: str,
    track_files: dict,
    class_name: str,
    data_dir: str,
    segment_len: float,
    overlap: float,
    sample_rate: int,
    use_demucs: bool,
    force: bool,
    dry_run: bool
) -> bool:
    """
    Process a single track through the complete pipeline.
    
    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Paths
        mp3_path = track_files['mp3']
        prompt_path = track_files['prompt']
        lyrics_path = track_files['lyrics']
        
        # Output paths
        cache_wav_dir = os.path.join(data_dir, "_cache_wav", class_name)
        analysis_dir = os.path.join(data_dir, "_analysis", class_name)
        segments_dir = os.path.join(data_dir, "_segments", class_name, track_name)
        demucs_dir = os.path.join(data_dir, "_demucs", class_name, track_name)
        
        wav_path = os.path.join(cache_wav_dir, f"{track_name}.wav")
        analysis_path = os.path.join(analysis_dir, f"{track_name}.analysis.json")
        
        # Step 0: Standardize audio
        logger.info(f"Step 0: Standardizing audio for {track_name}")
        if not audio_standardize.standardize_audio(
            mp3_path, wav_path, sample_rate, channels=2, force=force, dry_run=dry_run
        ):
            logger.error(f"Failed to standardize audio: {track_name}")
            return False
        
        # Step 1: Extract features
        logger.info(f"Step 1: Extracting features for {track_name}")
        
        # Optional: Demucs vocal separation (for bhajan)
        vocal_path = None
        if use_demucs and class_name == "bhajan":
            logger.info(f"Separating vocals for {track_name}")
            vocal_path = demucs_separate.separate_vocals(
                wav_path, demucs_dir, force=force, dry_run=dry_run
            )
            if vocal_path is None:
                logger.warning(f"Vocal separation failed for {track_name}, continuing without it")
        
        # Extract audio features
        features = feature_extract.extract_all_features(
            wav_path, vocal_path=vocal_path, sr=sample_rate
        )
        
        # Optional: Raga classification (for bhajan)
        raga_result = None
        if class_name == "bhajan":
            logger.info(f"Classifying raga for {track_name}")
            raga_result = raga_infer.run_raga_classification(
                wav_path, vocal_path=vocal_path, model_type="lstm"
            )
            if raga_result.get('status') == 'preprocessing_not_implemented':
                logger.warning("Raga preprocessing not fully implemented, skipping raga classification")
                raga_result = None
        
        # Merge track analysis
        track_metadata = {
            'track_name': track_name,
            'class': class_name,
            'source_mp3': mp3_path,
            'standardized_wav': wav_path,
            'sample_rate': sample_rate
        }
        
        track_analysis = json_merge.merge_track_analysis(
            features, raga_result=raga_result, track_metadata=track_metadata
        )
        
        # Save track analysis
        if not json_merge.save_track_analysis(
            track_analysis, analysis_path, force=force, dry_run=dry_run
        ):
            logger.error(f"Failed to save track analysis: {track_name}")
            return False
        
        # Step 2: Segment audio
        logger.info(f"Step 2: Segmenting audio for {track_name}")
        segments = segment.segment_audio(
            wav_path, segments_dir, segment_len, overlap, force=force, dry_run=dry_run
        )
        
        if not segments:
            logger.warning(f"No segments created for {track_name}")
            return True  # Not necessarily a failure
        
        # Step 3: Create per-segment files
        logger.info(f"Step 3: Creating segment files for {track_name}")
        for seg_path, start, end in segments:
            seg_name = os.path.splitext(os.path.basename(seg_path))[0]
            
            # Copy prompt and lyrics
            json_merge.copy_text_files_for_segment(
                prompt_path, lyrics_path, segments_dir, seg_name,
                force=force, dry_run=dry_run
            )
            
            # Create segment analysis
            seg_analysis = json_merge.create_segment_analysis(
                track_analysis, start, end, int(seg_name.replace("seg", ""))
            )
            
            seg_analysis_path = os.path.join(segments_dir, f"{seg_name}_analysis.json")
            json_merge.save_segment_analysis(
                seg_analysis, seg_analysis_path, force=force, dry_run=dry_run
            )
        
        logger.info(f"Successfully processed: {track_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing track {track_name}: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare dataset for ACE-Step finetuning",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '--data_dir',
        type=str,
        default=DEFAULT_DATA_DIR,
        help='Root data directory'
    )
    
    parser.add_argument(
        '--segment_len',
        type=float,
        default=20.0,
        help='Segment length in seconds'
    )
    
    parser.add_argument(
        '--overlap',
        type=float,
        default=2.0,
        help='Overlap between segments in seconds'
    )
    
    parser.add_argument(
        '--sr',
        type=int,
        default=44100,
        help='Sample rate for standardized WAV files'
    )
    
    parser.add_argument(
        '--use_demucs',
        action='store_true',
        default=False,
        help='Use Demucs for vocal separation (default: True for bhajan, False otherwise)'
    )
    
    parser.add_argument(
        '--no_demucs',
        action='store_true',
        help='Disable Demucs even for bhajan class'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing files'
    )
    
    parser.add_argument(
        '--dry_run',
        action='store_true',
        help='Dry run mode - show what would be done without actually doing it'
    )
    
    parser.add_argument(
        '--class',
        type=str,
        dest='class_filter',
        help='Process only this class (e.g., "bhajan" or "lofi")'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    utils.setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Determine Demucs usage
    use_demucs = args.use_demucs and not args.no_demucs
    
    if args.dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE - No files will be modified")
        logger.info("=" * 60)
    
    # Discover classes
    data_dir = args.data_dir
    if not os.path.isdir(data_dir):
        logger.error(f"Data directory not found: {data_dir}")
        return 1
    
    classes = []
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)
        if os.path.isdir(item_path) and not item.startswith('_'):
            if args.class_filter is None or item == args.class_filter:
                classes.append(item)
    
    if not classes:
        logger.warning(f"No classes found in {data_dir}")
        return 1
    
    logger.info(f"Found classes: {', '.join(classes)}")
    
    # Process each class
    total_tracks = 0
    successful_tracks = 0
    
    for class_name in classes:
        logger.info("=" * 60)
        logger.info(f"Processing class: {class_name}")
        logger.info("=" * 60)
        
        # Auto-enable Demucs for bhajan unless explicitly disabled
        class_use_demucs = use_demucs or (class_name == "bhajan" and not args.no_demucs)
        
        # Get tracks
        tracks = utils.get_track_files(data_dir, class_name)
        if not tracks:
            logger.warning(f"No tracks found in class: {class_name}")
            continue
        
        logger.info(f"Found {len(tracks)} tracks in {class_name}")
        
        # Process tracks
        for track_name, track_files in tqdm(tracks.items(), desc=f"Processing {class_name}"):
            total_tracks += 1
            if process_track(
                track_name, track_files, class_name, data_dir,
                args.segment_len, args.overlap, args.sr,
                class_use_demucs, args.force, args.dry_run
            ):
                successful_tracks += 1
    
    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total tracks: {total_tracks}")
    logger.info(f"Successful: {successful_tracks}")
    logger.info(f"Failed: {total_tracks - successful_tracks}")
    
    return 0 if successful_tracks == total_tracks else 1


if __name__ == "__main__":
    sys.exit(main())
