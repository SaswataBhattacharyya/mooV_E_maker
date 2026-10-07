# Dataset Preparation Pipeline for ACE-Step Finetuning

This pipeline processes audio files for ACE-Step model finetuning by standardizing audio, extracting features, segmenting tracks, and creating per-segment files with prompts and lyrics.

## Overview

The pipeline performs the following steps:

1. **Audio Standardization**: Convert MP3 files to standardized WAV format (44.1kHz, stereo, 16-bit PCM)
2. **Feature Extraction**: Extract audio features using Essentia and Librosa
3. **Vocal Separation** (optional, for bhajan): Use Demucs to separate vocals from music
4. **Raga Classification** (optional, for bhajan): Classify raga using automatic-raga-recognition model
5. **Segmentation**: Split audio into fixed-length segments (default: 20s with 2s overlap)
6. **File Generation**: Create per-segment prompt, lyrics, and analysis JSON files

## Installation

### System Dependencies

#### FFmpeg (Required)
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Verify installation
ffmpeg -version
```

### Python Dependencies

Create a virtual environment (recommended):

```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install Python packages:

```bash
pip install numpy scipy pandas
pip install soundfile librosa
pip install tqdm pyyaml
pip install torch torchaudio  # For Demucs and raga model
pip install essentia  # If available via pip, otherwise build from repo
pip install demucs  # For vocal separation (optional)
```

#### Essentia Installation

**Option 1: Pip install (if available)**
```bash
pip install essentia
```

**Option 2: Build from source**
If pip install fails, build from the cloned repo:
```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/essentia
# Follow Essentia build instructions
# See: https://essentia.upf.edu/installing.html
```

#### Demucs Installation (Optional, for vocal separation)
```bash
pip install demucs
```

## Docker Setup (Recommended)

Using Docker is the easiest way to set up the environment without dealing with dependency conflicts.

### Quick Start (Docker)

**Option 1: Using the helper script (easiest)**

```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes

# First time: Build the Docker image (takes ~10-15 minutes)
docker build -t audio-pipeline .

# Run the pipeline (automatically mounts data directory)
./run_docker.sh

# Or with custom arguments
./run_docker.sh --dry_run --verbose
./run_docker.sh --class bhajan
./run_docker.sh --segment_len 30 --overlap 5
```

**Option 2: Using docker-compose**

```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes

# Build and run
docker-compose run --rm audio-pipeline

# With custom arguments
docker-compose run --rm audio-pipeline python prepare_dataset.py --dry_run --verbose
```

**Option 3: Manual Docker commands**

```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes

# Build the Docker image (one-time setup, takes ~10-15 minutes)
docker build -t audio-pipeline .

# Run the pipeline
docker run --rm \
  -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
  audio-pipeline \
  python prepare_dataset.py --data_dir /app/data
```

That's it! The pipeline will process all your audio files.

### Prerequisites

- Docker installed on your system
  - [Install Docker](https://docs.docker.com/get-docker/)
  - Verify installation: `docker --version`

### Detailed Steps to Set Up and Run with Docker

1. **Navigate to the codes directory:**
   ```bash
   cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes
   ```

2. **Build the Docker image:**
   ```bash
   docker build -t audio-pipeline .
   ```
   
   This will:
   - Install system dependencies (ffmpeg, build tools)
   - Install all Python packages from requirements.txt
   - Set up the working environment
   
   **Note:** The first build may take 10-15 minutes as it downloads and installs all dependencies.

3. **Run the pipeline:**
   
   The Docker container needs access to your data directory. Use volume mounting to share the data folder:
   
   ```bash
   docker run --rm \
     -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
     audio-pipeline \
     python prepare_dataset.py --data_dir /app/data
   ```
   
   **Explanation:**
   - `--rm`: Automatically remove container after it exits
   - `-v`: Mount your data directory into the container (host_path:container_path)
   - `audio-pipeline`: The image name we built
   - `--data_dir /app/data`: Specify the data directory inside the container
   
   **Note:** The default data directory in the container is `/app/data`, which matches the mounted volume.
   
   **Directory Structure in Container:**
   ```
   /app/                    # Working directory
   ├── pipeline/           # Pipeline modules
   ├── prepare_dataset.py  # Main script
   └── data/               # Mounted from host (your data directory)
       ├── bhajan/
       ├── lofi/
       ├── _cache_wav/     # Created by pipeline
       ├── _analysis/      # Created by pipeline
       └── _segments/      # Created by pipeline
   ```

4. **Run with custom arguments:**
   
   ```bash
   # Dry run
   docker run --rm \
     -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
     audio-pipeline \
     python prepare_dataset.py --dry_run --verbose
   
   # Process only bhajan class
   docker run --rm \
     -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
     audio-pipeline \
     python prepare_dataset.py --class bhajan
   
   # Custom segment length
   docker run --rm \
     -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
     audio-pipeline \
     python prepare_dataset.py --segment_len 30 --overlap 5
   ```

5. **Using docker-compose (easier):**
   
   For convenience, you can use docker-compose:
   ```bash
   # Build and run with default command
   docker-compose run --rm audio-pipeline
   
   # Run with custom arguments
   docker-compose run --rm audio-pipeline python prepare_dataset.py --dry_run --verbose
   docker-compose run --rm audio-pipeline python prepare_dataset.py --class bhajan
   ```
   
   The data directory is automatically mounted via docker-compose.yml.

6. **Interactive mode (for debugging):**
   
   To get a shell inside the container:
   ```bash
   docker run --rm -it \
     -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
     audio-pipeline \
     /bin/bash
   ```
   
   Or with docker-compose:
   ```bash
   docker-compose run --rm audio-pipeline /bin/bash
   ```
   
   Then you can run commands interactively:
   ```bash
   python prepare_dataset.py --dry_run
   python prepare_dataset.py --class bhajan
   ```

### Docker Tips

- **GPU Support (if needed):** If you have NVIDIA GPU and want to use it for Demucs/raga model:
  ```bash
  docker run --rm --gpus all \
    -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
    audio-pipeline \
    python prepare_dataset.py
  ```
  
  Note: You'll need [nvidia-docker](https://github.com/NVIDIA/nvidia-docker) installed.

- **Rebuild after changes:** If you modify `requirements.txt` or the code:
  ```bash
  docker build -t audio-pipeline .
  ```

- **Check container logs:** If something goes wrong, check the output or run interactively to debug.

### Docker vs Local Installation

**Use Docker if:**
- You want a clean, isolated environment
- You're having dependency conflicts
- You want consistent results across different machines
- You don't want to pollute your system Python

**Use local installation if:**
- You need to modify dependencies frequently
- You're developing/debugging the pipeline code
- You prefer working directly with your Python environment

## Data Structure

### Input Structure

Place your audio files in the following structure:

```
data/
├── bhajan/
│   ├── track1.mp3
│   ├── track1_prompt.txt
│   ├── track1_lyrics.txt
│   ├── track2.mp3
│   ├── track2_prompt.txt
│   └── track2_lyrics.txt
└── lofi/
    ├── track1.mp3
    ├── track1_prompt.txt
    └── track1_lyrics.txt
```

**Note**: Prompt and lyrics files are optional but recommended. The pipeline will continue without them but will log warnings.

### Output Structure

The pipeline creates the following structure:

```
data/
├── _cache_wav/          # Standardized WAV files
│   ├── bhajan/
│   │   └── track1.wav
│   └── lofi/
│       └── track1.wav
├── _analysis/           # Track-level analysis JSON
│   ├── bhajan/
│   │   └── track1.analysis.json
│   └── lofi/
│       └── track1.analysis.json
├── _demucs/            # Demucs vocal separation (if used)
│   └── bhajan/
│       └── track1/
│           └── htdemucs/
│               └── track1/
│                   └── vocals.wav
└── _segments/          # Segmented audio and files
    ├── bhajan/
    │   └── track1/
    │       ├── seg000.wav
    │       ├── seg000_prompt.txt
    │       ├── seg000_lyrics.txt
    │       ├── seg000_analysis.json
    │       ├── seg001.wav
    │       └── ...
    └── lofi/
        └── track1/
            └── ...
```

## Usage

### Basic Usage

Process all classes with default settings:

```bash
cd /home/saswata/web_dev/video\ maker/audio/song_gen/codes
python prepare_dataset.py
```

### Command-Line Arguments

```bash
python prepare_dataset.py [OPTIONS]
```

**Options:**

- `--data_dir PATH`: Root data directory (default: `/home/saswata/web_dev/video maker/audio/song_gen/data`)
- `--segment_len FLOAT`: Segment length in seconds (default: 20.0)
- `--overlap FLOAT`: Overlap between segments in seconds (default: 2.0)
- `--sr INT`: Sample rate for standardized WAV files (default: 44100)
- `--use_demucs`: Enable Demucs vocal separation (default: auto-enabled for bhajan)
- `--no_demucs`: Disable Demucs even for bhajan class
- `--force`: Overwrite existing output files
- `--dry_run`: Show what would be done without actually doing it
- `--class NAME`: Process only this class (e.g., `--class bhajan`)
- `--verbose`: Enable verbose logging

### Examples

**Process only bhajan class:**
```bash
python prepare_dataset.py --class bhajan
```

**Custom segment length and overlap:**
```bash
python prepare_dataset.py --segment_len 30 --overlap 5
```

**Dry run to see what would happen:**
```bash
python prepare_dataset.py --dry_run --verbose
```

**Force reprocess all files:**
```bash
python prepare_dataset.py --force
```

**Process with custom data directory:**
```bash
python prepare_dataset.py --data_dir /path/to/your/data
```

## Adding New Classes

To add a new class (e.g., "bollywood" or "rap"):

1. Create a new folder in the data directory:
   ```bash
   mkdir -p data/bollywood
   ```

2. Add your audio files:
   ```
   data/bollywood/
   ├── song1.mp3
   ├── song1_prompt.txt
   ├── song1_lyrics.txt
   ├── song2.mp3
   └── ...
   ```

3. Run the pipeline:
   ```bash
   python prepare_dataset.py --class bollywood
   ```

The pipeline will automatically detect and process the new class folder.

## Features Extracted

### Essentia Features
- BPM (beats per minute)
- Key and scale
- Loudness
- Energy
- Danceability

### Librosa Features
- Spectral centroid (mean, std)
- Spectral rolloff (mean, std)
- Chroma features
- Tempo
- Harmonic/percussive ratio
- Zero crossing rate

### Raga Classification (bhajan only)
- Raga name
- Confidence score
- Voting statistics

## Troubleshooting

### FFmpeg Not Found
```bash
# Install ffmpeg
sudo apt-get install ffmpeg  # Ubuntu/Debian
brew install ffmpeg          # macOS
```

### Essentia Import Error
- Try installing via pip: `pip install essentia`
- If that fails, build from the cloned repo in `essentia/` directory
- See Essentia documentation for build instructions

### Demucs Not Working
- Ensure PyTorch is installed: `pip install torch torchaudio`
- Install Demucs: `pip install demucs`
- Demucs will download models on first use (may take time)

### Raga Classification Not Working
The raga classification requires preprocessing (pitch extraction, tonic detection) which is not fully implemented. The pipeline will continue without raga classification and log a warning. To fully enable raga classification, you'll need to implement the preprocessing pipeline based on the `dataset_preprocessing.ipynb` notebook in the automatic-raga-recognition repo.

### Out of Memory Errors
- Process one class at a time: `--class bhajan`
- Reduce batch processing by processing fewer tracks
- Ensure sufficient disk space for output files

### Docker-Specific Issues

**Permission Errors:**
If you get permission errors when writing output files:
```bash
# Check Docker volume permissions
docker run --rm -it \
  -v "/home/saswata/web_dev/video maker/audio/song_gen/data:/app/data" \
  audio-pipeline \
  ls -la /app/data
```

**Docker Build Fails:**
- Ensure you have enough disk space (Docker images can be large)
- Check internet connection (needs to download packages)
- Try building with `--no-cache`: `docker build --no-cache -t audio-pipeline .`

**Container Can't Find Data:**
- Verify the volume mount path is correct
- Use absolute paths for volume mounting
- Check that the data directory exists on the host

**Slow Performance:**
- Consider using GPU if available (see GPU Support section)
- Process one class at a time: `--class bhajan`
- Increase Docker memory limit in Docker Desktop settings

## Restarting/Resuming

The pipeline is designed to be restartable:

- If output files already exist, they will be skipped (unless `--force` is used)
- You can safely interrupt and resume processing
- Use `--force` to reprocess specific tracks

## Output File Formats

### Track Analysis JSON (`track_name.analysis.json`)
```json
{
  "features": {
    "essentia": {
      "bpm": 120.5,
      "key": "C",
      "scale": "major",
      ...
    },
    "librosa": {
      "tempo": 120.0,
      "spectral_centroid_mean": 2000.5,
      ...
    },
    "demucs": {
      "vocal_presence_score": 0.85,
      ...
    }
  },
  "raga": {
    "raga": "Suraṭi",
    "confidence": 0.95,
    "status": "confident"
  },
  "metadata": {
    "track_name": "track1",
    "class": "bhajan",
    "sample_rate": 44100
  }
}
```

### Segment Analysis JSON (`seg000_analysis.json`)
Same as track analysis, plus:
```json
{
  "segment": {
    "index": 0,
    "start": 0.0,
    "end": 20.0,
    "duration": 20.0
  },
  ...
}
```

## Notes

- The pipeline preserves original files - it never modifies files in `data/<class>/`
- All outputs go to `data/_cache_wav/`, `data/_analysis/`, and `data/_segments/`
- Processing is parallelizable by class (run multiple instances with `--class` option)
- Large audio files may take significant time to process
- Demucs vocal separation is optional but recommended for bhajan tracks

## License

See the main project license.
