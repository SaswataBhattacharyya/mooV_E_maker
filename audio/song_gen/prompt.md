You are building a local preprocessing + dataset-prep pipeline for ACE-Step finetuning.

ROOT DIR:
  /home/saswata/web_dev/video maker/audio/song_gen

AVAILABLE REPOS (DO NOT RE-CODE THESE MODELS; REUSE THEM):
  1) automatic-raga-recognition:
     /home/saswata/web_dev/video maker/audio/song_gen/automatic-raga-recognition
  2) essentia repo:
     /home/saswata/web_dev/video maker/audio/song_gen/essentia
  3) ACE-Step:
     /home/saswata/web_dev/video maker/audio/song_gen/ACE-Step (or ace-step folder)

DATA INPUT (source of truth):
  /home/saswata/web_dev/video maker/audio/song_gen/data/
    lofi/
      filename.mp3
      filename_prompt.txt
      filename_lyrics.txt
    bhajan/
      filename.mp3
      filename_prompt.txt
      filename_lyrics.txt
  More classes may be added later (bollywood, rap, etc). The pipeline must work for any class folder.

GOAL:
1) Standardize each mp3 into a cached wav (resample, consistent format).
2) Extract audio features using Essentia + Librosa into one merged JSON per track.
3) For bhajan only, optionally run vocal separation (demucs) and then run raga classification using the automatic-raga-recognition repo code, adding raga + confidence into the same JSON.
4) Segment standardized wav into fixed windows (default 20s, overlap 2s).
5) Option 1 lyrics handling: For every segment, copy the FULL lyrics and FULL prompt (same text) into per-segment files.
6) For every segment create a segment JSON that includes track-level analysis + segment start/end times.

OUTPUT STRUCTURE (create these folders under data/):
  data/_cache_wav/<class>/filename.wav
  data/_analysis/<class>/filename.analysis.json
  data/_segments/<class>/filename/
      seg000.wav
      seg000_prompt.txt
      seg000_lyrics.txt
      seg000_analysis.json
      seg001.wav ...
  The pipeline must not overwrite original data/<class>/filename_* files.

IMPLEMENTATION REQUIREMENTS:
- Use Python scripts, no notebooks.
- Use ffmpeg for conversion + segmentation (via subprocess).
- Use essentia python package if installed; otherwise fall back to calling essentia from the cloned repo if needed.
- Use librosa + soundfile for additional features.
- Demucs is optional; only run for bhajan class for vocals-based raga classification.
- Do NOT rewrite raga model; call the raga repo’s existing inference/eval code if possible, or import its modules.
- Write clean logging and progress bars.
- Add a “dry-run” mode.
- Make it restartable: if outputs already exist, skip unless --force is provided.

DELIVERABLES:
A) A single entry script:
   prepare_dataset.py
   with CLI args:
     --data_dir (default: ROOT/data)
     --segment_len 20
     --overlap 2
     --sr 44100
     --use_demucs (default true for bhajan)
     --force
     --dry_run

B) Helper modules in a /pipeline folder:
   pipeline/audio_standardize.py
   pipeline/feature_extract.py
   pipeline/raga_infer.py
   pipeline/segment.py
   pipeline/json_merge.py
   pipeline/utils.py

C) A README.md explaining:
   - exact commands to run
   - what dependencies to install (ffmpeg, python packages)
   - expected output structure
   - how to add new classes (folders)

Start by scanning the repos and confirming how to call raga inference from automatic-raga-recognition with minimal changes.
If calling their code directly is hard, wrap it via subprocess running their provided scripts and parse output.
Use robust error handling and continue processing other files if one fails.
