# StyleTTS2 Fine-tuning Guide with Docker

This guide will help you fine-tune StyleTTS2 to capture your own accent and phonetics using Docker for a clean, isolated environment with GPU support.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Understanding Fine-tuning](#understanding-fine-tuning)
4. [Data Preparation](#data-preparation)
5. [Docker Setup](#docker-setup)
6. [Step-by-Step Fine-tuning](#step-by-step-fine-tuning)
7. [Using Your Fine-tuned Model](#using-your-fine-tuned-model)
8. [Troubleshooting](#troubleshooting)

---

## Overview

**What is Fine-tuning?**
- Fine-tuning adapts a pre-trained StyleTTS2 model (trained on LibriTTS) to learn your specific voice characteristics
- You need **~1 hour of clean speech data** (approximately 1000 samples)
- The process takes **~4 hours on a single GPU** (A100) or longer on consumer GPUs
- Quality will be slightly lower than training from scratch, but much faster

**Why Docker?**
- Isolated environment with all dependencies pre-configured
- GPU support via NVIDIA Container Toolkit
- Reproducible setup across different machines
- No conflicts with your system Python packages

---

## Prerequisites

### 1. System Requirements

- **GPU**: NVIDIA GPU with CUDA support (minimum 6GB VRAM, 8GB+ recommended)
- **Docker**: Version 20.10+ with NVIDIA Container Toolkit installed
- **Disk Space**: ~10GB for Docker image + ~5GB for checkpoints and data

### 2. Required Downloads

#### A. Pre-trained LibriTTS Checkpoint
Download the pre-trained StyleTTS2 model trained on LibriTTS:

```bash
# Create checkpoints directory
mkdir -p StyleTTS2/checkpoints

# Download from Hugging Face (you'll need to download manually or use huggingface-cli)
# Visit: https://huggingface.co/yl4579/StyleTTS2-LibriTTS/tree/main
# Download: epochs_2nd_00020.pth (or latest checkpoint)
# Save to: StyleTTS2/checkpoints/epochs_2nd_00020.pth
```

**Alternative using `huggingface-cli`:**
```bash
pip install huggingface-hub
huggingface-cli download yl4579/StyleTTS2-LibriTTS epochs_2nd_00020.pth --local-dir StyleTTS2/checkpoints
```

#### B. Pre-trained Utils (Already in Repo)
The following should already be in `StyleTTS2/Utils/`:
- `Utils/ASR/` - Text aligner (epoch_00080.pth, config.yml)
- `Utils/JDC/` - Pitch extractor (bst.t7)
- `Utils/PLBERT/` - PL-BERT model (step_1000000.t7, config.yml)

If missing, download from the [StyleTTS2 repository](https://github.com/yl4579/StyleTTS2).

### 3. Your Voice Data

Prepare your audio recordings:
- **Format**: MP3, WAV, or any format supported by `torchaudio`
- **Quality**: Clean recordings, minimal background noise
- **Duration**: ~1 hour total (can be split into many short clips)
- **Sample Rate**: Any (will be resampled to 24 kHz automatically)
- **Text**: Exact transcriptions matching each audio file

**File Naming Convention:**
```
{name}_1.mp3  →  {name}_1.txt
{name}_2.mp3  →  {name}_2.txt
...
```

Example:
```
Dipa_1.mp3  →  Dipa_1.txt
Dipa_2.mp3  →  Dipa_2.txt
```

**Text File Format:**
- Plain text files with UTF-8 encoding
- One transcription per file, matching the audio exactly
- Example: `Dipa_1.txt` contains: `"Hello, this is my voice sample for fine-tuning."`

---

## Understanding Fine-tuning

### What Happens During Fine-tuning?

1. **Preprocessing** (`preprocess_dataset.py`):
   - Converts audio to 24 kHz mono WAV
   - Normalizes text transcriptions
   - Creates train/validation splits (95%/5%)
   - Generates filelists in StyleTTS2 format: `path.wav|transcription|speaker_id`

2. **Fine-tuning** (`finetune_multi.py`):
   - Loads pre-trained LibriTTS checkpoint
   - Adapts model to your voice using your audio/text pairs
   - Saves checkpoints every few epochs
   - Outputs final model: `styletts2_{speaker}.pth`

### Training Stages

StyleTTS2 fine-tuning has three stages:
1. **Initial epochs** (0-10): Basic adaptation
2. **Diffusion epochs** (10-30): Style diffusion training
3. **Joint epochs** (30+): Joint training with SLM adversarial loss

**Note**: If you run out of memory during joint epochs, you can skip them by setting `joint_epoch` > `epochs` in config, but quality may be slightly worse.

---

## Data Preparation

### Step 1: Organize Your Data

Create a folder structure:
```
your_data/
├── audio/
│   ├── Dipa_1.mp3
│   ├── Dipa_2.mp3
│   └── ...
└── text/
    ├── Dipa_1.txt
    ├── Dipa_2.txt
    └── ...
```

### Step 2: Verify Your Data

- **Audio files**: Should be clear, minimal noise
- **Text files**: Exact transcriptions (punctuation matters)
- **Pairs**: Every audio file must have a matching text file (same stem)

### Step 3: Check Data Volume

- **Minimum**: ~100 samples (10-15 minutes)
- **Recommended**: ~1000 samples (1 hour)
- **More is better**: Up to several hours for best quality

---

## Docker Setup

### Step 1: Install NVIDIA Container Toolkit

**For Ubuntu 24.04 (Modern Method - Recommended):**

Ubuntu 24.04 requires the modern installation method (no deprecated `apt-key`):

```bash
# Install prerequisites
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Create keyring directory
sudo install -m 0755 -d /etc/apt/keyrings

# Download and add NVIDIA GPG key (modern method, replaces apt-key)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /etc/apt/keyrings/nvidia-container-toolkit.gpg

# Add NVIDIA repository (use ubuntu20.04 repo - compatible with 24.04)
ARCH=$(dpkg --print-architecture)
echo "deb [signed-by=/etc/apt/keyrings/nvidia-container-toolkit.gpg] https://nvidia.github.io/libnvidia-container/stable/ubuntu20.04/${ARCH} /" | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install nvidia-container-toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use nvidia runtime
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker
sudo systemctl restart docker

# Verify installation
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**For Ubuntu 22.04 and earlier:**
```bash
# Add NVIDIA package repositories
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install nvidia-container-toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify installation
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
```

**Troubleshooting:**

If you get "Unsupported distribution" error:
- Ubuntu 24.04 is not in the old `nvidia-docker` repository
- Use the modern method above (with `libnvidia-container` repository)
- The `ubuntu20.04` repository works with Ubuntu 24.04

If `nvidia-ctk` command not found:
- The package might be named differently on your system
- Try: `sudo nvidia-container-toolkit configure` instead
- Or manually edit `/etc/docker/daemon.json` to add nvidia runtime

### Step 2: Build Docker Image

```bash
cd "/home/saswata/web_dev/video maker/audio/StyleTTS2_app/finetune_model"

# Build the image (this will take 10-20 minutes)
# Build from audio/ directory (parent of both StyleTTS2 and StyleTTS2_app)
docker build -t styletts2-finetune:latest -f Dockerfile ../..

# Verify build
docker images | grep styletts2-finetune
```

### Step 3: Verify GPU Access

```bash
# Test GPU access inside container
docker run --rm --gpus all styletts2-finetune:latest python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

---

## Step-by-Step Fine-tuning

### Step 1: Prepare Your Data Directory

```bash
# Create a directory structure for your project
mkdir -p finetune_project/{data,output,work}

# Copy your audio/text pairs
cp -r /path/to/your_data/* finetune_project/data/
```

### Step 2: Start Docker Container

**Option A: Using docker-compose (Recommended)**
```bash
# Edit docker-compose.yml to set your paths
# Then run:
docker-compose up -d

# View logs
docker-compose logs -f
```

**Option B: Using docker run**
```bash
cd "/home/saswata/web_dev/video maker/audio/StyleTTS2_app/finetune_model"

docker run -it --gpus all \
  --name styletts2-finetune \
  -v "/home/saswata/web_dev/video maker/audio/StyleTTS2:/workspace/StyleTTS2:ro" \
  -v "/home/saswata/web_dev/video maker/audio/StyleTTS2_app:/workspace/StyleTTS2_app:ro" \
  -v "$(pwd)/finetune_project:/workspace/finetune_project" \
  styletts2-finetune:latest \
  bash
```

### Step 3: Preprocess Your Data

Inside the Docker container:

```bash
# Navigate to workspace
cd /workspace

# Run preprocessing
python StyleTTS2_app/finetune_model/preprocess_dataset.py \
  --data_root /workspace/finetune_project/data \
  --work_dir /workspace/finetune_project/work \
  --sr 24000 \
  --val_ratio 0.05

# This will create:
# - work/wavs/{speaker}/{file}.wav (converted audio)
# - work/filelists/{speaker}_train.txt
# - work/filelists/{speaker}_val.txt
# - work/manifest.csv
# - work/speakers.json
```

**Expected Output:**
```
Found 1000 pairs across 1 speakers.
Train: 950  Val: 50
Saved speaker map to work/speakers.json
Done.
```

### Step 4: Verify Preprocessing

```bash
# Check generated files
ls -lh /workspace/finetune_project/work/wavs/
cat /workspace/finetune_project/work/filelists/Dipa_train.txt | head -3
# Should show: speaker/Dipa_1.wav|transcription text|0
```

### Step 5: Run Fine-tuning

Inside the Docker container:

```bash
# For single GPU with mixed precision (recommended for consumer GPUs)
python StyleTTS2_app/finetune_model/finetune_multi.py \
  --styletts2_repo /workspace/StyleTTS2 \
  --work_dir /workspace/finetune_project/work \
  --out_dir /workspace/finetune_project/output \
  --base_checkpoint /workspace/StyleTTS2/checkpoints/epochs_2nd_00020.pth \
  --base_config /workspace/StyleTTS2/Configs/config_ft.yml \
  --epochs 50 \
  --batch_size 4 \
  --use_accelerate

# For multiple GPUs or without accelerate
python StyleTTS2_app/finetune_model/finetune_multi.py \
  --styletts2_repo /workspace/StyleTTS2 \
  --work_dir /workspace/finetune_project/work \
  --out_dir /workspace/finetune_project/output \
  --base_checkpoint /workspace/StyleTTS2/checkpoints/epochs_2nd_00020.pth \
  --base_config /workspace/StyleTTS2/Configs/config_ft.yml \
  --epochs 50 \
  --batch_size 8
```

**Parameters Explained:**
- `--epochs 50`: Number of training epochs (default: 50 for 1 hour of data)
- `--batch_size 4`: Batch size (reduce if OOM, increase if you have VRAM)
- `--use_accelerate`: Use fp16 mixed precision (saves VRAM, faster)
- `--lr 0.0001`: Learning rate (optional override)
- `--speakers Dipa`: Specific speaker (optional, auto-detects if omitted)

**Training Time Estimates:**
- **Single GPU (RTX 3090)**: ~6-8 hours for 50 epochs
- **Single GPU (A100)**: ~4 hours for 50 epochs
- **Multiple GPUs**: Faster, but requires DDP (not fully supported)

### Step 6: Monitor Training

Training logs are saved to:
```
/workspace/finetune_project/output/{speaker}/train.log
/workspace/finetune_project/output/{speaker}/tensorboard/
```

**View logs in real-time:**
```bash
# In another terminal, attach to container
docker exec -it styletts2-finetune tail -f /workspace/finetune_project/output/Dipa/train.log

# Or view TensorBoard (if installed on host)
tensorboard --logdir finetune_project/output/Dipa/tensorboard
```

### Step 7: Check Final Model

After training completes:

```bash
# Check output directory
ls -lh /workspace/finetune_project/output/Dipa/

# Should contain:
# - styletts2_Dipa.pth (final model)
# - config_Dipa.yml (config used)
# - epoch_2nd_00050.pth (latest checkpoint)
# - train.log
```

---

## Using Your Fine-tuned Model

### Update Your Inference Code

In `StyleTTS2_app/infer_backend.py` or `app.py`, update the checkpoint path:

```python
# Old:
CHECKPOINT_PATH = str(STYLETTS2_DIR / "checkpoints" / "styletts2.pth")

# New:
CHECKPOINT_PATH = str(Path("/path/to/finetune_project/output/Dipa/styletts2_Dipa.pth"))
```

### Test Your Model

```python
from infer_backend import StyleTTS2Infer

# Load your fine-tuned model
tts = StyleTTS2Infer(CONFIG_PATH, CHECKPOINT_PATH)

# Generate speech
text = "Hello, this is my fine-tuned voice model!"
ref_audio = "path/to/reference_audio.wav"  # Can be any audio
output = "output.wav"

tts.synthesize(text, ref_audio, output)
```

---

## Troubleshooting

### 1. Docker Build Fails

**Error**: `nvidia-container-toolkit not found`
- **Solution**: Install NVIDIA Container Toolkit (see Docker Setup Step 1)

**Error**: `CUDA out of memory`
- **Solution**: Reduce `--batch_size` (try 2 or 4) or reduce `max_len` in config

### 2. Preprocessing Issues

**Error**: `No audio/text pairs found`
- **Solution**: Check file naming matches exactly (case-sensitive)

**Error**: `Missing text for audio files`
- **Solution**: Ensure every audio file has a matching `.txt` file

### 3. Training Issues

**Error**: `FileNotFoundError: epochs_2nd_00020.pth`
- **Solution**: Download LibriTTS checkpoint (see Prerequisites)

**Error**: `Loss becomes NaN`
- **Solution**: 
  - Reduce learning rate: `--lr 0.00005`
  - Increase batch size if possible
  - Check data quality (no corrupted audio files)

**Error**: `Out of memory after joint_epoch`
- **Solution**: 
  - Skip SLM adversarial training by setting `joint_epoch` > `epochs` in config
  - Or reduce `batch_percentage` in config to 0.3

**Error**: `RuntimeError: CUDA error: out of memory`
- **Solution**:
  - Use `--use_accelerate` flag (fp16 mixed precision)
  - Reduce `--batch_size` to 2 or 4
  - Reduce `max_len` in config (default 400, try 300)

### 4. Model Quality Issues

**Problem**: Generated speech doesn't sound like your voice
- **Solution**: 
  - Use more training data (aim for 1+ hours)
  - Ensure audio quality is high (clean, minimal noise)
  - Train for more epochs (try 100 instead of 50)

**Problem**: High-pitched background noise
- **Solution**: This is a known issue with older GPUs. Use a modern GPU or CPU inference.

### 5. Docker Container Issues

**Problem**: Container exits immediately
- **Solution**: Use `docker run -it` instead of `docker run -d` for interactive mode

**Problem**: Can't access GPU
- **Solution**: 
  ```bash
  # Verify nvidia-smi works
  nvidia-smi
  
  # Check Docker GPU access
  docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
  ```

---

## Quick Reference

### Complete Workflow (Copy-Paste)

```bash
# 1. Prepare data
mkdir -p finetune_project/{data,output,work}
# Copy your audio/text pairs to finetune_project/data/

# 2. Build Docker image
cd "/home/saswata/web_dev/video maker/audio/StyleTTS2/finetune_model"
docker build -t styletts2-finetune:latest -f Dockerfile ..

# 3. Run container
docker run -it --gpus all \
  -v "/home/saswata/web_dev/video maker/audio/StyleTTS2:/workspace/StyleTTS2" \
  -v "$(pwd)/finetune_project:/workspace/finetune_project" \
  styletts2-finetune:latest bash

# 4. Inside container: Preprocess
python StyleTTS2_app/finetune_model/preprocess_dataset.py \
  --data_root /workspace/finetune_project/data \
  --work_dir /workspace/finetune_project/work

# 5. Inside container: Fine-tune
python StyleTTS2_app/finetune_model/finetune_multi.py \
  --styletts2_repo /workspace/StyleTTS2 \
  --work_dir /workspace/finetune_project/work \
  --out_dir /workspace/finetune_project/output \
  --base_checkpoint /workspace/StyleTTS2/checkpoints/epochs_2nd_00020.pth \
  --base_config /workspace/StyleTTS2/Configs/config_ft.yml \
  --epochs 50 \
  --batch_size 4 \
  --use_accelerate

# 6. Your model is at:
# finetune_project/output/{speaker}/styletts2_{speaker}.pth
```

---

## Technical Deep Dive

### DP vs DDP: Understanding Parallel Training

**What is DP (DataParallel)?**

DP (PyTorch's `torch.nn.DataParallel`) is a **single-process, multi-GPU** training method:

- **How it works:**
  1. One main process runs on GPU 0
  2. Model is copied to all available GPUs
  3. Batch is split across GPUs (each GPU gets a portion)
  4. Each GPU computes forward pass and gradients independently
  5. Gradients are gathered on GPU 0 and averaged
  6. Model on GPU 0 is updated, then copied back to all GPUs

- **Advantages:**
  - Simple to use: just wrap model with `DataParallel(model)`
  - Works with minimal code changes
  - Good for quick multi-GPU experiments

- **Disadvantages:**
  - **Bottleneck**: All communication goes through GPU 0 (single process)
  - **Slower**: Gradient gathering/updates are sequential
  - **Memory inefficient**: Model replicated on each GPU
  - **Python GIL**: Single process limited by Python's Global Interpreter Lock

**What is DDP (DistributedDataParallel)?**

DDP (PyTorch's `torch.nn.parallel.DistributedDataParallel`) is a **multi-process, multi-GPU** training method:

- **How it works:**
  1. One process per GPU (each GPU has its own Python process)
  2. Each process has its own model copy
  3. Batch is split across processes
  4. Each process computes gradients independently
  5. Gradients are synchronized using **NCCL** (NVIDIA Collective Communications Library) - all-to-all communication
  6. Each process updates its model copy (they stay in sync)

- **Advantages:**
  - **Faster**: Parallel gradient synchronization (no single bottleneck)
  - **More efficient**: Better GPU utilization
  - **Scalable**: Works well with many GPUs
  - **No GIL bottleneck**: Each process runs independently

- **Disadvantages:**
  - More complex setup (requires process spawning, rank/world_size)
  - Some models/operations don't work well with DDP
  - Debugging is harder (multiple processes)

**Why StyleTTS2 Uses DP Instead of DDP**

From the README: *"DDP version not working, so the current version uses DP"*

The issue is likely related to:

1. **Complex model structure**: StyleTTS2 has multiple sub-modules (text_aligner, style_encoder, decoder, diffusion, etc.) that may not serialize well for DDP
2. **Custom operations**: The diffusion sampler, style encoding, and text alignment may have operations that don't work with DDP's gradient synchronization
3. **Dynamic computation**: Some parts of the model may have conditional paths that confuse DDP's gradient tracking

**In Practice:**

- **Single GPU**: Use regular model (no parallelization needed)
- **Multiple GPUs**: Use DP (works but slower than ideal)
- **For fine-tuning**: DP is usually sufficient since you're adapting a pre-trained model (fewer epochs needed)

The `train_finetune_accelerate.py` script uses HuggingFace's `Accelerator` which can use DDP, but it's configured for single GPU with mixed precision (fp16) to save VRAM.

---

### Audio Processing Pipeline: What Features Are Extracted?

StyleTTS2 extracts and uses multiple features from audio during training. Here's the complete pipeline:

#### 1. **Audio Loading & Preprocessing**

```python
# From meldataset.py
wave, sr = sf.read(audio_path)  # Load audio file
wave = librosa.resample(wave, orig_sr=sr, target_sr=24000)  # Resample to 24kHz
wave = np.concatenate([np.zeros([5000]), wave, np.zeros([5000])], axis=0)  # Add padding
```

**Why 24kHz?**
- Pre-trained models (ASR, F0 extractor) were trained on 24kHz audio
- Standard sample rate for TTS (balances quality vs. file size)

#### 2. **Mel Spectrogram Extraction**

```python
# Convert waveform to mel spectrogram
to_mel = torchaudio.transforms.MelSpectrogram(
    n_mels=80,           # 80 mel frequency bins
    n_fft=2048,         # FFT window size
    win_length=1200,    # Window length (50ms at 24kHz)
    hop_length=300      # Hop size (12.5ms at 24kHz)
)
mel_tensor = to_mel(wave_tensor)
mel_tensor = (torch.log(1e-5 + mel_tensor) - mean) / std  # Normalize
```

**What is a Mel Spectrogram?**
- **Spectrogram**: Time-frequency representation showing how energy changes over time
- **Mel scale**: Perceptually-motivated frequency scale (human ear is more sensitive to lower frequencies)
- **80 mel bins**: Compressed frequency representation (vs. 1024 FFT bins)
- **Shape**: `[80, T]` where T is number of time frames

**Why Mel Spectrogram?**
- Captures acoustic features needed for speech synthesis
- More compact than raw waveform
- Matches human auditory perception

#### 3. **Text Processing & Phonemization**

```python
# Text is converted to phoneme indices
text_cleaner = TextCleaner()  # Maps characters to indices
text_indices = text_cleaner(text)  # "Hello" -> [72, 101, 108, 108, 111]
```

**Phoneme Representation:**
- Text is converted to phonemes (IPA symbols) or character-level tokens
- Each phoneme/character gets a unique index
- Special tokens: padding (0), start-of-sequence, end-of-sequence

#### 4. **F0 (Pitch) Extraction**

```python
# Using pre-trained JDC (Joint Detection and Classification) model
pitch_extractor = load_F0_models("Utils/JDC/bst.t7")
F0 = pitch_extractor(mel_tensor)  # Extract fundamental frequency
```

**What is F0?**
- **Fundamental frequency**: The pitch of the voice (how high/low)
- **Units**: Hertz (Hz) - cycles per second
- **Range**: Typically 50-400 Hz for human speech
- **Shape**: `[T]` - one value per time frame

**Why F0?**
- Controls prosody (intonation, emotion)
- Essential for natural-sounding speech
- Separates content (text) from style (pitch)

#### 5. **Text-Audio Alignment (ASR Model)**

```python
# Pre-trained ASR (Automatic Speech Recognition) model
text_aligner = load_ASR_models(ASR_path, ASR_config)
ppgs, s2s_pred, s2s_attn = text_aligner(mels, mask, texts)
```

**What does alignment do?**
- **Purpose**: Maps each phoneme to its corresponding time segment in audio
- **Output**: Attention matrix showing which audio frames correspond to which phonemes
- **Example**: Phoneme "H" might align to frames 0-5, "e" to frames 6-12, etc.

**Why is alignment needed?**
- Text and audio have different lengths (text: ~10 phonemes, audio: ~500 frames)
- Model needs to know which audio frames correspond to which phonemes
- Enables learning duration (how long each phoneme should be)

#### 6. **PL-BERT Text Encoding**

```python
# Pre-trained PL-BERT (Phoneme-Level BERT)
plbert = load_plbert("Utils/PLBERT/")
bert_dur = plbert(tokens, attention_mask=text_mask)  # Encode phonemes
```

**What is PL-BERT?**
- **BERT**: Bidirectional Encoder Representations from Transformers
- **Phoneme-Level**: Trained on phoneme sequences (not words)
- **Output**: Contextual embeddings for each phoneme
- **Shape**: `[batch, phonemes, 768]` - 768-dimensional vectors

**Why PL-BERT?**
- Captures phoneme context (same phoneme sounds different in different contexts)
- Better than one-hot encoding (which ignores context)
- Helps model understand pronunciation rules

#### 7. **Style Encoding**

```python
# Extract style vector from reference audio
style_encoder = model.style_encoder
ref_s = style_encoder(ref_mel_tensor)  # [batch, 128] - style vector
```

**What is style?**
- **Style vector**: 128-dimensional representation of voice characteristics
- **Captures**: Speaker identity, emotion, speaking rate, accent
- **Extracted from**: Reference audio sample (can be different from training audio)

**Why style encoding?**
- Enables voice cloning (synthesize in different voices)
- Separates content (what to say) from style (how to say it)
- Allows zero-shot adaptation (use voice not in training set)

#### 8. **Duration Prediction**

```python
# Predict how long each phoneme should last
duration_predictor = model.predictor
duration = duration_predictor(bert_dur, style_vector)  # [batch, phonemes]
```

**What is duration?**
- **Duration**: Number of audio frames each phoneme should occupy
- **Example**: "Hello" -> [5, 8, 4, 4, 6] frames for H, e, l, l, o
- **Total**: Sum of durations = total audio length

**Why predict duration?**
- Different phonemes have different natural lengths
- Context affects duration (vowels longer in stressed syllables)
- Needed to convert phoneme sequence to audio sequence

#### 9. **Feature Summary**

| Feature | Type | Shape | Purpose |
|---------|------|-------|---------|
| **Mel Spectrogram** | Acoustic | `[80, T]` | Main audio representation |
| **F0 (Pitch)** | Prosody | `[T]` | Controls intonation |
| **Text Tokens** | Linguistic | `[phonemes]` | What to say |
| **PL-BERT Embeddings** | Linguistic | `[phonemes, 768]` | Phoneme context |
| **Alignment Matrix** | Temporal | `[T, phonemes]` | Text-audio mapping |
| **Style Vector** | Speaker | `[128]` | Voice characteristics |
| **Duration** | Temporal | `[phonemes]` | Phoneme lengths |

#### 10. **Training Process**

During training, the model learns to:

1. **Align**: Match phonemes to audio frames (using ASR model)
2. **Predict Duration**: Learn how long each phoneme should be
3. **Encode Style**: Extract voice characteristics from reference audio
4. **Generate Mel**: Create mel spectrogram from text + style
5. **Synthesize Audio**: Convert mel spectrogram to waveform (using vocoder)

**Loss Functions:**
- **Mel Loss**: How close predicted mel is to ground truth
- **F0 Loss**: How close predicted pitch is to ground truth
- **Duration Loss**: How close predicted durations are to aligned durations
- **Alignment Loss**: Encourages monotonic alignment (phonemes in order)
- **Adversarial Loss**: Uses WavLM to judge naturalness
- **Diffusion Loss**: For style generation (in second stage)

#### 11. **No Explicit Classification**

**Important**: StyleTTS2 does **NOT** use classification for:
- Speaker identification (uses continuous style vectors)
- Phoneme recognition (uses alignment, not classification)
- Emotion detection (captured in style vector)

Instead, it uses:
- **Regression**: Predict continuous values (mel, F0, duration)
- **Attention**: Learn alignments (soft attention matrices)
- **Embeddings**: Continuous representations (style, phoneme embeddings)

This makes the model more flexible and able to generalize to new speakers/accents.

---

## Additional Resources

- [StyleTTS2 Original README](../README.md)
- [StyleTTS2 GitHub Issues](https://github.com/yl4579/StyleTTS2/issues)
- [Fine-tuning Discussion #81](https://github.com/yl4579/StyleTTS2/discussions/81)
- [Fine-tuning Guide #128](https://github.com/yl4579/StyleTTS2/discussions/128)

---

## License

Fine-tuning code: MIT License  
Pre-trained models: See [StyleTTS2 License](../LICENSE) and usage terms in main README.

**Important**: If you use the pre-trained LibriTTS model, you agree to inform listeners that synthesized speech is generated by AI, unless you have permission to use the voice you're cloning.

